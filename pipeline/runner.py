"""One user message through the pipeline (plan §3.1).

intent → compute → fact sheet → compose → render and verify → at most one repair → degrade.
Calculations and the submission go through execute_calls as planned calls, so the Guard,
validate_reading, the store and the trace treat them like a model's calls. Each user message
uses at most two model calls here: the draft and one repair.
"""

from __future__ import annotations

import json
import re
import uuid

from harness.failures import failure, model_failure
from harness.loop import execute_calls
from harness.models import ModelResponse, ToolCall, TurnOutcome
from pipeline import compose, intent, verify
from pipeline.factsheet import Fact, tarot_facts
from pipeline.render import reading_args
from pipeline.state import PipelineRun, restore, snapshot
from plugins.tarot.catalogue import SPREADS

SPREAD_NAMES = {"single": "单张牌", "three_card": "三张牌", "decision": "二选一牌阵"}
TIMING = re.compile(r"什么时候|何时|时机|下个?月|下周|这周|本周|这个月|本月|今年|明年|下半年")
# The browser appends the chosen spread to the message; the reading keeps the question itself.
SPREAD_NOTE = re.compile(r"\n*我选择的牌阵为：[^\n]*")
MAX_REPAIRS = 1
TRUNCATED = "上一稿超过输出上限被截断：请精简为摘要加2-3层，每层不超过250字"


class PipelineRunner:
    def __init__(self, runtime):
        self.runtime = runtime
        self.session = runtime.session
        self.store = runtime.store
        self.tracer = runtime.tracer
        self.failed: dict[tuple, int] = {}
        self.step = 0

    async def turn(self, message: str) -> TurnOutcome | None:
        """None when the pipeline does not handle this message; the agent loop does."""
        found = intent.detect(self.runtime, message)
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
                run = (
                    PipelineRun.load(stored)
                    if same
                    else PipelineRun("tarot", "new", state.get("question") or message)
                )
                run.snapshot = snapshot(self.session.state)
                run.save(self.store, self.session, "computed")
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
        facts = tarot_facts(self.session)
        state = self.session.state
        spread = state["tarot_result"]["spread"]
        spread_note = f"{SPREAD_NAMES[spread]}（{'、'.join(SPREADS[spread])}）"
        followup = run.kind == "followup"
        question_type = self.question_type(run.question, spread, followup)
        messages = compose.tarot_messages(
            run.question, spread_note, facts, extra=extra, prior=prior
        )
        self.stage("compose", run_id=run.run_id)
        draft_text, truncated = await self.ask(messages, "compose")
        run.model_calls += 1
        while True:
            run.drafts.append(draft_text)
            if truncated:
                problems, terminal = [TRUNCATED], None
            else:
                problems, terminal = await self.check_and_submit(
                    draft_text, facts, question_type, run.question, followup
                )
            if terminal is not None:
                return self.finish(run, terminal, degraded=False)
            run.problems.append(problems)
            if run.repairs >= MAX_REPAIRS:
                break
            run.repairs += 1
            run.save(self.store, self.session, "composed")
            self.stage("repair", run_id=run.run_id, problems=len(problems))
            messages = compose.repair_messages(messages, draft_text, problems, facts)
            draft_text, truncated = await self.ask(messages, "repair")
            run.model_calls += 1
        self.stage("degrade", run_id=run.run_id)
        args = self.degraded(facts, question_type, run.question, followup)
        results, terminal = await self.planned([("submit_reading", args)])
        if terminal is not None:
            return self.finish(run, terminal, degraded=True)
        run.save(self.store, self.session, "composed")
        return failure(
            self.session,
            "validation_failed",
            "pipeline_degrade_failed",
            "这次解读没有通过事实核对，牌面已保留；可以发送“继续”重试。",
        )

    async def check_and_submit(self, draft_text, facts, question_type, question, followup):
        """(problems, terminal outcome); the outcome is set when the reading was saved."""
        draft, problems = compose.parse(draft_text, sections_required=not followup)
        if problems:
            return problems, None
        args, problems, texts = reading_args(
            draft, facts, question_type=question_type, question=question
        )
        problems += verify.tarot_problems(texts, verify.drawn_cards(self.session.state))
        if problems:
            return problems, None
        results, terminal = await self.planned([("submit_reading", args)])
        if terminal is not None:
            return [], terminal
        result = results[0]
        if result.get("code") == "birth_version_conflict":
            # The birth form changed meanwhile: nothing written from it may be saved or retried.
            return [], failure(
                self.session, "birth_version_conflict", "birth_version_conflict", result["error"]
            )
        return [result.get("error") or "提交未通过"], None

    def finish(self, run: PipelineRun, terminal: TurnOutcome, *, degraded: bool) -> TurnOutcome:
        self.store.finish_pipeline_run(run.run_id)
        self.stage("done", run_id=run.run_id, degraded=degraded, repairs=run.repairs)
        terminal.data["pipeline"] = {
            "run_id": run.run_id,
            "kind": run.kind,
            "model_calls": run.model_calls,
            "repairs": run.repairs,
            "degraded": degraded,
            "problems": run.problems,
        }
        return terminal

    # ---- helpers -------------------------------------------------------------------------

    @staticmethod
    def question_type(question: str, spread: str, followup: bool) -> str:
        if followup:
            return "tarot"
        if spread == "decision":
            return "decision"
        return "timing" if TIMING.search(question) else "tarot"

    def degraded(self, facts: list[Fact], question_type: str, question: str, followup: bool):
        """A reading made by code alone: each card, its position and its keywords."""
        from pipeline.render import safety_for

        cards = {card["label"]: card for card in self.session.state["tarot_result"]["cards"]}
        sections = []
        for fact in facts:
            keywords = "、".join((cards[fact.label].get("meaning") or {}).get("keywords") or [])
            body = f"{fact.label}位是{fact.text}。"
            if keywords:
                body += f"这张牌常和{keywords}有关，可以对照你现在的处境想一想。"
            sections.append(
                {"title": f"{fact.label}位：{fact.text}", "body": body, "ref_ids": [fact.alias]}
            )
        listed = "、".join(f"{fact.label}位{fact.text}" for fact in facts)
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
            "evidence": [{"ref_id": fact.alias} for fact in facts],
            "advice": [
                "先对照：把每张牌的关键词和你最近的处境逐条对一对。",
                "再行动：选一件最能落地的小事先做，过一段时间再回头看。",
            ],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了牌面的一般含义。"},
            "safety": safety_for(question),
        }

    def stage(self, name: str, **fields) -> None:
        self.tracer.log(self.session, "pipeline_stage", stage=name, **fields)

    async def planned(self, calls: list[tuple[str, dict]]):
        """Run code-issued calls like a model's; returns (model-visible results, terminal)."""
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
            failed_attempts=self.failed,
        )
        self.step += 1
        ids = {call.id for call in response.tool_calls}
        results = [
            json.loads(m["content"])
            for m in self.session.messages
            if m["role"] == "tool" and m["tool_call_id"] in ids
        ]
        return results, terminal

    async def ask(self, messages: list[dict], purpose: str) -> tuple[str, bool]:
        """(the model's text, whether it was cut off at the output limit)."""
        model = self.runtime.model
        response = await model.chat(messages, [])
        self.session.model_calls += 1
        self.session.total_tokens += response.input_tokens + response.output_tokens
        self.tracer.log(
            self.session,
            "model_response",
            step=self.step,
            purpose=purpose,
            input_tokens=response.input_tokens if response.usage_available else None,
            output_tokens=response.output_tokens if response.usage_available else None,
            usage_available=response.usage_available,
            cached_input_tokens=response.cached_input_tokens,
            reasoning_tokens=response.reasoning_tokens,
            finish_reason=response.finish_reason,
            requested_model=getattr(model, "model", None),
            returned_model=response.model,
            tool_names=[],
        )
        self.step += 1
        # A cut-off draft is a format problem: the repair asks for a shorter one.
        return response.text, response.finish_reason == "length"
