"""consult_specialist: run one specialist in an isolated child session and merge its result."""

import asyncio
import json
import time
from types import SimpleNamespace

from pydantic import ValidationError

from agents.schemas import ConsultInput, SpecialistReport
from agents.specialists import CONTINUE_PROMPT, SpecialistSpec
from harness.loop import CURRENT_CALL_ID, run_turn
from harness.models import ToolResult, TurnOutcome
from harness.registry import Tool
from plugins.context import range_provenance

FAILURES = {
    "timeout": "专家超时",
    "limit_reached": "专家达到步数或预算上限，未提交有效报告",
    "model_error": "专家模型调用失败",
    "usage_unavailable": "模型服务未返回用量",
    "error": "专家执行异常",
    "text": "专家未提交结构化报告",
}
SINGLE_VALUE_KEYS = (
    "natal_result",
    "transit_result",
    "bazi_result",
    "bazi_period_result",
    "tarot_result",
    "chart_id",
    "bazi_id",
    "kb_version",
    "tarot_drawn",
)
VISIBLE = ("system", "label", "status", "answer", "points", "missing", "confidence")


def project(data: dict) -> dict:
    """The orchestrator sees the structured report, never raw tool output or signals."""
    report = data["report"]
    visible = {k: report[k] for k in VISIBLE}
    if report["status"] == "needs_input":
        visible["needs_input"] = report["needs_input"]
    if report["status"] == "failed":
        visible["failure"] = report["failure"]
    return {"report": visible}


def stop_on_needs_input(call, result: ToolResult) -> TurnOutcome | None:
    if result.ok and result.data.get("status") == "needs_input":
        return TurnOutcome(
            status="needs_input", text=result.data.get("question", ""), data=result.data
        )
    return None


def merge(parent: dict, child: dict) -> str | None:
    """Fold a successful child's reading state into the parent; the parent stays the writer."""
    for key in ("timeframe", "timeframe_tz"):
        if parent.get(key) and child.get(key) and parent[key] != child[key]:
            return "专家计算的时间范围与本记录已有范围不一致"
    seen = {(s["ref_id"], s["theme"]) for s in parent["signals"]}
    parent["signals"].extend(s for s in child["signals"] if (s["ref_id"], s["theme"]) not in seen)
    parent["allowed_refs"].update(child["allowed_refs"])
    parent["kb_refs"].update(child["kb_refs"])
    parent["facts"].extend(f for f in child["facts"] if f not in parent["facts"])
    parent.setdefault("calculations", {}).update(child.get("calculations", {}))
    parent.setdefault("locations", {}).update(child.get("locations", {}))
    for key in (*SINGLE_VALUE_KEYS, "timeframe", "timeframe_tz"):
        if child.get(key) is not None:
            parent[key] = child[key]
    return None


class ConsultService:
    def __init__(self, specs: dict[str, SpecialistSpec], model, tracer, limits: dict):
        self.specs = specs
        self.model = model
        self.tracer = tracer
        self.max_steps = limits.get("specialist_max_steps", 6)
        self.token_budget = limits.get("specialist_token_budget", 40000)
        self.timeout = limits.get("specialist_timeout_s", 120)
        self.reserve = limits.get("orchestrator_reserve_tokens", 30000)
        self.semaphore = asyncio.Semaphore(limits.get("max_parallel_specialists", 3))

    def tool(self) -> Tool:
        names = "、".join(f"{s.system}（{s.label}）" for s in self.specs.values())
        return Tool(
            "consult_specialist",
            f"咨询体系专家：{names}。同一步可并行咨询多位专家；专家在隔离子会话中计算，"
            "返回结构化报告（status为ok/needs_input/failed）。",
            ConsultInput,
            self.consult,
            roles=frozenset({"orchestrator"}),
            dependency="active_reading_id",
            idempotent=False,
            parallel_safe=True,
            validator=self.validate,
            commit=self.commit,
            model_result=project,
        )

    def validate(self, args: ConsultInput, session) -> str | None:
        state = session.state
        if args.system not in self.specs:
            return f"未接入该体系专家，可用：{'、'.join(self.specs)}"
        if state.get("response_mode") == "followup":
            return "追问请用read_reading读取原记录作答，不再咨询专家或重新计算"
        if args.location_id and args.location_id not in state.get("locations", {}):
            return "location_id须先由resolve_location解析并确认"
        if args.spread and args.system != "tarot":
            return "spread只用于塔罗专家"
        requested = state.get("requested_spread")
        if args.spread and requested and args.spread != requested:
            return "必须使用用户明确指定的牌阵"
        if args.timeframe:
            error = range_provenance(
                SimpleNamespace(
                    start=args.timeframe.start, end=args.timeframe.end, tz=args.timeframe.tz
                ),
                session,
            )
            if error:
                return error
        return None

    def cache_key(self, args: ConsultInput, session) -> str:
        spec = self.specs[args.system]
        # A clarification or profile change must re-run the specialist; a repeat within the
        # same turn reuses its report. Tarot is drawn once per reading, whatever is asked.
        context = (
            []
            if not spec.repeatable
            else [len(session.user_messages), session.profile.get("version", 0)]
        )
        payload = args.model_dump(mode="json") if spec.repeatable else {"system": args.system}
        return json.dumps([payload, context], ensure_ascii=False, sort_keys=True)

    def child_state(self, args: ConsultInput, parent: dict) -> dict:
        state = {
            "active_reading_id": parent["active_reading_id"],
            "parent_reading_id": parent.get("parent_reading_id"),
            "question": parent["question"],
            "question_message_index": parent.get("question_message_index", 0),
            "seed": parent.get("seed"),
            "requested_spread": args.spread or parent.get("requested_spread"),
            "signals": [],
            "facts": [],
            "allowed_refs": set(),
            "kb_refs": set(),
            "asked_this_turn": True,
            "complete": False,
            "locations": dict(parent.get("locations", {})),
            "location_aliases": dict(parent.get("location_aliases", {})),
        }
        if args.timeframe:
            state["timeframe_required"] = True
            state["timeframe"] = (args.timeframe.start, args.timeframe.end)
            if args.timeframe.tz:
                state["timeframe_tz"] = args.timeframe.tz
        elif parent.get("timeframe"):
            state["timeframe"] = parent["timeframe"]
            if parent.get("timeframe_tz"):
                state["timeframe_tz"] = parent["timeframe_tz"]
        return state

    def spawn(self, spec: SpecialistSpec, args: ConsultInput, session):
        profile = {k: session.profile[k] for k in spec.profile_fields if k in session.profile}
        profile["version"] = session.profile.get("version", 0)
        messages = [
            {"role": "system", "content": spec.prompt},
            {
                "role": "system",
                "content": f"日历基准（Asia/Shanghai）：{session.calendar_anchor}；"
                "按子问题给出的日期范围计算，不猜系统月份。",
            },
            {
                "role": "system",
                "content": "本体系可用画像：" + json.dumps(profile, ensure_ascii=False),
            },
        ]
        parent_budget = session.turn_budget
        return session.spawn(
            spec.system,
            spec.system,
            messages=messages,
            state=self.child_state(args, session.state),
            profile=profile,
            parent_call_id=CURRENT_CALL_ID.get(),
            budget=None
            if parent_budget is None
            else parent_budget.child(self.token_budget, reserve=self.reserve),
            continue_prompt=CONTINUE_PROMPT,
        )

    def brief(self, args: ConsultInput, session) -> str:
        return json.dumps(
            {
                "system": args.system,
                "sub_question": args.sub_question,
                "original_question": session.state["question"],
                "timeframe": args.timeframe.model_dump() if args.timeframe else None,
                "location_id": args.location_id,
                "spread": args.spread,
            },
            ensure_ascii=False,
        )

    def report(self, spec, child, outcome: TurnOutcome, latency_ms: float) -> SpecialistReport:
        common = dict(
            system=spec.system,
            label=spec.label,
            session_id=child.id,
            latency_ms=round(latency_ms, 3),
            tokens=child.total_tokens,
            model_calls=child.model_calls,
        )
        if outcome.status == "submit_report":
            own = [s for s in child.state["signals"] if s["system"] == spec.system]
            try:
                return SpecialistReport(
                    status="ok", signals=own, **outcome.data["report"], **common
                )
            except (ValidationError, KeyError, TypeError):
                return SpecialistReport(status="failed", failure="专家报告不符合schema", **common)
        if outcome.status == "needs_input":
            data = outcome.data
            return SpecialistReport(
                status="needs_input",
                needs_input=dict(
                    code=data.get("code"),
                    question=data.get("question"),
                    candidates=data.get("candidates", []),
                ),
                **common,
            )
        return SpecialistReport(
            status="failed", failure=FAILURES.get(outcome.status, outcome.status), **common
        )

    async def consult(self, args: ConsultInput, session) -> ToolResult:
        spec = self.specs[args.system]
        state = session.state
        key = self.cache_key(args, session)
        cached = state.setdefault("consult_cache", {}).get(key)
        if cached:
            return ToolResult(data={"report": cached}, cached=True)
        # Everything up to the first await runs before any sibling call starts, so the
        # in-flight and timeframe bookkeeping is ordered by the model's call order.
        inflight = state.setdefault("consult_inflight", set())
        if args.system in inflight:
            return ToolResult.failure("duplicate_consult", "本步已在咨询该专家，请等待其报告")
        if args.timeframe:
            requested = (args.timeframe.start, args.timeframe.end)
            if state.setdefault("consult_timeframe", requested) != requested:
                return ToolResult.failure(
                    "timeframe_conflict", "同一记录内各专家必须使用相同时间范围"
                )
        inflight.add(args.system)
        try:
            child = self.spawn(spec, args, session)
            self.tracer.log(
                session,
                "specialist_started",
                system=spec.system,
                child_session_id=child.id,
                call_id=child.parent_call_id,
            )
            started = time.perf_counter()
            async with self.semaphore:
                try:
                    outcome = await asyncio.wait_for(
                        run_turn(
                            child,
                            self.brief(args, session),
                            self.model,
                            spec.registry,
                            self.tracer,
                            self.max_steps,
                            self.token_budget,
                            as_evidence=False,
                            on_tool_result=stop_on_needs_input,
                        ),
                        self.timeout,
                    )
                except TimeoutError:
                    outcome = TurnOutcome(status="timeout", text="")
                except Exception as exc:
                    self.tracer.log(child, "specialist_error", error_type=type(exc).__name__)
                    outcome = TurnOutcome(status="error", text="")
            report = self.report(spec, child, outcome, (time.perf_counter() - started) * 1000)
            self.tracer.log(
                session,
                "specialist_finished",
                system=spec.system,
                child_session_id=child.id,
                call_id=child.parent_call_id,
                status=report.status,
                failure=report.failure,
                latency_ms=report.latency_ms,
                tokens=report.tokens,
                model_calls=report.model_calls,
            )
            return ToolResult(
                data={
                    "report": report.model_dump(mode="json"),
                    "_child_state": child.state if report.status == "ok" else None,
                    "_cache_key": key,
                }
            )
        finally:
            inflight.discard(args.system)

    def commit(self, result: ToolResult, session) -> ToolResult:
        data = dict(result.data)
        child_state = data.pop("_child_state", None)
        key = data.pop("_cache_key", None)
        report = data["report"]
        if child_state is not None:
            error = merge(session.state, child_state)
            if error:
                report = {**report, "status": "failed", "failure": error, "signals": []}
                data["report"] = report
            elif key:
                session.state.setdefault("consult_cache", {})[key] = report
        session.state.setdefault("specialist_reports", {})[report["system"]] = report
        return result.model_copy(update={"data": data})
