import json

import pytest

from agents.demo import DemoModel
from harness.context import CONTEXT_CHAR_LIMIT, SNAPSHOT_PREFIX, compact_context
from harness.failures import model_failure
from harness.guard import Guard
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from harness.refs import transform


async def test_failed_context_compacts_without_losing_draw_or_tool_protocol(
    runtime, scripted_model
):
    session = runtime.session
    session.append_user("抽一张牌")
    session.start_reading("抽一张牌")
    call = ToolCall(
        id="draw", name="draw_tarot", arguments={"spread": "single", "question": "抽一张牌"}
    )
    args, error, _ = Guard(runtime.registry).check(call, session)
    assert error is None
    draw = await runtime.registry.run("draw_tarot", args, session)
    session.state["tarot_drawn"] = True
    original = json.dumps(session.state["tarot_result"], ensure_ascii=False)
    short = transform({"ref_id": draw.data["cards"][0]["ref_id"]}, session)["ref_id"]
    for i in range(20):
        session.messages.extend(
            [
                ModelResponse(
                    tool_calls=[ToolCall(id=str(i), name="bad", arguments={})]
                ).assistant_message(),
                {
                    "role": "tool",
                    "tool_call_id": str(i),
                    "content": json.dumps(
                        {"ok": False, "code": "validation_failed", "error": "旧错误" * 3000}
                    ),
                },
            ]
        )
    session.append_user("继续解释原牌面")
    runtime.compact_history()
    assert len(json.dumps(session.messages, ensure_ascii=False)) < CONTEXT_CHAR_LIMIT
    assert session.messages[-1]["content"] == "继续解释原牌面"
    snapshot = next(
        m["content"] for m in session.messages if m.get("content", "").startswith(SNAPSHOT_PREFIX)
    )
    packet = json.loads(snapshot.removeprefix(SNAPSHOT_PREFIX))
    assert packet["tarot_result"]["cards"][0]["ref_id"] == short
    assert json.dumps(session.state["tarot_result"], ensure_ascii=False) == original
    assert not any(m["role"] == "tool" or m.get("tool_calls") for m in session.messages)
    output = DemoModel.submission("抽一张牌", [{"ref_id": short}], "single", "A")
    model = scripted_model(
        [ModelResponse(tool_calls=[ToolCall(id="submit", name="submit_reading", arguments=output)])]
    )
    outcome = await run_turn(session, "继续解释原牌面", model, runtime.registry, runtime.tracer)
    assert outcome.status == "submit_reading"
    assert runtime.store.get_reading(session.user_id, session.state["active_reading_id"])
    assert json.dumps(session.state["tarot_result"], ensure_ascii=False) == original


async def test_large_failed_turn_compacts_before_model_call(runtime):
    runtime.session.messages.append({"role": "assistant", "content": "失败轨迹" * 20000})

    class Inspect:
        async def chat(self, messages, tools):
            assert len(json.dumps(messages, ensure_ascii=False)) < CONTEXT_CHAR_LIMIT
            assert messages[-1]["content"] == "换个角度继续"
            return ModelResponse(text="可以，先明确你关心的方面。")

    runtime.model = Inspect()
    assert (await runtime.turn("换个角度继续")).status == "text"


async def test_limit_failures_distinguish_budget_steps_and_output(runtime, scripted_model):
    steps = await run_turn(
        runtime.session, "看八字", scripted_model([]), runtime.registry, runtime.tracer, max_steps=0
    )
    assert steps.data["failure"]["reason"] == "step_limit"
    assert "抽牌" not in steps.text and "保留" not in steps.text
    tokens = await run_turn(
        runtime.session,
        "看八字",
        scripted_model([ModelResponse(text="reply", input_tokens=100)]),
        runtime.registry,
        runtime.tracer,
        token_budget=20,
    )
    assert tokens.data["failure"]["reason"] == "token_budget"
    truncated = await run_turn(
        runtime.session,
        "看八字",
        scripted_model([ModelResponse(text="partial", finish_reason="length")]),
        runtime.registry,
        runtime.tracer,
    )
    assert truncated.data["failure"]["reason"] == "output_limit"


@pytest.mark.parametrize(
    "status,code,reason",
    [
        (401, None, "authorization"),
        (429, None, "rate_limit"),
        (503, None, "provider_unavailable"),
        (400, "context_length_exceeded", "context_limit"),
    ],
)
def test_provider_failures_are_actionable_without_exposing_exception(runtime, status, code, reason):
    class ProviderError(Exception):
        pass

    exc = ProviderError("secret request headers")
    exc.status_code, exc.code = status, code
    outcome = model_failure(runtime.session, exc)
    assert outcome.data["failure"]["reason"] == reason
    assert "secret" not in outcome.model_dump_json()


def test_small_incomplete_context_is_unchanged(runtime):
    messages = list(runtime.session.messages)
    assert not compact_context(runtime.session, runtime.registry)
    assert runtime.session.messages == messages
