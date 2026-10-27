"""A rejected draft is repaired on the existing reading, never by resetting its facts."""

import copy
import json

from harness.context import SNAPSHOT_PREFIX, compact_context
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from harness.refs import transform
from tests.plugins.test_astro_bazi_integration import draft, invoke, prepare


def response(name, **arguments):
    return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=arguments)])


async def prepared_bazi(runtime):
    birth = await prepare(runtime)
    assert (await invoke(runtime, "compute_bazi", birth)).ok
    good = draft(runtime)
    bad = copy.deepcopy(good)
    bad["summary"] = "原局年柱是" + runtime.session.state["bazi_result"]["pillars"]["month"] + "。"
    return good, bad


async def test_rejected_draft_survives_compaction_and_repairs_without_reset(runtime):
    good, bad = await prepared_bazi(runtime)
    session = runtime.session
    reading_id = session.state["active_reading_id"]
    calculations = copy.deepcopy(session.state["calculations"])
    short_good = transform(good, session)
    short_bad = transform(bad, session)
    step = 0

    class Repair:
        async def chat(self, messages, tools):
            nonlocal step
            step += 1
            if step == 1:
                return response("submit_reading", **short_bad)
            if step == 2:
                result = json.loads(messages[-1]["content"])
                assert result["code"] == "validation_failed"
                assert "summary" in result["error"] and "应为" in result["error"]
                assert result["data"]["recovery"]["attempt"] == 1
                return response("start_reading", question="重新开始同一个问题")
            if step == 3:
                result = json.loads(messages[-1]["content"])
                assert not result["ok"] and "不要重开" in result["error"]
                assert session.state["active_reading_id"] == reading_id
                assert compact_context(session, runtime.registry, force=True)
                snapshot = next(
                    m["content"]
                    for m in session.messages
                    if m.get("content", "").startswith(SNAPSHOT_PREFIX)
                )
                packet = json.loads(snapshot.removeprefix(SNAPSHOT_PREFIX))
                assert packet["failed_submission"]["arguments"]["summary"] == bad["summary"]
                assert packet["failed_submission"]["arguments"]["evidence"] == short_bad["evidence"]
                return response("read_reading")
            result = json.loads(messages[-1]["content"])
            restored = result["data"]["reading"]
            assert restored["status"] == "in_progress"
            assert restored["reading_id"] == reading_id
            assert restored["output_json"]["summary"] == bad["summary"]
            assert restored["output_json"]["evidence"] == short_bad["evidence"]
            assert session.state["failed_submission"]["arguments"]["evidence"] == bad["evidence"]
            assert "应为" in restored["validation_error"]
            return response("submit_reading", **short_good)

    outcome = await run_turn(session, "继续", Repair(), runtime.registry, runtime.tracer)
    assert outcome.status == "submit_reading", outcome.text
    assert session.state["active_reading_id"] == reading_id
    assert session.state["calculations"] == calculations
    assert "failed_submission" not in session.state
    assert runtime.store.get_reading(session.user_id, reading_id)


async def test_same_failure_stops_before_step_limit_and_can_continue_next_turn(
    runtime, scripted_model
):
    good, bad = await prepared_bazi(runtime)
    session = runtime.session
    reading_id = session.state["active_reading_id"]
    # Changing unrelated content must not buy more attempts at the same underlying error.
    responses = [response("submit_reading", **{**bad, "closing": f"建议第{i}版"}) for i in range(5)]
    model = scripted_model(responses)
    outcome = await run_turn(session, "继续解读", model, runtime.registry, runtime.tracer)
    assert outcome.status == "validation_stalled"
    assert outcome.data["failure"]["reason"] == "repeated_tool_failure"
    assert outcome.data["failure"]["retained_calculations"]
    assert len(model.seen_messages) == 3
    assert not runtime.store.get_reading(session.user_id, reading_id)
    assert session.state["active_reading_id"] == reading_id
    assert session.state["failed_submission"]["arguments"]["closing"] == "建议第2版"
    fixed = scripted_model([response("submit_reading", **good)])
    outcome = await run_turn(session, "请继续修正", fixed, runtime.registry, runtime.tracer)
    assert outcome.status == "submit_reading"
    assert session.state["active_reading_id"] == reading_id


async def test_active_snapshot_cannot_replace_foreign_or_missing_history(runtime):
    await prepared_bazi(runtime)
    result = await invoke(runtime, "read_reading", {"reading_id": "someone-elses-reading"})
    assert not result.ok and result.code == "missing_reading"


async def test_read_without_an_active_or_saved_reading_is_missing(runtime):
    result = await invoke(runtime, "read_reading", {})
    assert not result.ok and result.code == "missing_reading"


async def test_flow_evidence_can_be_submitted_and_saved_as_facts(runtime):
    good, _ = await prepared_bazi(runtime)
    state = runtime.session.state
    result = await invoke(
        runtime,
        "compute_bazi_period",
        {
            "bazi_id": state["bazi_id"],
            "start": "2026-01-01",
            "end": "2028-12-31",
            "granularity": "year",
        },
    )
    assert result.ok
    good["evidence"] = [{"ref_id": item["ref_id"]} for item in result.data["interpretations"]]
    submitted = await invoke(runtime, "submit_reading", good)
    assert submitted.ok, submitted.error
    saved = runtime.store.get_reading(runtime.session.user_id, state["active_reading_id"])
    assert any("流年：" in item["reading"] for item in saved["output_json"]["evidence"])


async def test_stalled_batch_answers_all_calls_without_resetting_reading(runtime, scripted_model):
    _, bad = await prepared_bazi(runtime)
    session = runtime.session
    reading_id = session.state["active_reading_id"]
    third = response("submit_reading", **bad)
    third.tool_calls.append(
        ToolCall(id="reset", name="start_reading", arguments={"question": "重开"})
    )
    model = scripted_model(
        [response("submit_reading", **bad), response("submit_reading", **bad), third]
    )
    outcome = await run_turn(session, "继续", model, runtime.registry, runtime.tracer)
    assert outcome.status == "validation_stalled"
    assert session.state["active_reading_id"] == reading_id
    assert session.state["failed_submission"]["arguments"]["summary"] == bad["summary"]
    reset_result = next(m for m in session.messages if m.get("tool_call_id") == "reset")
    assert json.loads(reset_result["content"])["code"] == "turn_finished"
