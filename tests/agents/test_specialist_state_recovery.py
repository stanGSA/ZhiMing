"""State recovery across profile edits, request cancellation and repeated report failures."""

import asyncio

import pytest

from common.validation import report_matches_profile
from harness.guard import Guard
from scripts.trace_tree import build_tree
from tests.agents.test_multi_agent import (
    BIRTH,
    LOW,
    RoleModel,
    brief,
    call,
    disclose,
    events,
    make,
    reading,
    respond,
    tarot_points,
    tool_results,
    turn_results,
)


async def invoke(runtime, name, **arguments):
    args, error, _ = Guard(runtime.registry).check(call(name, **arguments), runtime.session)
    if error is not None:
        return error
    result = await runtime.registry.run(name, args, runtime.session)
    tool = runtime.registry.tools[name]
    return tool.commit(result, runtime.session) if result.ok and tool.commit else result


@pytest.mark.parametrize(
    "report,profile,expected",
    [
        ({"profile_version": 1}, {"version": 1}, True),
        ({"profile_version": 1}, {"version": 2}, False),
        ({"profile_dependencies": {}}, {"version": 2, "name": "小明"}, True),
        ({"profile_dependencies": {"time_known": None}}, {"time_known": True}, False),
        ({"profile_dependencies": {"time_known": True}}, {}, False),
    ],
)
def test_profile_snapshot_checks_missing_fields_and_legacy_reports(report, profile, expected):
    assert report_matches_profile(report, profile) is expected


async def test_unrelated_profile_edit_preserves_report_when_retry_fails(project):
    fail = False
    handler = expert("bazi")

    async def bazi(messages):
        if fail:
            raise RuntimeError("synthetic retry failure")
        return await handler(messages)

    runtime = make(project, RoleModel(bazi=bazi))
    try:
        session = runtime.session
        session.append_user(BIRTH + "我叫小明，用八字看看工作方式。")
        session.start_reading("用八字看看工作方式")
        assert (
            await invoke(
                runtime,
                "update_profile",
                field="birth_local_dt",
                value="1993-08-17 23:20",
                evidence="1993年8月17日晚上11点20分",
            )
        ).ok
        location = (await invoke(runtime, "resolve_location", query="北京")).data["location"]
        args = dict(system="bazi", sub_question="工作方式", location_id=location["location_id"])
        first = await invoke(runtime, "consult_specialist", **args)
        assert first.data["report"]["status"] == "ok"
        old_refs = set(session.state["allowed_refs"])
        updated = await invoke(
            runtime, "update_profile", field="name", value="小明", evidence="我叫小明"
        )
        assert updated.ok
        fail = True
        retry = await invoke(runtime, "consult_specialist", **args)
        assert retry.data["report"]["status"] == "failed"
        assert retry.data["report"]["retained_previous"]
        assert session.state["specialist_reports"]["bazi"] == first.data["report"]
        assert session.state["allowed_refs"] == old_refs
    finally:
        runtime.close()


def expert(system):
    async def handler(messages):
        done = tool_results(messages)
        if not done:
            arguments = {"location_id": brief(messages)["location_id"]}
            if system == "bazi":
                arguments["gender"] = "male"
            return respond(
                call("compute_bazi" if system == "bazi" else "compute_natal_chart", **arguments)
            )
        return respond(
            call(
                "submit_report",
                answer="先明确职责。",
                points=[
                    {
                        "ref_id": done[-1]["data"]["interpretations"][0]["ref_id"],
                        "text": "相关配置提示先明确职责边界。",
                    }
                ],
                confidence=LOW,
            )
        )

    return handler


@pytest.mark.parametrize("partial_reconsult", [False, True])
async def test_profile_edit_blocks_stale_submission_until_all_reports_refreshed(
    project, partial_reconsult
):
    runtime = make(project, RoleModel(bazi=expert("bazi"), astro=expert("astro")))
    try:
        session = runtime.session
        session.append_user(BIRTH + "我叫小明，用八字和占星看看工作方式。")
        session.start_reading("用八字和占星看看工作方式")
        await invoke(
            runtime,
            "update_profile",
            field="birth_local_dt",
            value="1993-08-17 23:20",
            evidence="1993年8月17日晚上11点20分",
        )
        location = (await invoke(runtime, "resolve_location", query="北京")).data["location"]

        async def consult(system):
            result = await invoke(
                runtime,
                "consult_specialist",
                system=system,
                sub_question="工作方式",
                location_id=location["location_id"],
            )
            assert result.ok and result.data["report"]["status"] == "ok"

        async def payload():
            evidence = [
                {"ref_id": r["points"][0]["ref_id"], "reading": r["points"][0]["text"]}
                for r in session.state["specialist_reports"].values()
            ]
            output = reading(
                evidence, ["bazi", "astro"], question_type="trait", summary="先明确职责。"
            )
            table = (await invoke(runtime, "merge_signals")).data["merge"]
            output["tensions"] = disclose(table)
            output["sections"] = [
                {"title": "工作方式", "body": e["reading"], "ref_ids": [e["ref_id"]]}
                for e in evidence
            ]
            return output

        await consult("bazi")
        await consult("astro")
        old_refs = set(session.state["allowed_refs"])
        # Unrelated profile edits must not invalidate either specialist's birth calculation.
        await invoke(runtime, "update_profile", field="name", value="小明", evidence="我叫小明")
        _, error, _ = Guard(runtime.registry).check(
            call("submit_reading", **await payload()), session
        )
        assert error is None

        session.append_user("更正：我是1993年8月17日晚上10点20分出生的。")
        await invoke(
            runtime,
            "update_profile",
            field="birth_local_dt",
            value="1993-08-17 22:20",
            evidence="1993年8月17日晚上10点20分出生",
        )
        if partial_reconsult:
            await consult("bazi")
        rejected = await invoke(runtime, "submit_reading", **await payload())
        assert not rejected.ok and rejected.code == "validation_failed"
        assert "画像" in rejected.error and "重新咨询" in rejected.error
        reading_id = session.state["active_reading_id"]
        assert runtime.store.get_reading(session.user_id, reading_id) is None

        if not partial_reconsult:
            await consult("bazi")
        await consult("astro")
        assert not old_refs & session.state["allowed_refs"]
        output = await payload()
        assert (await invoke(runtime, "submit_reading", **output)).ok
        stored = runtime.store.specialist_reports(session.user_id, reading_id)
        assert all(
            r["profile_dependencies"]["birth_local_dt"] == "1993-08-17 22:20"
            for r in stored.values()
        )

        # A historical follow-up deliberately uses its pinned calculations, even after an edit.
        session.append_user("更正：我是1993年8月17日晚上9点20分出生的。")
        await invoke(
            runtime,
            "update_profile",
            field="birth_local_dt",
            value="1993-08-17 21:20",
            evidence="1993年8月17日晚上9点20分出生",
        )
        assert (await invoke(runtime, "read_reading", reading_id=reading_id)).ok
        assert (await invoke(runtime, "submit_reading", **output)).ok
    finally:
        runtime.close()


@pytest.mark.parametrize("termination", ["cancel", "timeout"])
@pytest.mark.parametrize("finished_sibling", [False, True])
async def test_draw_survives_cancelled_request_and_completed_sibling(
    project, termination, finished_sibling
):
    ready = asyncio.Event()
    retry = False

    async def tarot(messages):
        existing = brief(messages).get("existing_results")
        done = tool_results(messages)
        if existing:
            draw = existing[0]["data"]
        elif not done:
            return respond(call("draw_tarot", spread="single", question="工作状态"))
        else:
            draw = done[0]["data"]
        if not retry:
            ready.set()
            if not finished_sibling:
                await asyncio.sleep(30)
        return respond(
            call("submit_report", answer="先梳理现状。", points=tarot_points(draw), confidence=LOW)
        )

    async def blocked(messages):
        await asyncio.sleep(30)

    async def orchestrator(messages):
        done = turn_results(messages)
        if retry:
            if not done:
                return respond(
                    call("consult_specialist", system="tarot", sub_question="继续原问题")
                )
            report = done[0]["data"]["report"]
            assert report["status"] == "ok"
            evidence = [{"ref_id": p["ref_id"], "reading": p["text"]} for p in report["points"]]
            return respond(
                call(
                    "submit_reading",
                    **reading(evidence, ["tarot"], question_type="tarot", summary="先梳理现状。"),
                )
            )
        if not done:
            return respond(call("start_reading", question="用塔罗看看工作状态"))
        consults = [call("consult_specialist", system="tarot", sub_question="工作状态")]
        if finished_sibling:
            consults.append(call("consult_specialist", system="bazi", sub_question="工作状态"))
        return respond(*consults)

    runtime = make(
        project,
        RoleModel(orchestrator=orchestrator, tarot=tarot, bazi=blocked),
        request_timeout_s=0.5 if termination == "timeout" else 60,
        specialist_timeout_s=10,
    )
    task = asyncio.create_task(runtime.turn("用塔罗看看工作状态。"))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        if termination == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert (await task).status == "timeout"
        state = runtime.session.state
        reading_id = state["active_reading_id"]
        assert state["specialist_facts"]["tarot"]["values"]["tarot_result"]["spread"] == "single"
        recovery = (await invoke(runtime, "read_reading")).data["reading"]
        assert recovery["recovery_stage"] == "needs_specialist_report"
        assert recovery["pending_specialists"] == ["tarot"]
        assert recovery["tarot_json"]["cards"]
        assert "consult_specialist" in recovery["note"]
        changed = await invoke(
            runtime, "consult_specialist", system="tarot", sub_question="继续", spread="three_card"
        )
        assert not changed.ok and "已抽牌" in changed.error
        retry = True
        assert (await runtime.turn("继续原问题。")).status == "submit_reading"
        assert runtime.session.state["active_reading_id"] == reading_id
        draws = [
            e
            for e in events(runtime)
            if e["event"] == "tool_result"
            and e["call"]["name"] == "draw_tarot"
            and e["result"]["ok"]
        ]
        assert len(draws) == 1
        assert (
            runtime.store.get_reading(runtime.session.user_id, reading_id)["tarot_json"]["spread"]
            == "single"
        )
        assert build_tree(events(runtime), reading_id)["problems"] == []
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        runtime.close()


async def test_three_report_attempts_keep_the_original_calculation_snapshot(project):
    seen = []
    attempts = 0

    async def tarot(messages):
        nonlocal attempts
        existing = brief(messages).get("existing_results")
        done = tool_results(messages)
        if not done:
            seen.append(len(existing or []))
        if not existing and not done:
            return respond(call("draw_tarot", spread="single", question="工作状态"))
        draw = existing[0]["data"] if existing else done[0]["data"]
        attempts += 1
        if attempts <= 2:
            raise RuntimeError("synthetic report failure")
        return respond(
            call("submit_report", answer="先梳理现状。", points=tarot_points(draw), confidence=LOW)
        )

    async def orchestrator(messages):
        done = turn_results(messages)
        if not done:
            return respond(call("start_reading", question="用塔罗看看工作状态"))
        if len(done) <= 3:
            return respond(call("consult_specialist", system="tarot", sub_question="工作状态"))
        report = done[-1]["data"]["report"]
        evidence = [{"ref_id": p["ref_id"], "reading": p["text"]} for p in report["points"]]
        return respond(
            call(
                "submit_reading",
                **reading(evidence, ["tarot"], question_type="tarot", summary="先梳理现状。"),
            )
        )

    runtime = make(project, RoleModel(orchestrator=orchestrator, tarot=tarot))
    try:
        outcome = await runtime.turn("用塔罗看看工作状态。")
        assert seen == [0, 1, 1]
        assert outcome.status == "submit_reading"
        draws = [
            e
            for e in events(runtime)
            if e["event"] == "tool_result" and e["call"]["name"] == "draw_tarot"
        ]
        assert len(draws) == 1 and draws[0]["result"]["ok"]
    finally:
        runtime.close()


async def test_read_after_failed_report_retries_the_expert_without_redrawing(project):
    from copy import deepcopy

    from harness.refs import transform

    fail_report = True

    async def tarot(messages):
        existing = brief(messages).get("existing_results")
        done = tool_results(messages)
        if not existing and not done:
            return respond(call("draw_tarot", spread="single", question="工作状态"))
        if fail_report:
            raise RuntimeError("synthetic report failure")
        draw = existing[0]["data"] if existing else done[0]["data"]
        return respond(
            call("submit_report", answer="先梳理现状。", points=tarot_points(draw), confidence=LOW)
        )

    runtime = make(project, RoleModel(tarot=tarot))
    try:
        session = runtime.session
        session.append_user("用塔罗看看工作状态")
        assert (await invoke(runtime, "start_reading", question="工作状态", systems=["tarot"])).ok
        failed = await invoke(
            runtime, "consult_specialist", system="tarot", sub_question="工作状态"
        )
        assert failed.data["report"]["status"] == "failed"
        kept = deepcopy(session.state["specialist_facts"])
        recovered = await invoke(runtime, "read_reading")
        projected = runtime.registry.tools["read_reading"].model_result(recovered.data)
        shown = transform(projected, session)["reading"]
        assert shown["recovery_stage"] == "needs_specialist_report"
        assert shown["pending_specialists"] == ["tarot"]
        assert shown["tarot_json"]["cards"]
        assert "ref_id" not in shown["tarot_json"]["cards"][0]
        assert shown["citable"] == []
        assert "consult_specialist" in shown["note"]
        assert session.state["specialist_facts"] == kept
        assert session.state["allowed_refs"] == set()

        fail_report = False
        retried = await invoke(
            runtime, "consult_specialist", system="tarot", sub_question="工作状态"
        )
        assert retried.data["report"]["status"] == "ok"
        ready = (await invoke(runtime, "read_reading")).data["reading"]
        assert ready["recovery_stage"] == "ready_to_submit"
        assert ready["pending_specialists"] == []
        assert ready["citable"]
        points = retried.data["report"]["points"]
        evidence = [{"ref_id": p["ref_id"], "reading": p["text"]} for p in points]
        assert (
            await invoke(
                runtime,
                "submit_reading",
                **reading(evidence, ["tarot"], question_type="tarot", summary="先梳理现状。"),
            )
        ).ok
        draws = [
            e
            for e in events(runtime)
            if e["event"] == "tool_result" and e["call"]["name"] == "draw_tarot"
        ]
        assert len(draws) == 1
    finally:
        runtime.close()
