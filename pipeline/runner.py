"""One user message through the pipeline (plan §3.1).

intent → compute → fact sheet → compose → render and verify → at most one repair → degrade.
Calculations and the submission go through execute_calls as planned calls, so the Guard,
validate_reading, the store and the trace treat them like a model's calls. Each user message
uses at most three model calls: an intent call where code alone cannot read the question
(pipeline/dream.py), the draft and one repair. What differs between systems is in their
pipeline.system.System; the steps here are shared.
"""

from __future__ import annotations

import json
import re
import uuid

from common.validation import HIGH_RISK
from harness.budget import Budget
from harness.failures import failure, model_failure
from harness.loop import call_model, estimate_call, execute_calls
from harness.models import ModelResponse, ToolCall, TurnOutcome
from pipeline import compose, intent
from pipeline.daily import Daily
from pipeline.dream import Dream
from pipeline.name import Name
from pipeline.render import expand, reading_args
from pipeline.state import RESUMABLE, PipelineRun, restore, snapshot
from pipeline.tarot import SAFETY_FALLBACK, Tarot
from pipeline.verify import safety_rules

# In the order their detection runs: a message is the first system's that claims it.
SYSTEM_TYPES = (Tarot, Dream, Name, Daily)
MAX_REPAIRS = 1
TRUNCATED = "上一稿超过输出上限被截断：请精简为摘要加2-3层，每层不超过250字"
# Problems that fail a safety rule rather than a fact (common/validation.py, output_policy.py):
# after the repair, these end in a safety reply without any reading of the cards.
HARD_SAFETY = re.compile(
    r"不能给出健康、投资或生死的确定性结论|不能给出确定性结果或停药建议|不能劝阻就医"
)
CERTAINTY = re.compile(r"这类确定性说法")
__all__ = ["SAFETY_FALLBACK", "SYSTEM_TYPES", "PipelineRunner"]


class PipelineRunner:
    def __init__(self, runtime):
        self.runtime = runtime
        self.session = runtime.session
        self.store = runtime.store
        self.tracer = runtime.tracer
        self.step = 0
        self.systems = {kind.name: kind(runtime) for kind in SYSTEM_TYPES}

    async def turn(self, message: str) -> TurnOutcome | None:
        """None when the pipeline does not handle this message; the agent loop does."""
        found = self.detect(message)
        if found is None:
            return None
        self.session.append_user(message)
        self.stage("intent", kind=found.kind)
        try:
            outcome = await self.run(found, message)
        except Exception as exc:
            # API exceptions can carry request details: never log their text.
            self.tracer.log(self.session, "model_error", error_type=type(exc).__name__)
            outcome = model_failure(self.session, exc)
        self.session.messages.append({"role": "assistant", "content": outcome.text})
        return outcome

    def detect(self, message: str) -> intent.Intent | None:
        for name, system in self.systems.items():
            if name in self.runtime.pipeline_systems:
                found = system.detect(self.runtime, message)
                if found is not None:
                    return found
        return None

    # ---- stages --------------------------------------------------------------------------

    async def run(self, found: intent.Intent, message: str) -> TurnOutcome:
        state = self.session.state
        prior = None
        extra = ""
        system = self.systems[found.system]
        if found.kind == "new":
            stale = self.store.unfinished_pipeline_run(self.session.user_id)
            if stale:
                self.store.finish_pipeline_run(stale["run_id"])  # an abandoned calculation
            run = PipelineRun(system.name, "new", system.question(message))
            stopped = await system.compute(self, run)
            if stopped is not None:
                return stopped
            run.snapshot = snapshot(self.session.state)
            run.save(self.store, self.session, "computed")
        elif found.kind == "resume":
            if found.run is not None:
                run = PipelineRun.load(found.run)
                restore(self.session, run.snapshot)
                self.stage("resume", run_id=run.run_id)
            else:
                stored = self.store.unfinished_pipeline_run(self.session.user_id)
                same = stored and stored.get("reading_id") == state.get("active_reading_id")
                if stored and not same:
                    self.store.finish_pipeline_run(stored["run_id"])  # another, abandoned draw
                run = (
                    PipelineRun.load(stored)
                    if same
                    else PipelineRun(system.name, "new", state.get("question") or message)
                )
                run.snapshot = snapshot(self.session.state)
                # A run stopped after a failed draft keeps its stage, so it resumes at the repair.
                run.save(
                    self.store, self.session, run.stage if run.stage in RESUMABLE else "computed"
                )
            if message.strip() != run.question.strip() and not intent.CONTINUE.search(message):
                extra = message.strip()
        else:
            run = PipelineRun(system.name, "followup", system.question(message))
            results, _ = await self.planned([("read_reading", {"reading_id": found.reading_id})])
            if not results[0]["ok"]:
                return failure(self.session, "tool_error", results[0].get("code"), "没有找到原记录")
            saved = results[0]["data"]["reading"]
            prior = {"question": saved["question"], "summary": saved["output_json"]["summary"]}
        return await self.write(run, prior=prior, extra=extra)

    async def write(self, run: PipelineRun, *, prior=None, extra="") -> TurnOutcome:
        system = self.systems[run.system]
        facts = system.facts(self.session)
        state = self.session.state
        followup = run.kind == "followup"
        question_type = system.question_type(run, self.session, followup)
        # The reading's question counts as much as this turn's: a follow-up to a question about
        # savings and stocks carries the same risk, exactly as validate_reading judges it.
        risk_text = f"{state.get('question') or ''} {run.question}"
        template = (
            None if followup else system.template(self.session, facts, question_type, risk_text)
        )
        if template is not None:
            # Nothing to interpret: code writes the whole reading, no writing call is made.
            run.degraded, args = template
            self.stage("template", run_id=run.run_id, kind=run.degraded)
            return await self.submit_by_code(run, args)
        messages = system.messages(run, facts, self.session, prior=prior, extra=extra)
        try:
            if run.stage == "composed" and run.drafts and run.repairs < MAX_REPAIRS:
                # The run stopped after a failed draft: continue at its repair.
                draft_text, truncated = run.drafts[-1], False
                problems = run.problems[-1] if run.problems else []
            else:
                self.stage("compose", run_id=run.run_id)
                draft_text, truncated = await self.ask(messages, "compose", run)
                problems = None
            while True:
                if problems is None:
                    run.drafts.append(draft_text)
                    run.safety.append(self.classify(draft_text, facts, risk_text, run))
                    if truncated:
                        problems, terminal = [TRUNCATED], None
                    else:
                        problems, terminal = await self.check_and_submit(
                            run, draft_text, facts, question_type, risk_text, followup
                        )
                    if terminal is not None:
                        return self.finish(run, terminal)
                    run.problems.append(problems)
                if run.repairs >= MAX_REPAIRS:
                    break
                self.keep(run)
                self.stage("repair", run_id=run.run_id, problems=len(problems))
                messages = compose.repair_messages(messages, draft_text, problems, facts)
                draft_text, truncated = await self.ask(messages, "repair", run)
                # Counted once the repair is written: an interrupted one is still to do.
                run.repairs += 1
                problems = None
        except OutOfBudget:
            run.problems.append(["本轮token预算已用尽"])
        except Stopped as stop:
            self.keep(run)
            return stop.outcome
        last = set(run.safety[-1]) if run.safety else set()
        hard = (
            any(HARD_SAFETY.search(p) for p in run.problems[-1])
            or bool(
                HIGH_RISK.search(risk_text)
                and any(CERTAINTY.search(p) for problems in run.problems for p in problems)
            )
            or bool(last & {"discourage_care", "hard_claim"})
            or any("certainty" in rules for rules in run.safety)
        )
        run.degraded = "safety" if hard else "keywords"
        self.stage("degrade", run_id=run.run_id, kind=run.degraded)
        args = system.degraded(
            self.session, facts, question_type, risk_text, followup, safety_only=hard
        )
        return await self.submit_by_code(run, args)

    def classify(self, draft_text: str, facts, risk_text: str, run: PipelineRun) -> list[str]:
        """The hard safety rules this draft breaks, whatever its first reported problem is."""
        rendered, _, _ = expand(draft_text, {fact.alias: fact for fact in facts})
        rules = safety_rules([rendered], risk_text)
        if rules:
            self.stage("safety", run_id=run.run_id, draft=len(run.drafts), rules=rules)
        return rules

    async def submit_by_code(self, run: PipelineRun, args: dict) -> TurnOutcome:
        """Submit a reading code wrote; if even that is refused, keep the run for 继续."""
        try:
            _, terminal = await self.submit(run, args)
        except Stopped as stop:
            self.keep(run)
            return stop.outcome
        if terminal is not None:
            return self.finish(run, terminal)
        self.keep(run)
        return failure(
            self.session,
            "validation_failed",
            "pipeline_degrade_failed",
            f"这次解读没有通过事实核对，{self.systems[run.system].kept}已保留；可以发送“继续”重试。",
        )

    async def check_and_submit(self, run, draft_text, facts, question_type, risk_text, followup):
        """(problems, terminal outcome); the outcome is set when the reading was saved."""
        system = self.systems[run.system]
        draft, problems = compose.parse(draft_text, sections_required=not followup)
        if problems:
            return problems, None
        args, problems, texts = reading_args(
            draft, facts, question_type=question_type, question=risk_text
        )
        problems += system.problems(texts, self.session)
        if problems:
            return problems, None
        system.complete(args, self.session)
        result, terminal = await self.submit(run, args)
        if terminal is not None:
            return [], terminal
        if result.get("code") == "birth_version_conflict":
            # The birth form changed meanwhile: nothing written from it may be saved or retried.
            return [], failure(
                self.session, "birth_version_conflict", "birth_version_conflict", result["error"]
            )
        return [result.get("error") or "提交未通过"], None

    async def submit(self, run: PipelineRun, args: dict):
        """Submit through submit_reading; the run's record is saved with the reading."""
        self.session.state["pipeline_run"] = run.record()
        try:
            results, terminal = await self.planned([("submit_reading", args)])
        finally:
            # A later turn of the agent loop on this state must not inherit this run's record.
            self.session.state.pop("pipeline_run", None)
        if terminal is not None and terminal.status != "submit_reading":
            # Only a saved reading finishes a run; any other ending keeps it for 继续.
            raise Stopped(terminal)
        return results[0], terminal

    def keep(self, run: PipelineRun) -> None:
        """Store a run that drew cards; a follow-up has no draw of its own to resume."""
        if run.kind != "followup":
            run.save(self.store, self.session, "composed" if run.drafts else "computed")

    def finish(self, run: PipelineRun, terminal: TurnOutcome) -> TurnOutcome:
        if terminal.status != "submit_reading":
            # A conflict or another refusal: nothing was saved, and nothing is left to resume.
            self.store.finish_pipeline_run(run.run_id)
            return terminal
        self.store.finish_pipeline_run(run.run_id)
        self.stage("done", run_id=run.run_id, degraded=run.degraded, repairs=run.repairs)
        terminal.data["pipeline"] = run.record()
        return terminal

    # ---- helpers -------------------------------------------------------------------------

    def stage(self, name: str, **fields) -> None:
        self.tracer.log(self.session, "pipeline_stage", stage=name, **fields)

    async def planned(self, calls: list[tuple[str, dict]]):
        """Run code-issued calls like a model's; returns (model-visible results, terminal).

        The pipeline bounds its own attempts (at most three submissions), so each planned call
        counts repeated failures on its own instead of reaching the agent loop's retry limit.
        """
        response = ModelResponse(
            planned=True,
            tool_calls=[
                ToolCall(id=f"plan-{uuid.uuid4().hex[:12]}", name=name, arguments=args)
                for name, args in calls
            ],
        )
        self.session.messages.append(response.assistant_message())
        self.tracer.log(
            self.session, "tool_plan", step=self.step, tool_names=[name for name, _ in calls]
        )
        terminal = await execute_calls(
            self.session,
            self.runtime.registry,
            self.tracer,
            response.tool_calls,
            step=self.step,
            failed_attempts={},
        )
        self.step += 1
        ids = {call.id for call in response.tool_calls}
        results = [
            json.loads(m["content"])
            for m in self.session.messages
            if m["role"] == "tool" and m["tool_call_id"] in ids
        ]
        return results, terminal

    async def ask(self, messages: list[dict], purpose: str, run: PipelineRun) -> tuple[str, bool]:
        """(the model's text, whether it was cut off at the output limit).

        The call goes through the agent loop's model boundary: it is admitted against the
        request's token budget, charged and traced, and a response without usage is not used.
        """
        budget = self.session.budget or Budget(self.runtime.token_budget)
        called = await call_model(
            self.session,
            self.runtime.model,
            messages,
            [],
            budget,
            self.tracer,
            step=self.step,
            estimate=estimate_call(messages, [], None, 0),
            admission=True,
            purpose=purpose,
        )
        self.step += 1
        if called.stop == "budget":
            raise OutOfBudget
        if called.stop == "timeout":
            self.tracer.log(self.session, "timeout", step=self.step)
            raise Stopped(
                failure(
                    self.session,
                    "timeout",
                    "request_timeout",
                    "本轮达到请求时限，请发送“继续”接着写，或缩小问题范围。",
                )
            )
        if called.outcome is not None:
            raise Stopped(called.outcome)
        run.model_calls += 1
        response = called.response
        # A cut-off draft is a format problem: the repair asks for a shorter one.
        return response.text, response.finish_reason == "length"


class OutOfBudget(Exception):
    """The request's token budget refuses another writing call; code writes the reading."""


class Stopped(Exception):
    """The turn ends with this outcome; the run is kept so “继续” resumes it."""

    def __init__(self, outcome: TurnOutcome):
        super().__init__(outcome.status)
        self.outcome = outcome
