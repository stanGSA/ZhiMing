"""One user message through the pipeline (plan §3.1).

intent → compute → fact sheet → compose → render and verify → at most one repair → degrade.
Calculations and the submission go through execute_calls as planned calls, so the Guard,
validate_reading, the store and the trace treat them like a model's calls. Each user message
uses at most two model calls, shared by writing, repair and optional semantic checks.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from common.validation import HIGH_RISK
from harness.budget import Budget
from harness.failures import failure, model_failure
from harness.loop import call_model, estimate_call, execute_calls
from harness.models import ModelResponse, ToolCall, TurnOutcome
from pipeline import compose, intent, verify
from pipeline.factsheet import Fact, tarot_facts
from pipeline.render import reading_args, safety_for
from pipeline.state import RESUMABLE, PipelineRun, restore, snapshot
from plugins.tarot.catalogue import SPREADS

SPREAD_NAMES = {"single": "单张牌", "three_card": "三张牌", "decision": "二选一牌阵"}
TIMING = re.compile(r"什么时候|何时|时机|下个?月|下周|这周|本周|这个月|本月|今年|明年|下半年")
# The browser appends the chosen spread to the message; the reading keeps the question itself.
SPREAD_NOTE = re.compile(r"\n*我选择的牌阵为：[^\n]*")
MAX_REPAIRS = 1
MAX_MODEL_CALLS = 2  # Writing, repair and optional semantic checks share this per-turn limit.
TRUNCATED = "上一稿超过输出上限被截断：请精简为摘要加2-3层，每层不超过250字"
# Problems that fail a safety rule rather than a fact (common/validation.py, output_policy.py):
# after the repair, these end in a safety reply without any reading of the cards.
HARD_SAFETY = re.compile(
    r"不能给出健康、投资或生死的确定性结论|不能给出确定性结果或停药建议|不能劝阻就医"
)
CERTAINTY = re.compile(r"这类确定性说法")
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"


class PipelineRunner:
    def __init__(self, runtime):
        self.runtime = runtime
        self.session = runtime.session
        self.store = runtime.store
        self.tracer = runtime.tracer
        self.step = 0

    async def turn(self, message: str) -> TurnOutcome | None:
        """None when the pipeline does not handle this message; the agent loop does."""
        found = intent.detect(self.runtime, message)
        if found is None:
            return None
        # The submit tool's optional semantic judge reads turn_budget, including after a
        # previous turn fell back to the agent loop. Never leave it pointing at that old turn.
        budget = self.session.budget or Budget(self.runtime.token_budget)
        budget.max_model_calls = MAX_MODEL_CALLS
        self.session.budget = self.session.turn_budget = budget
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

    # ---- stages --------------------------------------------------------------------------

    async def run(self, found: intent.Intent, message: str) -> TurnOutcome:
        state = self.session.state
        prior = None
        extra = ""
        if found.kind == "new":
            stale = self.store.unfinished_pipeline_run(self.session.user_id)
            if stale:
                self.store.finish_pipeline_run(stale["run_id"])  # an abandoned draw
            question = SPREAD_NOTE.sub("", message).strip() or message
            run = PipelineRun("tarot", "new", question)
            results, _ = await self.planned(
                [
                    ("start_reading", {"question": question, "systems": ["tarot"]}),
                    ("draw_tarot", {"question": question}),
                ]
            )
            if not all(result["ok"] for result in results):
                error = next(r for r in results if not r["ok"])
                return failure(self.session, "tool_error", error.get("code"), error["error"])
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
                    else PipelineRun("tarot", "new", state.get("question") or message)
                )
                run.snapshot = snapshot(self.session.state)
                # A run stopped after a failed draft keeps its stage, so it resumes at the repair.
                run.save(
                    self.store, self.session, run.stage if run.stage in RESUMABLE else "computed"
                )
            if message.strip() != run.question.strip() and not intent.CONTINUE.search(message):
                extra = message.strip()
        else:
            run = PipelineRun("tarot", "followup", SPREAD_NOTE.sub("", message).strip() or message)
            results, _ = await self.planned([("read_reading", {"reading_id": found.reading_id})])
            if not results[0]["ok"]:
                return failure(self.session, "tool_error", results[0].get("code"), "没有找到原记录")
            saved = results[0]["data"]["reading"]
            prior = {"question": saved["question"], "summary": saved["output_json"]["summary"]}
        return await self.write(run, prior=prior, extra=extra)

    async def write(self, run: PipelineRun, *, prior=None, extra="") -> TurnOutcome:
        # Count every returned model response, including discarded drafts and the submit
        # tool's semantic checks. The same record must be current *before* the store saves it.
        def counted(event):
            if event["event"] == "model_response" and event["session_id"] == self.session.id:
                run.model_calls += 1
                if record := self.session.state.get("pipeline_run"):
                    record["model_calls"] = run.model_calls

        self.tracer.listeners.append(counted)
        try:
            return await self.write_draft(run, prior=prior, extra=extra)
        except asyncio.CancelledError:
            self.keep(run)
            raise
        finally:
            self.tracer.listeners.remove(counted)

    async def write_draft(self, run: PipelineRun, *, prior=None, extra="") -> TurnOutcome:
        facts = tarot_facts(self.session)
        state = self.session.state
        spread = state["tarot_result"]["spread"]
        spread_note = f"{SPREAD_NAMES[spread]}（{'、'.join(SPREADS[spread])}）"
        followup = run.kind == "followup"
        question_type = self.question_type(run.question, spread, followup)
        # The reading's question counts as much as this turn's: a follow-up to a question about
        # savings and stocks carries the same risk, exactly as validate_reading judges it.
        risk_text = f"{state.get('question') or ''} {run.question}"
        messages = compose.tarot_messages(
            run.question, spread_note, facts, extra=extra, prior=prior
        )
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
            run.problems.append(["本轮模型调用或token预算已用尽"])
        except Stopped as stop:
            self.keep(run)
            return stop.outcome
        hard = any(HARD_SAFETY.search(p) for p in run.problems[-1]) or bool(
            HIGH_RISK.search(risk_text)
            and any(CERTAINTY.search(p) for problems in run.problems for p in problems)
        )
        run.degraded = "safety" if hard else "keywords"
        self.stage("degrade", run_id=run.run_id, kind=run.degraded)
        args = self.degraded(facts, question_type, risk_text, followup, safety_only=hard)
        _, terminal = await self.submit(run, args)
        if terminal is not None:
            return self.finish(run, terminal)
        self.keep(run)
        return failure(
            self.session,
            "validation_failed",
            "pipeline_degrade_failed",
            "这次解读没有通过事实核对，牌面已保留；可以发送“继续”重试。",
        )

    async def check_and_submit(self, run, draft_text, facts, question_type, risk_text, followup):
        """(problems, terminal outcome); the outcome is set when the reading was saved."""
        draft, problems = compose.parse(draft_text, sections_required=not followup)
        if problems:
            return problems, None
        args, problems, texts = reading_args(
            draft, facts, question_type=question_type, question=risk_text
        )
        problems += verify.tarot_problems(texts, verify.drawn_cards(self.session.state))
        if problems:
            return problems, None
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

    @staticmethod
    def question_type(question: str, spread: str, followup: bool) -> str:
        if followup:
            return "tarot"
        if spread == "decision":
            return "decision"
        return "timing" if TIMING.search(question) else "tarot"

    def degraded(
        self, facts: list[Fact], question_type: str, risk_text: str, followup: bool, *, safety_only
    ):
        """A reading made by code alone.

        Normally each card, its position and its keywords. When the drafts failed on a safety
        rule of a high-risk question, no interpretation at all: the cards and the safety note.
        """
        cards = {card["label"]: card for card in self.session.state["tarot_result"]["cards"]}
        listed = "、".join(f"{fact.label}位{fact.text}" for fact in facts)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            return {
                "question_type": question_type,
                "systems_used": ["tarot"],
                "summary": f"这次抽到{listed}。这个问题牵涉重大的现实决定，这次不根据牌面给出判断。"[
                    :200
                ],
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：把实际情况交给相关专业人士评估，再决定下一步。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出牌面解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
        sections = []
        for fact in facts:
            keywords = "、".join((cards[fact.label].get("meaning") or {}).get("keywords") or [])
            body = f"{fact.label}位是{fact.text}。"
            if keywords:
                body += f"这张牌常和{keywords}有关，可以对照你现在的处境想一想。"
            sections.append(
                {"title": f"{fact.label}位：{fact.text}", "body": body, "ref_ids": [fact.alias]}
            )
        summary = (
            f"你问到的牌面是：{listed}。下面先给出每张牌的一般含义，请结合自己的处境对照。"
            if followup
            else f"这次抽到{listed}。下面先给出每张牌的一般含义，请结合自己的处境对照。"
        )
        return {
            "question_type": question_type,
            "systems_used": ["tarot"],
            "summary": summary[:200],
            "sections": sections,
            "evidence": evidence,
            "advice": [
                "先对照：把每张牌的关键词和你最近的处境逐条对一对。",
                "再行动：选一件最能落地的小事先做，过一段时间再回头看。",
            ],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了牌面的一般含义。"},
            "safety": safety,
        }

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
        response = called.response
        # A cut-off draft is a format problem: the repair asks for a shorter one.
        return response.text, response.finish_reason == "length"


class OutOfBudget(Exception):
    """The token or dispatch budget refuses another writing call; code writes the reading."""


class Stopped(Exception):
    """The turn ends with this outcome; the run is kept so “继续” resumes it."""

    def __init__(self, outcome: TurnOutcome):
        super().__init__(outcome.status)
        self.outcome = outcome
