"""consult_specialist: run one specialist in an isolated child session and merge its result."""

import asyncio
import json
import time
from copy import deepcopy
from types import SimpleNamespace

from pydantic import ValidationError

from agents.lite import LiteModel
from agents.schemas import ConsultInput, SpecialistReport
from agents.specialists import CONTINUE_PROMPT, SpecialistSpec
from common.validation import report_matches_profile
from harness.loop import CURRENT_CALL_ID, run_turn
from harness.models import ToolResult, TurnOutcome
from harness.refs import transform
from harness.registry import Tool
from plugins.context import location_choices, range_provenance, resolve_birth_location

FAILURES = {
    "timeout": "专家超时",
    "limit_reached": "专家达到步数或预算上限，未提交有效报告",
    "validation_stalled": "专家连续校验未通过，已停止重复尝试并保留计算",
    "model_error": "专家模型调用失败",
    "usage_unavailable": "模型服务未返回用量",
    "output_truncated": "专家输出达到单次上限，未提交完整报告",
    "error": "专家执行异常",
    "text": "专家未提交结构化报告",
}
# Reading-state values a specialist contributes; all are owned by exactly one system except
# the shared timeframe and knowledge edition.
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
    "timeframe",
    "timeframe_tz",
)
VISIBLE = ("system", "label", "status", "answer", "points", "missing", "confidence")


def project(data: dict) -> dict:
    """The orchestrator sees the structured report, never raw tool output or signals."""
    report = data["report"]
    visible = {k: report[k] for k in VISIBLE}
    if report.get("analysis"):
        visible["analysis"] = report["analysis"]
    if report["status"] == "needs_input":
        visible["needs_input"] = report["needs_input"]
    if report["status"] == "failed":
        visible["failure"] = report["failure"]
    if report.get("retained_previous"):
        visible["retained_previous"] = True
        visible["note"] = "本次重试未成功；该体系此前的有效报告保留不变，可继续引用其ref_id。"
    return {"report": visible}


def stop_on_needs_input(call, result: ToolResult) -> TurnOutcome | None:
    if result.ok and result.data.get("status") == "needs_input":
        return TurnOutcome(
            status="needs_input", text=result.data.get("question", ""), data=result.data
        )
    return None


def conflict(parent: dict, child: dict, system: str) -> str | None:
    """A specialist may not change a value another system's merged result depends on."""
    for owner, contrib in parent.get("specialist_contrib", {}).items():
        if owner == system:
            continue
        for key in ("timeframe", "timeframe_tz"):
            if key in contrib["values"] and child.get(key) not in (None, contrib["values"][key]):
                return "专家计算的时间范围与本记录其它体系不一致"
    return None


def revoke(parent: dict, system: str) -> None:
    """Remove everything one system contributed, so a replaced or stale result leaves no trace."""
    contribs = parent.setdefault("specialist_contrib", {})
    contrib = contribs.pop(system, None)
    parent["signals"] = [s for s in parent["signals"] if s["system"] != system]
    if contrib is None:
        return
    parent["allowed_refs"] -= contrib["allowed_refs"]
    parent["kb_refs"] -= contrib["kb_refs"]
    parent["facts"] = [f for f in parent["facts"] if f not in contrib["facts"]]
    for key in contrib["calculations"]:
        parent.get("calculations", {}).pop(key, None)
    for key, value in contrib["values"].items():
        shared = any(other["values"].get(key) == value for other in contribs.values())
        if parent.get(key) == value and not shared:
            parent.pop(key, None)


def merge(parent: dict, child: dict, system: str) -> None:
    """Fold a successful child's reading state into the parent; the parent stays the writer."""
    seen = {(s["ref_id"], s["theme"]) for s in parent["signals"]}
    parent["signals"].extend(s for s in child["signals"] if (s["ref_id"], s["theme"]) not in seen)
    parent["allowed_refs"].update(child["allowed_refs"])
    parent["kb_refs"].update(child["kb_refs"])
    parent["facts"].extend(f for f in child["facts"] if f not in parent["facts"])
    calculations = child.get("calculations", {})
    parent.setdefault("calculations", {}).update(calculations)
    parent.setdefault("locations", {}).update(child.get("locations", {}))
    values = {key: child[key] for key in SINGLE_VALUE_KEYS if child.get(key) is not None}
    parent.update(values)
    parent.setdefault("specialist_contrib", {})[system] = dict(
        allowed_refs=set(child["allowed_refs"]),
        kb_refs=set(child["kb_refs"]),
        facts=list(child["facts"]),
        calculations=list(calculations),
        values=values,
    )


def computed_results(child, spec: SpecialistSpec) -> list[dict]:
    """Projected results of the plugin's own calculation tools, as the specialist saw them."""
    names = {
        call["id"]: call["function"]["name"]
        for message in child.messages
        for call in message.get("tool_calls") or []
    }
    own = set(spec.registry.tools) - {"lookup_meaning", "submit_report"}
    results = []
    for message in child.messages:
        name = names.get(message.get("tool_call_id"))
        if message["role"] != "tool" or name not in own:
            continue
        payload = json.loads(message["content"])
        if payload["ok"] and payload["data"].get("status") != "needs_input":
            results.append({"tool": name, "data": transform(payload["data"], child, restore=True)})
    return results


class ConsultService:
    def __init__(self, specs: dict[str, SpecialistSpec], model, tracer, limits: dict):
        self.specialist_mode = limits.get("specialist_mode", "agent")
        if self.specialist_mode not in ("agent", "lite"):
            raise ValueError("specialist_mode 必须是 agent 或 lite")
        self.specs = specs
        self.model = model
        self.tracer = tracer
        self.max_steps = limits.get("specialist_max_steps", 6)
        self.token_budget = limits.get("specialist_token_budget", 40000)
        self.timeout = limits.get("specialist_timeout_s", 120)
        self.reserve = limits.get("orchestrator_reserve_tokens", 30000)
        self.semaphore = asyncio.Semaphore(limits.get("max_parallel_specialists", 3))

    def preserve_facts(self, spec: SpecialistSpec, child, parent: dict) -> None:
        """Checkpoint non-repeatable facts independently of reports and batch commit.

        A completed draw must survive cancellation of its report or a sibling consultation.
        Retried reports may create no new tool messages, so retain their previous projection.
        """
        if spec.repeatable:
            return
        own = [s for s in child.state["signals"] if s["system"] == spec.system]
        if not own:
            return
        facts = parent.setdefault("specialist_facts", {})
        results = {r["tool"]: r for r in facts.get(spec.system, {}).get("results", [])}
        results.update({r["tool"]: r for r in computed_results(child, spec)})
        facts[spec.system] = deepcopy(
            dict(
                signals=own,
                allowed_refs=set(child.state["allowed_refs"]),
                kb_refs=set(child.state["kb_refs"]),
                facts=list(child.state["facts"]),
                calculations=dict(child.state.get("calculations", {})),
                values={
                    k: child.state[k]
                    for k in SINGLE_VALUE_KEYS
                    if child.state.get(k) is not None and k not in ("timeframe", "timeframe_tz")
                },
                results=list(results.values()),
            )
        )

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
        resolve_birth_location(args, session)
        if args.location_id and args.location_id not in state.get("locations", {}):
            return "location_id须先由resolve_location解析并确认；" + location_choices(session)
        if args.spread and args.system != "tarot":
            return "spread只用于塔罗专家"
        requested = state.get("requested_spread")
        if args.spread and requested and args.spread != requested:
            return "必须使用用户明确指定的牌阵"
        kept = state.get("specialist_facts", {}).get(args.system, {})
        drawn = (kept.get("values", {}).get("tarot_result") or {}).get("spread")
        if args.spread and drawn and args.spread != drawn:
            return f"本记录已抽牌（{drawn}），重试不能更换牌阵；重抽须用户明确要求并开始新记录"
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

    def child_state(self, spec: SpecialistSpec, args: ConsultInput, parent: dict) -> dict:
        kept = parent.get("specialist_facts", {}).get(spec.system)
        drawn = (kept or {}).get("values", {}).get("tarot_result") or {}
        state = {
            "active_reading_id": parent["active_reading_id"],
            "parent_reading_id": parent.get("parent_reading_id"),
            "question": parent["question"],
            "question_message_index": parent.get("question_message_index", 0),
            "seed": parent.get("seed"),
            "requested_spread": drawn.get("spread")
            or args.spread
            or parent.get("requested_spread"),
            "signals": [],
            "facts": [],
            "allowed_refs": set(),
            "kb_refs": set(),
            "asked_this_turn": True,
            "complete": False,
            "locations": dict(parent.get("locations", {})),
            "location_aliases": dict(parent.get("location_aliases", {})),
        }
        if spec.system == "tarot" and parent.get("picks"):
            state["picks"] = list(parent["picks"])
        if spec.system == "name" and parent.get("bazi_id"):
            # The name specialist may set its names beside the bazi already computed in this
            # reading (counts only); it never computes bazi itself.
            state["bazi_id"] = parent["bazi_id"]
        if args.timeframe:
            state["timeframe_required"] = True
            state["timeframe"] = (args.timeframe.start, args.timeframe.end)
            if args.timeframe.tz:
                state["timeframe_tz"] = args.timeframe.tz
        elif parent.get("timeframe"):
            state["timeframe"] = parent["timeframe"]
            if parent.get("timeframe_tz"):
                state["timeframe_tz"] = parent["timeframe_tz"]
        if kept:
            # A non-repeatable calculation (the draw) survived a failed attempt: restore it so
            # the retry writes its report from the same facts and cannot draw again.
            state["signals"] = [dict(s) for s in kept["signals"]]
            state["allowed_refs"] = set(kept["allowed_refs"])
            state["kb_refs"] = set(kept["kb_refs"])
            state["facts"] = list(kept["facts"])
            state["calculations"] = dict(kept["calculations"])
            state.update(kept["values"])
        return state

    def spawn(self, spec: SpecialistSpec, args: ConsultInput, session):
        profile = {k: session.profile[k] for k in spec.profile_fields if k in session.profile}
        profile["version"] = session.profile.get("version", 0)
        messages = [
            {"role": "system", "content": spec.prompt},
            {
                "role": "system",
                "content": f"日历基准（{session.calendar_timezone}）：{session.calendar_anchor}；"
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
            state=self.child_state(spec, args, session.state),
            profile=profile,
            parent_call_id=CURRENT_CALL_ID.get(),
            budget=None
            if parent_budget is None
            else parent_budget.child(self.token_budget, reserve=self.reserve),
            continue_prompt=CONTINUE_PROMPT,
        )

    def brief(self, spec: SpecialistSpec, args: ConsultInput, session) -> str:
        kept = session.state.get("specialist_facts", {}).get(spec.system)
        return json.dumps(
            {
                "system": args.system,
                "sub_question": args.sub_question,
                "original_question": session.state["question"],
                "timeframe": args.timeframe.model_dump() if args.timeframe else None,
                "location_id": args.location_id,
                "spread": args.spread,
                "existing_results": kept["results"] if kept else None,
                **(
                    {"bazi_id": session.state["bazi_id"]}
                    if spec.system == "name" and session.state.get("bazi_id")
                    else {}
                ),
            },
            ensure_ascii=False,
        )

    def report(
        self, spec, child, outcome: TurnOutcome, latency_ms: float, queue_ms: float
    ) -> SpecialistReport:
        common = dict(
            system=spec.system,
            label=spec.label,
            session_id=child.id,
            latency_ms=round(latency_ms, 3),
            queue_ms=round(queue_ms, 3),
            tokens=child.total_tokens,
            model_calls=child.model_calls,
            profile_version=child.profile.get("version", 0),
            profile_dependencies={field: child.profile.get(field) for field in spec.profile_fields},
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

    def finished(self, session, child, spec, status, **fields) -> None:
        self.tracer.log(child, "session_finished", system=spec.system, status=status)
        self.tracer.log(
            session,
            "specialist_finished",
            system=spec.system,
            child_session_id=child.id,
            call_id=child.parent_call_id,
            status=status,
            **fields,
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
        child = self.spawn(spec, args, session)
        brief = self.brief(spec, args, session)

        def on_result(call, result):
            if result.ok:
                self.preserve_facts(spec, child, state)
            return stop_on_needs_input(call, result)

        # The child's trace exists from the start, so a timeout before its first model
        # response still leaves a complete call tree.
        self.tracer.log(child, "session_started", system=spec.system)
        self.tracer.log(
            session,
            "specialist_queued",
            system=spec.system,
            child_session_id=child.id,
            call_id=child.parent_call_id,
        )
        queued = time.perf_counter()
        started = None
        try:
            async with self.semaphore:
                started = time.perf_counter()
                self.tracer.log(
                    session,
                    "specialist_started",
                    system=spec.system,
                    child_session_id=child.id,
                    call_id=child.parent_call_id,
                )
                try:
                    outcome = await asyncio.wait_for(
                        run_turn(
                            child,
                            brief,
                            LiteModel(self.model, child, spec.system, args)
                            if self.specialist_mode == "lite"
                            and spec.system in ("astro", "bazi", "tarot")
                            else self.model,
                            spec.registry,
                            self.tracer,
                            self.max_steps,
                            self.token_budget,
                            as_evidence=False,
                            admission=True,
                            on_tool_result=on_result,
                        ),
                        self.timeout,
                    )
                except TimeoutError:
                    self.tracer.log(child, "timeout", timeout_s=self.timeout)
                    outcome = TurnOutcome(status="timeout", text="")
                except Exception as exc:
                    self.tracer.log(child, "specialist_error", error_type=type(exc).__name__)
                    outcome = TurnOutcome(status="error", text="")
        except asyncio.CancelledError:
            # The whole request was cancelled (e.g. its wall-clock limit): close the subtree.
            now = time.perf_counter()
            self.finished(
                session,
                child,
                spec,
                "cancelled",
                queue_ms=round(((started or now) - queued) * 1000, 3),
                latency_ms=round((now - started) * 1000, 3) if started else 0.0,
                tokens=child.total_tokens,
                model_calls=child.model_calls,
            )
            raise
        finally:
            # Also cover cancellation before a result is returned to the parent, and a
            # completed sibling whose batch is cancelled before its ordered commit.
            self.preserve_facts(spec, child, state)
            inflight.discard(args.system)
        now = time.perf_counter()
        report = self.report(
            spec, child, outcome, (now - started) * 1000, (started - queued) * 1000
        )
        self.finished(
            session,
            child,
            spec,
            report.status,
            failure=report.failure,
            queue_ms=report.queue_ms,
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

    def commit(self, result: ToolResult, session) -> ToolResult:
        """Apply one consult result to the reading, in call order.

        A valid report replaces the system's earlier contribution atomically. A failed or
        incomplete retry keeps an earlier valid report unless the profile changed since, in
        which case the stale contribution is revoked and the failure becomes effective.
        """
        state = session.state
        data = dict(result.data)
        child_state = data.pop("_child_state", None)
        key = data.pop("_cache_key", None)
        report = data["report"]
        system = report["system"]
        reports = state.setdefault("specialist_reports", {})
        state.setdefault("specialist_attempts", []).append(
            {k: report.get(k) for k in ("system", "status", "failure", "session_id")}
        )
        if result.cached:
            reports[system] = report
            return result.model_copy(update={"data": data})
        if child_state is not None:
            error = conflict(state, child_state, system)
            if error:
                report = {**report, "status": "failed", "failure": error, "signals": []}
            else:
                # Conventions the specialist's calculation saved (e.g. the bazi zishi rule)
                # are part of the report's profile dependencies; the orchestrator's view of
                # the profile must carry them too, or the report would look stale.
                session.profile = {**session.profile, **child_state.get("derived_profile", {})}
                revoke(state, system)
                merge(state, child_state, system)
                state.setdefault("specialist_facts", {}).pop(system, None)
                if key:
                    state.setdefault("consult_cache", {})[key] = report
                reports[system] = report
                data["report"] = report
                return result.model_copy(update={"data": data})
        previous = reports.get(system)
        if (
            previous
            and previous["status"] == "ok"
            and report_matches_profile(previous, session.profile)
        ):
            data["report"] = {**report, "retained_previous": True}
        else:
            revoke(state, system)
            reports[system] = report
            data["report"] = report
        return result.model_copy(update={"data": data})
