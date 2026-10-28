import json

import pytest

from harness.loop import run_turn
from harness.models import ModelResponse, StrictInput, ToolCall, ToolResult
from harness.registry import Tool


class Attempt(StrictInput):
    draft: int = 0


def response(index, name="submit_test"):
    return ModelResponse(
        input_tokens=100,
        output_tokens=10,
        tool_calls=[ToolCall(id=f"attempt-{index}", name=name, arguments=dict(draft=index))],
    )


def register(runtime, *, terminal=True, handler=None):
    runtime.registry.register(
        Tool(
            "submit_test",
            "test",
            Attempt,
            handler or (lambda a, s: ToolResult.failure("validation_failed", "同一事实错误")),
            terminal=terminal,
            idempotent=False,
        )
    )


async def test_changing_submission_draft_cannot_repeat_same_failure_forever(
    runtime, scripted_model
):
    register(runtime)
    runtime.session.state["calculations"] = {"kept": {"value": 1}}
    model = scripted_model([response(i) for i in range(12)])
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "retry_limit"
    assert len(model.seen_messages) == 3
    assert runtime.session.total_tokens == 330
    assert outcome.data["failure"]["retained_calculations"]
    assert runtime.session.state["calculations"] == {"kept": {"value": 1}}
    assert runtime.store.recent_readings(runtime.session.user_id) == []


async def test_unrelated_success_does_not_reset_submission_failures(runtime, scripted_model):
    register(runtime)
    responses = []
    for i in range(3):
        responses.extend(
            [
                response(i),
                ModelResponse(
                    tool_calls=[
                        ToolCall(id=f"profile-{i}", name="get_profile"),
                    ]
                ),
            ]
        )
    model = scripted_model(responses)
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "retry_limit"
    assert len(model.seen_messages) == 5


async def test_repaired_submission_can_finish_before_limit(runtime, scripted_model):
    register(
        runtime,
        handler=lambda a, s: (
            dict(text="完成")
            if a.draft == 2
            else ToolResult.failure("validation_failed", "事实错误")
        ),
    )
    model = scripted_model([response(i) for i in range(3)])
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "submit_test" and outcome.text == "完成"


@pytest.mark.parametrize("same_arguments", [True, False])
async def test_nonterminal_failures_track_inputs(runtime, scripted_model, same_arguments):
    register(runtime, terminal=False)
    model = scripted_model([response(0 if same_arguments else i) for i in range(4)])
    outcome = await run_turn(
        runtime.session,
        "q",
        model,
        runtime.registry,
        runtime.tracer,
        max_steps=4,
    )
    assert outcome.status == ("retry_limit" if same_arguments else "limit_reached")


async def test_retry_limit_completes_protocol_and_resets_next_request(runtime, scripted_model):
    register(runtime)
    last = response(2)
    last.tool_calls.append(
        ToolCall(id="after-limit", name="start_reading", arguments=dict(question="q"))
    )
    model = scripted_model([response(0), response(1), last])
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "retry_limit"
    messages = [m for m in runtime.session.messages if m["role"] == "tool"]
    assert len(messages) == 4
    assert json.loads(messages[-1]["content"])["code"] == "turn_finished"
    assert not runtime.session.state.get("active_reading_id")
    next_model = scripted_model([response(3), ModelResponse(text="下一轮")])
    outcome = await run_turn(runtime.session, "q", next_model, runtime.registry, runtime.tracer)
    assert outcome.status == "text"


async def test_successful_tool_resets_its_failure_counter(runtime, scripted_model):
    register(
        runtime,
        terminal=False,
        handler=lambda a, s: (
            {} if a.draft == 1 else ToolResult.failure("validation_failed", "失败")
        ),
    )
    model = scripted_model([response(i) for i in (0, 0, 1, 0, 0)] + [ModelResponse(text="结束")])
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "text"
