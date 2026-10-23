"""Regressions for the PR #2 review: retries, budget admission, deadlines, kept draws, traces
and metric definitions. Each test fails when the fix it covers is reverted."""

import asyncio
import dataclasses
import time

import yaml

from app import create_runtime
from common.schemas import Reading
from common.validation import validate_reading
from harness.guard import Guard
from harness.models import ModelResponse, ToolCall
from scripts.trace_tree import build_tree, specialist_metrics
from tests.agents.test_multi_agent import (
    BIRTH,
    LOW,
    ROLE_TOOLS,
    RoleModel,
    bazi_specialist,
    brief,
    call,
    events,
    make,
    reading,
    respond,
    tarot_points,
    tarot_specialist,
    tool_results,
    turn_results,
)


def evidence_of(report, index=0):
    point = report["points"][index]
    return {"ref_id": point["ref_id"], "reading": point["text"]}


def reports_in(done):
    return [d["data"]["report"] for d in done if d["ok"] and "report" in d.get("data", {})]


def draws(runtime):
    return [
        e
        for e in events(runtime)
        if e["event"] == "tool_result" and e["call"]["name"] == "draw_tarot" and e["result"]["ok"]
    ]


async def invoke(runtime, name, **arguments):
    args, result, _ = Guard(runtime.registry).check(
        ToolCall(id="probe", name=name, arguments=arguments), runtime.session
    )
    return result if result is not None else await runtime.registry.run(name, args, runtime.session)


async def test_failed_retry_keeps_earlier_valid_report(project):
    """Review item 1: a failed retry must not leave the reading unsubmittable."""

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用八字和塔罗看看我的工作方式"))
        if len(done) == 1:
            return respond(call("resolve_location", query="北京"))
        location = done[1]["data"]["location"]["location_id"]
        if len(done) == 2:
            return respond(
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="工作方式",
                    location_id=location,
                )
            )
        if len(done) == 3:
            return respond(
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="再细看工作方式",
                    location_id=location,
                ),
                call("consult_specialist", system="tarot", sub_question="工作状态"),
            )
        first, retry, tarot = reports_in(done[2:])
        assert retry["status"] == "failed" and retry["retained_previous"] is True
        return respond(
            call(
                "submit_reading",
                **reading(
                    [evidence_of(first), evidence_of(tarot)],
                    ["bazi", "tarot"],
                    question_type="trait",
                    summary="可以先尝试职责清楚的工作方式，再用实际反馈验证。",
                ),
            )
        )

    base = bazi_specialist()

    async def bazi(messages):
        if brief(messages)["sub_question"] == "再细看工作方式":
            raise RuntimeError("specialist model down")
        return await base(messages)

    model = RoleModel(orchestrator=orchestrator, bazi=bazi, tarot=tarot_specialist())
    runtime = make(project, model)
    try:
        outcome = await runtime.turn(BIRTH + "用八字和塔罗看看我的工作方式。")
        assert outcome.status == "submit_reading", outcome.text
        state = runtime.session.state
        assert state["specialist_reports"]["bazi"]["status"] == "ok"
        assert [a["status"] for a in state["specialist_attempts"]] == ["ok", "failed", "ok"]
        assert {s["system"] for s in state["signals"]} == {"bazi", "tarot"}
    finally:
        runtime.close()


async def test_profile_correction_revokes_then_replaces_atomically(project):
    """Review item 1: corrected data invalidates the old result; the new one fully replaces it."""
    failures = [True]

    async def orchestrator(messages):
        done = turn_results(messages)
        last = [m for m in messages if m["role"] == "user"][-1]["content"]
        if "更正" in last:
            if not done:
                return respond(
                    call(
                        "update_profile",
                        field="birth_local_dt",
                        value="1993-08-17 22:20",
                        evidence="1993年8月17日晚上10点20分出生",
                    )
                )
            if len(done) == 1:
                location = next(iter(runtime.session.state["locations"]))
                return respond(
                    call(
                        "consult_specialist",
                        system="bazi",
                        sub_question="工作方式",
                        location_id=location,
                    )
                )
            return respond(call("ask_user", question="八字暂时无法完成，要再试一次吗？"))
        if "再试" in last:
            if not done:
                location = next(iter(runtime.session.state["locations"]))
                return respond(
                    call(
                        "consult_specialist",
                        system="bazi",
                        sub_question="工作方式",
                        location_id=location,
                    )
                )
            return respond(
                call(
                    "submit_reading",
                    **reading(
                        [evidence_of(done[0]["data"]["report"])],
                        ["bazi"],
                        question_type="trait",
                        summary="可以先尝试职责清楚的工作方式，再用实际反馈验证。",
                    ),
                )
            )
        if not done:
            return respond(call("start_reading", question="用八字看看我的工作方式"))
        if len(done) == 1:
            return respond(
                call(
                    "update_profile",
                    field="birth_local_dt",
                    value="1993-08-17 23:20",
                    evidence="1993年8月17日晚上11点20分",
                )
            )
        if len(done) == 2:
            return respond(call("resolve_location", query="北京"))
        if len(done) == 3:
            location = done[2]["data"]["location"]["location_id"]
            return respond(
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="工作方式",
                    location_id=location,
                )
            )
        return respond(call("ask_user", question="还有需要补充或更正的资料吗？"))

    async def bazi(messages):
        done = tool_results(messages)
        if not done:
            if runtime.session.profile.get("birth_local_dt") == "1993-08-17 22:20" and failures:
                failures.pop()
                raise RuntimeError("specialist model down")
            return respond(
                call("compute_bazi", location_id=brief(messages)["location_id"], gender="male")
            )
        ref = done[-1]["data"]["interpretations"][0]["ref_id"]
        return respond(
            call(
                "submit_report",
                answer="有条件推进，前提是先明确职责。",
                points=[{"ref_id": ref, "text": "十神关系提示先明确职责边界再推进。"}],
                confidence=LOW,
            )
        )

    runtime = make(project, RoleModel(orchestrator=orchestrator, bazi=bazi))
    try:
        state = lambda: runtime.session.state  # noqa: E731
        assert (await runtime.turn(BIRTH + "用八字看看我的工作方式。")).status == "ask_user"
        old_id = state()["bazi_id"]
        assert any(old_id in ref for ref in state()["allowed_refs"])

        assert (await runtime.turn("更正：我是1993年8月17日晚上10点20分出生的。")).status == (
            "ask_user"
        )
        # The profile changed, so the earlier result is stale: revoked, not kept.
        assert state()["specialist_reports"]["bazi"]["status"] == "failed"
        assert not [s for s in state()["signals"] if s["system"] == "bazi"]
        assert "bazi_id" not in state() and not state()["allowed_refs"]

        outcome = await runtime.turn("再试一次。")
        assert outcome.status == "submit_reading", outcome.text
        new_id = state()["bazi_id"]
        assert new_id != old_id
        refs = {s["ref_id"] for s in state()["signals"]}
        assert refs and all(new_id in ref for ref in refs)
        assert not any(old_id in ref for ref in state()["allowed_refs"])
    finally:
        runtime.close()


async def test_read_reading_restores_that_readings_specialist_state(project):
    """Review item 1: restoring a reading brings its own specialist reports, nothing stale."""

    async def broken(messages):
        raise RuntimeError("specialist model down")

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用占星和塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(
                call("consult_specialist", system="astro", sub_question="工作方式"),
                call("consult_specialist", system="tarot", sub_question="工作状态"),
            )
        tarot = next(r for r in reports_in(done[1:]) if r["system"] == "tarot")
        payload = reading(
            [evidence_of(tarot)],
            ["tarot"],
            question_type="tarot",
            reason="西方占星专家未完成，本次只用塔罗；释义为未人工审核的自写草稿",
            summary="建议先梳理现状，再做小步尝试。",
        )
        return respond(call("submit_reading", **payload))

    model = RoleModel(orchestrator=orchestrator, astro=broken, tarot=tarot_specialist())
    runtime = make(project, model)
    try:
        assert (await runtime.turn("用占星和塔罗看看最近的工作状态。")).status == "submit_reading"
        reading_id = runtime.session.state["active_reading_id"]
        metrics = specialist_metrics(events(runtime))
        assert metrics["report_compliance_rate"] == 0.5
        assert metrics["consults_without_submission"] == 1

        runtime.session.append_user("第一张牌什么意思？")
        assert (await invoke(runtime, "read_reading", reading_id=reading_id)).ok
        state = runtime.session.state
        assert {s: r["status"] for s, r in state["specialist_reports"].items()} == {
            "astro": "failed",
            "tarot": "ok",
        }
        assert not {"consult_cache", "specialist_contrib", "specialist_attempts"} & set(state)
        followup = Reading.model_validate(
            reading(
                [{"ref_id": state["tarot_result"]["cards"][0]["ref_id"], "reading": "原牌解释"}],
                ["tarot"],
                question_type="tarot",
                summary="第一张牌提示先梳理现状。",
            )
        )
        # A follow-up answers from the stored reading; its disclosure was made when saved.
        assert validate_reading(followup, runtime.session) is None
    finally:
        runtime.close()


async def test_concurrent_specialists_cannot_spend_orchestrator_reserve(project, monkeypatch):
    """Review item 2: reviewer's scenario (200 budget, 60 reserve, three 80-token calls)."""

    def estimate(messages, tools, last_input, last_count):
        names = {t["function"]["name"] for t in tools}
        return 15 if "consult_specialist" in names else 80

    monkeypatch.setattr("harness.loop.estimate_call", estimate)

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="看看我的运势"))
        if len(done) == 1:
            return respond(
                *(call("consult_specialist", system=s, sub_question="运势") for s in ROLE_TOOLS)
            )
        return respond(call("ask_user", question="部分专家因预算未完成，要缩小问题范围吗？"))

    async def specialist(messages):
        await asyncio.sleep(0.05)  # keep every admitted call in flight together
        return ModelResponse(text="未完成", input_tokens=75, output_tokens=5)

    model = RoleModel(orchestrator=orchestrator, **dict.fromkeys(ROLE_TOOLS, specialist))
    runtime = make(
        project,
        model,
        request_token_budget=200,
        orchestrator_reserve_tokens=60,
        specialist_token_budget=100,
        specialist_max_steps=1,
    )
    try:
        outcome = await runtime.turn("看看我的运势。")
        # The orchestrator still got its closing call out of the reserve.
        assert outcome.status == "ask_user"
        assert model.calls["orchestrator"] == 3
        assert sum(model.calls[role] for role in ROLE_TOOLS) == 1
        assert runtime.session.budget.used == 15 + 15 + 80 + 15 <= 200
        denied = [e for e in events(runtime) if e["event"] == "budget_denied"]
        assert len(denied) == 2
    finally:
        runtime.close()


async def test_request_deadline_stops_a_waiting_orchestrator(project):
    """Review item 3: the deadline bounds a model call in progress, not only step starts."""

    async def slow(messages):
        await asyncio.sleep(3)
        return respond(call("start_reading", question="q"))

    runtime = make(project, RoleModel(orchestrator=slow), request_timeout_s=0.2)
    try:
        started = time.perf_counter()
        outcome = await runtime.turn("看看我的运势。")
        assert outcome.status == "timeout"
        assert time.perf_counter() - started < 1.5
        assert not runtime.session.state.get("active_reading_id")
    finally:
        runtime.close()


async def test_request_deadline_bounds_tool_execution(project):
    """Review item 3: the request wall clock also cancels a tool that outlives it."""

    async def stall(args, session):
        await asyncio.sleep(3)

    runtime = make(
        project, RoleModel(orchestrator=tarot_only_orchestratorless()), request_timeout_s=0.3
    )
    tool = runtime.registry.tools["start_reading"]
    runtime.registry.tools["start_reading"] = dataclasses.replace(tool, handler=stall)
    try:
        started = time.perf_counter()
        outcome = await runtime.turn("用塔罗看看最近的工作状态。")
        assert outcome.status == "timeout"
        assert time.perf_counter() - started < 1.5
        assert [e for e in events(runtime) if e["event"] == "request_timeout"]
        (result,) = [m for m in runtime.session.messages if m["role"] == "tool"]
        assert '"cancelled"' in result["content"]
    finally:
        runtime.close()


async def test_request_deadline_bounds_running_specialists(project):
    """Review item 3: a slow specialist cannot hold the request past its wall clock."""

    async def slow(messages):
        await asyncio.sleep(3)
        return respond(call("draw_tarot", spread="single", question="q"))

    model = RoleModel(orchestrator=tarot_only_orchestratorless(), tarot=slow)
    runtime = make(project, model, request_timeout_s=0.3, specialist_timeout_s=10)
    try:
        started = time.perf_counter()
        outcome = await runtime.turn("用塔罗看看最近的工作状态。")
        assert outcome.status == "timeout"
        assert time.perf_counter() - started < 2
        calls = {
            c["id"]
            for m in runtime.session.messages
            if m.get("tool_calls")
            for c in m["tool_calls"]
        }
        answered = {m["tool_call_id"] for m in runtime.session.messages if m["role"] == "tool"}
        assert calls <= answered  # protocol stays complete for the next request
        reading_id = runtime.session.state["active_reading_id"]
        tree = build_tree(events(runtime), reading_id)
        assert tree["problems"] == []
        (root,) = tree["roots"]
        (child,) = root["children"]
        assert {"session_started", "session_finished"} <= {e["event"] for e in child["events"]}
        assert not draws(runtime)
    finally:
        runtime.close()


def tarot_only_orchestratorless():
    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(call("consult_specialist", system="tarot", sub_question="工作状态"))
        return respond(call("ask_user", question="塔罗专家没有完成，要稍后再试吗？"))

    return orchestrator


async def test_response_after_deadline_runs_no_tools(project):
    """Review item 3: a response that arrives after the deadline is not acted on."""

    async def late(messages):
        time.sleep(0.3)  # blocking: cannot be interrupted, returns after the deadline
        return respond(call("start_reading", question="q"))

    runtime = make(project, RoleModel(orchestrator=late), request_timeout_s=0.1)
    try:
        outcome = await runtime.turn("看看我的运势。")
        assert outcome.status == "timeout"
        assert not runtime.session.state.get("active_reading_id")
        assert not [e for e in events(runtime) if e["event"] == "tool_result"]
    finally:
        runtime.close()


async def test_draw_survives_a_failed_report_and_spread_stays_fixed(project):
    """Review item 4: the draw is kept when reporting fails; the retry cannot redraw."""

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用塔罗看看最近的工作状态"))
        if len(done) == 1:
            return respond(
                call("consult_specialist", system="tarot", sub_question="工作状态", spread="single")
            )
        if len(done) == 2:
            assert done[1]["data"]["report"]["status"] == "failed"
            return respond(
                call(
                    "consult_specialist",
                    system="tarot",
                    sub_question="工作状态",
                    spread="three_card",
                )
            )
        if len(done) == 3:
            assert done[2]["code"] == "validation_failed" and "已抽牌" in done[2]["error"]
            return respond(call("consult_specialist", system="tarot", sub_question="工作状态"))
        return respond(
            call(
                "submit_reading",
                **reading(
                    [evidence_of(done[3]["data"]["report"])],
                    ["tarot"],
                    question_type="tarot",
                    summary="建议先梳理现状，再做小步尝试。",
                ),
            )
        )

    async def tarot(messages):
        b = brief(messages)
        if b["existing_results"]:
            draw = b["existing_results"][0]["data"]
            return respond(
                call(
                    "submit_report",
                    answer="先梳理现状。",
                    points=tarot_points(draw),
                    confidence=LOW,
                )
            )
        if not tool_results(messages):
            return respond(call("draw_tarot", spread=b["spread"], question=b["original_question"]))
        raise RuntimeError("report step down")

    runtime = make(project, RoleModel(orchestrator=orchestrator, tarot=tarot))
    try:
        outcome = await runtime.turn("用塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        assert len(draws(runtime)) == 1
        assert runtime.session.state["tarot_result"]["spread"] == "single"
        assert "tarot" not in runtime.session.state["specialist_facts"]
    finally:
        runtime.close()


async def test_timeout_before_first_response_keeps_the_call_tree(project):
    """Review item 5: the child session is traced even if it never got a model response."""

    async def stuck(messages):
        await asyncio.sleep(5)
        return respond(call("draw_tarot", spread="single", question="q"))

    model = RoleModel(orchestrator=tarot_only_orchestratorless(), tarot=stuck)
    runtime = make(project, model, specialist_timeout_s=0.2)
    try:
        assert (await runtime.turn("用塔罗看看最近的工作状态。")).status == "ask_user"
        report = runtime.session.state["specialist_reports"]["tarot"]
        assert (report["status"], report["failure"]) == ("failed", "专家超时")
        tree = build_tree(events(runtime), runtime.session.state["active_reading_id"])
        assert tree["problems"] == []
        (child,) = tree["roots"][0]["children"]
        assert {"session_started", "session_finished", "timeout"} <= {
            e["event"] for e in child["events"]
        }
    finally:
        runtime.close()


async def test_queueing_is_not_counted_as_concurrency(project):
    """Review item 6: with one permit, the metric must report one running specialist."""

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="看看我的运势"))
        if len(done) == 1:
            return respond(
                *(call("consult_specialist", system=s, sub_question="运势") for s in ROLE_TOOLS)
            )
        return respond(call("ask_user", question="继续吗？"))

    async def specialist(messages):
        await asyncio.sleep(0.1)
        return ModelResponse(text="未完成", input_tokens=1, output_tokens=1)

    model = RoleModel(orchestrator=orchestrator, **dict.fromkeys(ROLE_TOOLS, specialist))
    runtime = make(project, model, max_parallel_specialists=1, specialist_max_steps=1)
    try:
        await runtime.turn("看看我的运势。")
        metrics = specialist_metrics(events(runtime))
        assert metrics["max_concurrent_specialists"] == 1
        assert sorted(metrics["queue_ms"])[-1] >= 150  # the last one waited for two others
    finally:
        runtime.close()


async def test_first_pass_rate_uses_each_consults_first_submission(project):
    """Review item 7: rejected, rejected, accepted is a 0% first pass, not 33%."""
    attempts = []

    async def tarot(messages):
        done = [r for r in tool_results(messages) if r["ok"] and "cards" in r["data"]]
        if not done:
            return respond(call("draw_tarot", spread="three_card", question="q"))
        attempts.append(len(attempts))
        if len(attempts) < 3:
            bad = [{"ref_id": "astro:fake:Sun:Leo", "text": "伪造引用"}]
            return respond(call("submit_report", answer="x", points=bad, confidence=LOW))
        points = tarot_points(done[0]["data"])
        return respond(call("submit_report", answer="先梳理现状。", points=points, confidence=LOW))

    model = RoleModel(orchestrator=tarot_only_orchestratorless(), tarot=tarot)
    runtime = make(project, model)
    try:
        await runtime.turn("用塔罗看看最近的工作状态。")
        metrics = specialist_metrics(events(runtime))
        assert metrics["report_first_pass_rate"] == 0.0
        assert metrics["report_corrected_pass_rate"] == 1.0
        assert metrics["submit_attempt_pass_rate"] == 1 / 3
        assert metrics["report_compliance_rate"] == 1.0
    finally:
        runtime.close()


async def test_single_mode_keeps_week1_3_budget_semantics(project, scripted_model):
    """Admission estimates apply to multi mode only: single mode still allows a call while
    any budget is left, as accepted in weeks 1-3."""
    path = project / "config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["limits"]["request_token_budget"] = 100
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    model = scripted_model(
        [
            ModelResponse(
                tool_calls=[ToolCall(id="p", name="get_profile", arguments={})],
                input_tokens=85,
                output_tokens=5,
            ),
            ModelResponse(text="你好", input_tokens=5, output_tokens=5),
        ]
    )
    runtime = create_runtime(root=project, user_id="single-budget", model=model, mode="single")
    try:
        outcome = await runtime.turn("你好")
        assert outcome.status == "text"
        assert runtime.session.budget.used == 100
        assert not [e for e in events(runtime) if e["event"].startswith("budget_")]
    finally:
        runtime.close()


async def test_cancelled_request_closes_queued_and_running_specialists(project):
    """Review item 3: cancelling the request (what the wall clock does) closes every child,
    including ones still waiting for a parallelism permit."""

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="看看我的运势"))
        return respond(
            *(call("consult_specialist", system=s, sub_question="运势") for s in ROLE_TOOLS)
        )

    async def stuck(messages):
        await asyncio.sleep(30)

    model = RoleModel(orchestrator=orchestrator, **dict.fromkeys(ROLE_TOOLS, stuck))
    runtime = make(project, model, max_parallel_specialists=1, request_timeout_s=60)
    try:
        task = asyncio.create_task(runtime.turn("看看我的运势。"))
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finished = [e for e in events(runtime) if e["event"] == "specialist_finished"]
        assert sorted(e["status"] for e in finished) == ["cancelled"] * 3
        assert sorted(e["latency_ms"] == 0 for e in finished) == [False, True, True]
        tree = build_tree(events(runtime), runtime.session.state["active_reading_id"])
        assert tree["problems"] == []
        assert len(tree["roots"][0]["children"]) == 3
        answered = {m["tool_call_id"] for m in runtime.session.messages if m["role"] == "tool"}
        assert {c["id"] for m in runtime.session.messages for c in m.get("tool_calls") or []} <= (
            answered
        )
    finally:
        runtime.close()
