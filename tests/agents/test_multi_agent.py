"""Week 4 multi-agent orchestration: isolation, parallelism, failure handling and persistence."""

import asyncio
import json
import time
import uuid
from collections import Counter

import pytest
import yaml

from app import create_runtime
from harness.budget import Budget
from harness.guard import Guard
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from plugins.tarot.draw import draw_tarot
from scripts.trace_tree import build_tree, load, specialist_metrics

ROLE_TOOLS = {"astro": "compute_natal_chart", "bazi": "compute_bazi", "tarot": "draw_tarot"}
BIRTH = "我是男性，1993年8月17日晚上11点20分在北京出生。"
TIMING = BIRTH + "请用占星、八字和三张塔罗看看2026-11-01至2026-11-30适合跳槽吗？"
RANGE = {"start": "2026-11-01", "end": "2026-11-30"}
LOW = {"level": "low", "reason": "释义为未人工审核的自写草稿"}


class RoleModel:
    """Scripted model shared by orchestrator and specialists, routed by the visible tools."""

    def __init__(self, **handlers):
        self.handlers = handlers
        self.calls = Counter()

    async def chat(self, messages, tools):
        names = {t["function"]["name"] for t in tools}
        role = (
            "orchestrator"
            if "start_reading" in names
            or "consult_specialist" in names
            or "submit_reading" in names
            else next(r for r, tool in ROLE_TOOLS.items() if tool in names)
        )
        self.calls[role] += 1
        return await self.handlers[role](messages)


def call(name, **arguments):
    return ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments)


def respond(*calls, tokens=10):
    return ModelResponse(tool_calls=list(calls), input_tokens=tokens, output_tokens=5)


def turn_results(messages):
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    return [json.loads(m["content"]) for m in messages[last_user + 1 :] if m["role"] == "tool"]


def tool_results(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def brief(messages):
    return next(
        json.loads(m["content"])
        for m in messages
        if m["role"] == "user" and m["content"].startswith("{")
    )


def reading(evidence, systems, question_type="timing", reason=LOW["reason"], summary=None):
    return dict(
        question_type=question_type,
        systems_used=systems,
        summary=summary or "2026年11月有条件适合跳槽，前提是先核实岗位与书面条件。",
        evidence=evidence,
        advice=["先核实岗位职责与书面条件。"],
        confidence={"level": "low", "reason": reason},
        safety={"flag": False, "note": ""},
    )


def first_points(results, systems):
    reports = {r["data"]["report"]["system"]: r["data"]["report"] for r in results if r["ok"]}
    return [
        {"ref_id": reports[s]["points"][0]["ref_id"], "reading": reports[s]["points"][0]["text"]}
        for s in systems
    ]


def disclose(merge):
    """Tensions written exactly as the code-computed table states them."""
    return [
        dict(
            theme=t["theme"],
            sides=t["sides"],
            how_to_read="两边体系看法不同，需结合现实条件同时看待。"
            + (f"（日期：{'、'.join(t['windows'])}）" if t.get("windows") else ""),
        )
        for t in merge["tensions"]
    ]


def astro_specialist(barrier=None):
    async def handler(messages):
        b = brief(messages)
        done = tool_results(messages)
        if not done:
            if barrier:
                await barrier("astro")
            if not b["location_id"]:
                return respond(call("compute_natal_chart"))
            return respond(
                call(
                    "compute_natal_chart",
                    birth_local="1993-08-17 23:20",
                    location_id=b["location_id"],
                )
            )
        data = done[-1]["data"]
        if b["timeframe"] and len(done) == 1:
            tf = b["timeframe"]
            return respond(
                call(
                    "compute_transits", chart_id=data["chart_id"], start=tf["start"], end=tf["end"]
                )
            )
        ref = data["interpretations"][0]["ref_id"]
        return respond(
            call(
                "submit_report",
                answer="有条件推进，前提是先核实条件。",
                points=[{"ref_id": ref, "text": "相关配置提示先核实条件、安排沟通再行动。"}],
                confidence=LOW,
            )
        )

    return handler


def bazi_specialist(barrier=None):
    async def handler(messages):
        b = brief(messages)
        done = tool_results(messages)
        if not done:
            if barrier:
                await barrier("bazi")
            if not b["location_id"]:
                return respond(call("compute_bazi", gender="male"))
            return respond(
                call(
                    "compute_bazi",
                    birth_local="1993-08-17 23:20",
                    location_id=b["location_id"],
                    gender="male",
                )
            )
        data = done[-1]["data"]
        if b["timeframe"] and len(done) == 1:
            tf = b["timeframe"]
            return respond(
                call(
                    "compute_bazi_period", bazi_id=data["bazi_id"], start=tf["start"], end=tf["end"]
                )
            )
        ref = data["interpretations"][0]["ref_id"]
        return respond(
            call(
                "submit_report",
                answer="有条件推进，前提是先完善材料。",
                points=[{"ref_id": ref, "text": "十神关系提示先明确职责边界再推进。"}],
                confidence=LOW,
            )
        )

    return handler


def tarot_points(draw):
    return [
        {
            "ref_id": card["ref_id"],
            "text": f"{card['label']}：【{card['name']}】{'逆位' if card['reversed'] else '正位'}。",
        }
        for card in draw["cards"]
    ]


def tarot_specialist(barrier=None, before_draw=None):
    async def handler(messages):
        b = brief(messages)
        done = [r for r in tool_results(messages) if r["ok"] and "cards" in r["data"]]
        if not done:
            if barrier:
                await barrier("tarot")
            if before_draw:
                extra = await before_draw(messages)
                if extra:
                    return extra
            return respond(
                call(
                    "draw_tarot",
                    spread=b["spread"] or "three_card",
                    question=b["original_question"],
                )
            )
        return respond(
            call(
                "submit_report",
                answer="牌面提示先梳理现状，再小步尝试。",
                points=tarot_points(done[0]["data"]),
                confidence=LOW,
            )
        )

    return handler


def make(project, model, user="multi-user", reviewer=False, **limits):
    """Week 4 orchestration tests run without the week 5 reviewer unless asked for."""
    path = project / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["limits"].update(limits)
    config["reviewer"]["enabled"] = reviewer
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return create_runtime(root=project, user_id=user, mode="multi", model=model, seed=42)


def events(runtime):
    return load(runtime.tracer.user_dir(runtime.session.user_id))


def results_of(runtime, role):
    return [e for e in events(runtime) if e["role"] == role and e["event"] == "tool_result"]


def test_multi_mode_tool_tables(project):
    runtime = make(project, RoleModel())
    try:
        orchestrator = set(runtime.registry.tools)
        assert "consult_specialist" in orchestrator
        assert not orchestrator & {
            "compute_natal_chart",
            "compute_transits",
            "compute_bazi",
            "compute_bazi_period",
            "draw_tarot",
            "analyze_name",
            "lookup_dream_symbols",
        }
        # Week 6: daily fortune has no specialist; the orchestrator calls it directly.
        assert "daily_fortune" in orchestrator
        specs = runtime.registry.tools["consult_specialist"].handler.__self__.specs
        assert set(specs) == {"astro", "bazi", "tarot", "name", "dream"}
        assert set(specs["name"].registry.tools) == {
            "analyze_name",
            "lookup_meaning",
            "submit_report",
        }
        assert set(specs["dream"].registry.tools) == {
            "lookup_dream_symbols",
            "lookup_meaning",
            "submit_report",
        }
        assert set(specs["tarot"].registry.tools) == {
            "draw_tarot",
            "lookup_meaning",
            "submit_report",
        }
        assert set(specs["astro"].registry.tools) == {
            "compute_natal_chart",
            "compute_transits",
            "lookup_meaning",
            "submit_report",
        }
        assert "name" not in specs["bazi"].profile_fields
    finally:
        runtime.close()


async def test_parallel_consult_merges_persists_and_traces(project):
    arrived = {role: asyncio.Event() for role in ROLE_TOOLS}

    async def barrier(role):
        # Serial execution would wait here forever: every specialist must be running at once.
        arrived[role].set()
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in arrived.values())), 5)

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question=TIMING))
        if len(done) == 1:
            return respond(call("resolve_location", query="北京"))
        if len(done) == 2:
            location = done[1]["data"]["location"]["location_id"]
            return respond(
                call(
                    "consult_specialist",
                    system="astro",
                    sub_question="2026年11月行运是否支持求职",
                    timeframe=RANGE,
                    location_id=location,
                ),
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="2026年11月流月是否支持求职",
                    timeframe=RANGE,
                    location_id=location,
                ),
                call(
                    "consult_specialist",
                    system="tarot",
                    sub_question="下个月跳槽的反思线索",
                    spread="three_card",
                ),
            )
        if len(done) == 5:
            # Week 5: with several systems the cross-system table is read before writing.
            return respond(call("merge_signals"))
        systems = ["astro", "bazi", "tarot"]
        payload = reading(first_points(done[2:5], systems), systems)
        payload["tensions"] = disclose(done[5]["data"]["merge"])
        return respond(call("submit_reading", **payload))

    model = RoleModel(
        orchestrator=orchestrator,
        astro=astro_specialist(barrier),
        bazi=bazi_specialist(barrier),
        tarot=tarot_specialist(barrier),
    )
    runtime = make(project, model)
    try:
        outcome = await runtime.turn(TIMING)
        assert outcome.status == "submit_reading", outcome.text
        state = runtime.session.state
        reports = state["specialist_reports"]
        assert {s: r["status"] for s, r in reports.items()} == dict.fromkeys(reports, "ok")
        assert set(reports) == {"astro", "bazi", "tarot"}
        # Results were merged into the orchestrator's reading in call order.
        assert state["chart_id"] and state["bazi_id"] and state["tarot_result"]["spread"]
        assert {s["system"] for s in state["signals"]} == {"astro", "bazi", "tarot"}
        assert state["timeframe"] == ("2026-11-01", "2026-11-30")
        tool_messages = [m["tool_call_id"] for m in runtime.session.messages if m["role"] == "tool"]
        consult_ids = [
            c["id"]
            for m in runtime.session.messages
            if m.get("tool_calls")
            for c in m["tool_calls"]
            if c["function"]["name"] == "consult_specialist"
        ]
        assert [i for i in tool_messages if i in consult_ids] == consult_ids
        saved = runtime.store.get_reading(runtime.session.user_id, state["active_reading_id"])
        assert saved["mode"] == "multi"
        stored = runtime.store.specialist_reports(runtime.session.user_id, saved["reading_id"])
        assert set(stored) == {"astro", "bazi", "tarot"}
        assert all("signals" not in r and r["signal_refs"] for r in stored.values())
        tree = build_tree(events(runtime), saved["reading_id"])
        assert tree["problems"] == []
        metrics = specialist_metrics(events(runtime))
        assert metrics["max_concurrent_specialists"] == 3
        assert metrics["out_of_scope_attempts"] == 0
        assert metrics["report_submissions"] == metrics["report_submissions_accepted"] == 3
        (root,) = tree["roots"]
        assert root["role"] == "orchestrator"
        assert sorted(c["role"] for c in root["children"]) == ["astro", "bazi", "tarot"]
        assert {c["parent_call_id"] for c in root["children"]} == set(consult_ids)
    finally:
        runtime.close()


async def test_brief_is_context_not_user_evidence(project):
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用八字看看我的工作方式"))
        if len(done) == 1:
            # The orchestrator invents a birth date the user never gave.
            return respond(
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="用户1990年1月1日早上8点出生在北京，男性，请排八字",
                )
            )
        return respond(call("ask_user", question="请提供出生日期、时间与地点。"))

    async def bazi(messages):
        done = tool_results(messages)
        if not done:
            return respond(
                call(
                    "compute_bazi",
                    birth_local="1990-01-01 08:00",
                    tz="Asia/Shanghai",
                    lon=116.4,
                    gender="male",
                )
            )
        return ModelResponse(text="无法计算", input_tokens=1, output_tokens=1)

    runtime = make(project, RoleModel(orchestrator=orchestrator, bazi=bazi))
    try:
        outcome = await runtime.turn("用八字看看我的工作方式。")
        assert outcome.status == "ask_user"
        computed = [e for e in results_of(runtime, "bazi") if e["call"]["name"] == "compute_bazi"]
        assert computed[0]["result"]["code"] == "validation_failed"
        assert "出生日期" in computed[0]["result"]["error"]
        assert runtime.session.state["specialist_reports"]["bazi"]["status"] == "failed"
        assert runtime.session.user_messages == ["用八字看看我的工作方式。"]
    finally:
        runtime.close()


async def test_run_turn_brief_does_not_enter_evidence(runtime, scripted_model):
    model = scripted_model([ModelResponse(text="好的")])
    before = list(runtime.session.user_messages)
    outcome = await run_turn(
        runtime.session,
        "编排者写的子问题",
        model,
        runtime.registry,
        runtime.tracer,
        as_evidence=False,
    )
    assert outcome.status == "text"
    assert runtime.session.user_messages == before
    assert runtime.session.messages[-2] == {"role": "user", "content": "编排者写的子问题"}


def tarot_only_orchestrator(final=None, consult_args=None):
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用三张塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(
                call(
                    "consult_specialist",
                    **(consult_args or dict(system="tarot", sub_question="最近工作状态的反思线索")),
                )
            )
        if final:
            return await final(done)
        return respond(
            call(
                "submit_reading",
                **reading(
                    first_points(done[1:2], ["tarot"]),
                    ["tarot"],
                    question_type="tarot",
                    summary="建议先梳理现状，再做小步尝试。",
                ),
            )
        )

    return orchestrator


async def test_specialist_cannot_cross_tools_or_partitions(project):
    async def probe(messages):
        if not tool_results(messages):
            return respond(
                call("compute_bazi", gender="male"),
                call("lookup_meaning", system="bazi", kind="ten_god", key="七杀"),
            )
        return None

    model = RoleModel(
        orchestrator=tarot_only_orchestrator(), tarot=tarot_specialist(before_draw=probe)
    )
    runtime = make(project, model)
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        codes = {e["call"]["name"]: e["result"]["code"] for e in results_of(runtime, "tarot")}
        assert codes["compute_bazi"] == "unknown_tool"
        assert codes["lookup_meaning"] == "partition_denied"
        metrics = specialist_metrics(events(runtime))
        assert metrics["out_of_scope_attempts"] == 2
        assert metrics["statuses"] == {"ok": 1}
        assert runtime.session.state["specialist_reports"]["tarot"]["status"] == "ok"
    finally:
        runtime.close()


async def test_report_must_cite_own_computed_refs(project):
    attempts = []

    async def tarot(messages):
        done = [r for r in tool_results(messages) if r["ok"] and "cards" in r["data"]]
        if not done:
            return respond(call("draw_tarot", spread="three_card", question="q"))
        points = tarot_points(done[0]["data"])
        attempts.append(len(attempts))
        if len(attempts) == 1:
            bad = [{"ref_id": "astro:fake:Sun:Leo", "text": "伪造引用"}]
            return respond(call("submit_report", answer="x", points=bad, confidence=LOW))
        if len(attempts) == 2:
            card = done[0]["data"]["cards"][0]
            wrong = "正位" if card["reversed"] else "逆位"
            flipped = [{"ref_id": card["ref_id"], "text": f"【{card['name']}】{wrong}。"}]
            return respond(call("submit_report", answer="x", points=flipped, confidence=LOW))
        return respond(call("submit_report", answer="先梳理现状。", points=points, confidence=LOW))

    runtime = make(project, RoleModel(orchestrator=tarot_only_orchestrator(), tarot=tarot))
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        submits = [e for e in results_of(runtime, "tarot") if e["call"]["name"] == "submit_report"]
        assert [s["result"]["ok"] for s in submits] == [False, False, True]
        assert "ref_id" in submits[0]["result"]["error"]
        assert "方向" in submits[1]["result"]["error"]
    finally:
        runtime.close()


async def test_failed_specialist_is_isolated_and_disclosed(project):
    submissions = []

    async def final(done):
        reports = {r["data"]["report"]["system"]: r["data"]["report"] for r in done if r["ok"]}
        assert reports["astro"]["status"] == "failed"
        evidence = first_points(done, ["tarot"])
        attempt = len(submissions)
        submissions.append(attempt)
        if attempt == 0:
            payload = reading(evidence, ["tarot", "astro"], question_type="tarot")
        elif attempt == 1:
            payload = reading(evidence, ["tarot"], question_type="tarot")
        else:
            reason = "西方占星专家未完成，本次只用塔罗；释义为未人工审核的自写草稿"
            payload = reading(evidence, ["tarot"], question_type="tarot", reason=reason)
        payload["summary"] = "建议先梳理现状，再做小步尝试。"
        return respond(call("submit_reading", **payload))

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用占星和三张塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(
                call("consult_specialist", system="astro", sub_question="工作方式"),
                call("consult_specialist", system="tarot", sub_question="工作状态"),
            )
        return await final([r for r in done if "report" in r.get("data", {})])

    async def broken(messages):
        raise RuntimeError("specialist model down")

    model = RoleModel(orchestrator=orchestrator, astro=broken, tarot=tarot_specialist())
    runtime = make(project, model)
    try:
        outcome = await runtime.turn("用占星和三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        orchestrator_results = [
            e for e in results_of(runtime, "orchestrator") if e["call"]["name"] == "submit_reading"
        ]
        # The failed system is dropped and disclosed by code instead of a rejection round.
        assert [e["result"]["ok"] for e in orchestrator_results] == [True]
        output = outcome.data["reading"]
        assert output["systems_used"] == ["tarot"]
        assert "西方占星" in output["confidence"]["reason"]
        assert "专家模型调用失败" in output["confidence"]["reason"]
        stored = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
        assert stored["output_json"]["systems_used"] == ["tarot"]
        saved = runtime.store.specialist_reports(
            runtime.session.user_id, runtime.session.state["active_reading_id"]
        )
        assert saved["astro"]["status"] == "failed"
        assert saved["astro"]["failure"] == "专家模型调用失败"
    finally:
        runtime.close()


async def test_specialist_timeout_is_a_failed_report(project):
    async def slow(messages):
        if not tool_results(messages):
            await asyncio.sleep(5)
        return respond(call("draw_tarot", spread="three_card", question="q"))

    async def final(done):
        return respond(call("ask_user", question="塔罗专家超时，要稍后再试吗？"))

    model = RoleModel(orchestrator=tarot_only_orchestrator(final=final), tarot=slow)
    runtime = make(project, model, specialist_timeout_s=0.2)
    try:
        started = time.perf_counter()
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert time.perf_counter() - started < 4
        assert outcome.status == "ask_user"
        report = runtime.session.state["specialist_reports"]["tarot"]
        assert (report["status"], report["failure"]) == ("failed", "专家超时")
        assert not runtime.session.state.get("tarot_drawn")
    finally:
        runtime.close()


async def test_needs_input_is_asked_once_and_never_cached(project):
    asked = []

    async def orchestrator(messages):
        done = turn_results(messages)
        last_user = [m for m in messages if m["role"] == "user"][-1]["content"]
        if "1993" not in last_user:
            if not done:
                return respond(call("start_reading", question="用占星和八字看看我的性格"))
            if len(done) == 1:
                return respond(
                    call("consult_specialist", system="astro", sub_question="性格"),
                    call("consult_specialist", system="bazi", sub_question="性格"),
                )
            questions = [r["data"]["report"]["needs_input"]["question"] for r in done[1:]]
            asked.append(questions)
            return respond(call("ask_user", question="；".join(dict.fromkeys(questions))))
        if not done:
            return respond(call("resolve_location", query="北京"))
        if len(done) == 1:
            location = done[0]["data"]["location"]["location_id"]
            return respond(
                call(
                    "consult_specialist", system="astro", sub_question="性格", location_id=location
                ),
                call(
                    "consult_specialist", system="bazi", sub_question="性格", location_id=location
                ),
            )
        if len(done) == 3:
            return respond(call("merge_signals"))
        payload = reading(
            first_points(done[1:3], ["astro", "bazi"]),
            ["astro", "bazi"],
            question_type="trait",
            summary="更适合先尝试结构清楚的工作方式，再用实际反馈验证。",
        )
        payload["tensions"] = disclose(done[3]["data"]["merge"])
        return respond(call("submit_reading", **payload))

    model = RoleModel(orchestrator=orchestrator, astro=astro_specialist(), bazi=bazi_specialist())
    runtime = make(project, model)
    try:
        first = await runtime.turn("我是男性。用占星和八字看看我的性格。")
        assert first.status == "ask_user"
        reports = runtime.session.state["specialist_reports"]
        assert {r["status"] for r in reports.values()} == {"needs_input"}
        assert len(asked) == 1
        calls_before = dict(model.calls)
        second = await runtime.turn("1993年8月17日晚上11点20分在北京出生。")
        assert second.status == "submit_reading", second.text
        assert model.calls["astro"] > calls_before["astro"]
        assert model.calls["bazi"] > calls_before["bazi"]
        assert {r["status"] for r in reports.values()} == {"ok"}
    finally:
        runtime.close()


async def test_same_step_conflicts_are_rejected(project):
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="看看我的运势"))
        if len(done) == 1:
            return respond(
                call("consult_specialist", system="tarot", sub_question="a"),
                call("consult_specialist", system="tarot", sub_question="b"),
                call(
                    "consult_specialist",
                    system="astro",
                    sub_question="c",
                    timeframe={"start": "2026-11-01", "end": "2026-11-30"},
                ),
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="d",
                    timeframe={"start": "2026-12-01", "end": "2026-12-31"},
                ),
            )
        return respond(call("ask_user", question="继续吗？"))

    async def unavailable(messages):
        return ModelResponse(text="未计算", input_tokens=1, output_tokens=1)

    model = RoleModel(
        orchestrator=orchestrator, tarot=tarot_specialist(), astro=unavailable, bazi=unavailable
    )
    runtime = make(project, model, specialist_max_steps=1)
    try:
        await runtime.turn("看看我的运势。")
        consults = [
            e
            for e in results_of(runtime, "orchestrator")
            if e["call"]["name"] == "consult_specialist"
        ]
        codes = [e["result"]["code"] for e in consults]
        assert codes == [None, "duplicate_consult", None, "timeframe_conflict"]
    finally:
        runtime.close()


async def test_tarot_is_drawn_once_per_reading(project):
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用三张塔罗看看最近的工作状态"))
        if len(done) in (1, 2):
            return respond(call("consult_specialist", system="tarot", sub_question="状态"))
        assert done[2]["cached"] is True
        return respond(
            call(
                "submit_reading",
                **reading(
                    first_points(done[1:2], ["tarot"]),
                    ["tarot"],
                    question_type="tarot",
                    summary="建议先梳理现状，再做小步尝试。",
                ),
            )
        )

    model = RoleModel(orchestrator=orchestrator, tarot=tarot_specialist())
    runtime = make(project, model)
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        draws = [e for e in results_of(runtime, "tarot") if e["call"]["name"] == "draw_tarot"]
        assert len(draws) == 1
    finally:
        runtime.close()


async def test_tarot_specialist_draws_the_chosen_positions(project):
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用三张塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(call("consult_specialist", system="tarot", sub_question="状态"))
        return respond(
            call(
                "submit_reading",
                **reading(
                    first_points(done[1:2], ["tarot"]),
                    ["tarot"],
                    question_type="tarot",
                    summary="建议先梳理现状，再做小步尝试。",
                ),
            )
        )

    runtime = make(project, RoleModel(orchestrator=orchestrator, tarot=tarot_specialist()))
    try:
        runtime.session.pending_picks = (12, 40, 63)
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        (draw,) = [e for e in results_of(runtime, "tarot") if e["call"]["name"] == "draw_tarot"]
        data = draw["result"]["data"]
        assert data["picks"] == [12, 40, 63]
        expected = draw_tarot(data["spread"], data["question"], data["seed"], [12, 40, 63])
        assert [c["card_id"] for c in data["cards"]] == [c["card_id"] for c in expected["cards"]]
    finally:
        runtime.close()


async def test_followup_does_not_consult_specialists(project):
    runtime = make(project, RoleModel())
    try:
        runtime.session.append_user("第二张牌什么意思？")
        runtime.session.start_reading("q")
        runtime.session.state["response_mode"] = "followup"
        _, result, _ = Guard(runtime.registry).check(
            ToolCall(
                id="x",
                name="consult_specialist",
                arguments={"system": "tarot", "sub_question": "q"},
            ),
            runtime.session,
        )
        assert result.code == "validation_failed" and "read_reading" in result.error
    finally:
        runtime.close()


async def test_demo_model_runs_multi_mode_end_to_end(project):
    runtime = create_runtime(root=project, user_id="demo-multi", provider="demo", mode="multi")
    try:
        outcome = await runtime.turn("A 公司还是 B 公司的 offer？")
        assert outcome.status == "submit_reading", outcome.text
        reading_id = runtime.session.state["active_reading_id"]
        assert runtime.store.get_reading("demo-multi", reading_id)["mode"] == "multi"
        followup = await runtime.turn("第二张牌具体什么意思？")
        assert followup.status == "submit_reading"
        assert build_tree(events(runtime), reading_id)["problems"] == []
    finally:
        runtime.close()


def test_budget_propagates_reserve_and_deadline():
    root = Budget(100)
    child = root.child(80, reserve=30)
    leaf = Budget(50, parent=child)
    assert leaf.remaining() == 50
    leaf.charge(40)
    assert (root.used, child.used, leaf.remaining()) == (40, 40, 10)
    assert child.remaining() == min(80 - 40, (100 - 40) - 30)
    leaf.charge(30)
    assert leaf.remaining() < 0 and root.remaining() == 30
    expired = Budget(10, deadline=time.monotonic() - 1)
    assert Budget(10, parent=expired).expired()


@pytest.mark.parametrize("mode", ["single", "multi"])
def test_config_modes_and_reviewer_guard(project, mode):
    runtime = create_runtime(root=project, provider="demo", mode=mode)
    try:
        assert runtime.mode == mode
        assert ("consult_specialist" in runtime.registry.tools) is (mode == "multi")
    finally:
        runtime.close()
    with pytest.raises(ValueError):
        create_runtime(root=project, provider="demo", mode="parallel")


async def test_single_mode_has_no_wall_clock_deadline(project, scripted_model):
    model = scripted_model([ModelResponse(text="你好")])
    runtime = create_runtime(root=project, user_id="single-deadline", model=model, mode="single")
    try:
        await runtime.turn("你好")
        assert runtime.session.budget.deadline is None
    finally:
        runtime.close()
    multi = make(project, RoleModel(orchestrator=lambda m: None), user="multi-deadline")
    try:
        multi.model = scripted_model([ModelResponse(text="你好")])
        await multi.turn("你好")
        assert multi.session.budget.deadline is not None
    finally:
        multi.close()
