import json

import httpx
import pytest
import yaml
from openai import AsyncOpenAI

from app import build_model, create_runtime
from harness.llm import OpenAIModel
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from harness.registry import Registry
from harness.session import Session
from harness.trace import Tracer


@pytest.mark.parametrize("thinking,effort", [("disabled", None), ("enabled", "low")])
async def test_deepseek_wire_protocol_and_reasoning_replay(monkeypatch, thinking, effort):
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test")
    monkeypatch.setenv("OPENAI_API_KEY", "old-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://old.test")
    received = []

    def respond(request):
        received.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "reply",
                            "reasoning_content": "retained reasoning",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 12,
                    "total_tokens": 32,
                    "prompt_cache_hit_tokens": 7,
                    "completion_tokens_details": {"reasoning_tokens": 9},
                },
            },
        )

    adapter = OpenAIModel(
        "deepseek-flash",
        provider="deepseek",
        thinking=thinking,
        reasoning_effort=effort,
        max_tokens=4096,
    )
    assert str(adapter.client.base_url) == "https://api.deepseek.com"
    assert adapter.client.api_key == "deepseek-test"
    await adapter.close()
    adapter.client = AsyncOpenAI(
        api_key="deepseek-test",
        base_url="https://example.test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    messages = [
        {"role": "system", "content": "policy"},
        {"role": "assistant", "content": "locally rendered reply"},
        {"role": "user", "content": "question"},
    ]
    tool = {
        "type": "function",
        "function": {"name": "lookup", "parameters": {"type": "object", "properties": {}}},
    }
    try:
        response = await adapter.chat(messages, [tool])
        messages += [response.assistant_message(), {"role": "user", "content": "followup"}]
        await adapter.chat(messages, [tool])
    finally:
        await adapter.close()
    assert received[0]["thinking"] == {"type": thinking}
    assert received[0].get("reasoning_effort") == effort
    assert received[0]["max_tokens"] == 4096
    assert received[0]["messages"][0]["role"] == "system"
    assert received[0]["messages"][1]["reasoning_content"] == ""
    assert "reasoning_content" not in messages[1]  # original history is not mutated
    assert received[1]["messages"][-2]["reasoning_content"] == "retained reasoning"
    assert response.cached_input_tokens == 7 and response.reasoning_tokens == 9
    assert response.output_tokens == 12  # includes reasoning; do not add it twice
    assert response.finish_reason == "stop"


async def test_loop_replays_tool_and_text_reasoning_across_turns(tmp_path, scripted_model):
    model = scripted_model(
        [
            ModelResponse(
                reasoning_content="tool reasoning",
                tool_calls=[ToolCall(id="unknown", name="unknown", arguments={})],
            ),
            ModelResponse(text="clarification", reasoning_content="text reasoning"),
            ModelResponse(text="done", reasoning_content="final reasoning"),
        ]
    )
    session = Session(user_id="test")
    tracer = Tracer(tmp_path)
    first = await run_turn(session, "first", model, Registry(), tracer)
    second = await run_turn(session, "second", model, Registry(), tracer)
    assert first.status == second.status == "text"
    assistants = [m for m in model.seen_messages[-1] if m["role"] == "assistant"]
    assert [m["reasoning_content"] for m in assistants] == ["tool reasoning", "text reasoning"]
    trace = next(tmp_path.rglob("*.jsonl")).read_text(encoding="utf-8")
    assert "tool reasoning" not in trace and "text reasoning" not in trace


async def test_truncation_does_not_execute_partial_tool_call(tmp_path, scripted_model):
    model = scripted_model(
        [
            ModelResponse(
                finish_reason="length",
                reasoning_tokens=10,
                output_tokens=20,
                tool_calls=[ToolCall(id="partial", name="unknown", arguments={})],
            )
        ]
    )
    session = Session(user_id="test")
    result = await run_turn(session, "question", model, Registry(), Tracer(tmp_path))
    assert result.status == "output_truncated"
    rows = [json.loads(line) for line in next(tmp_path.rglob("*.jsonl")).read_text().splitlines()]
    assert not any(r["event"] == "tool_result" for r in rows)
    assert session.total_tokens == 20
    assert rows[0]["finish_reason"] == "length"


async def test_runtime_keeps_role_options_separate(project, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    config_path = project / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["llm"]["provider"] = "deepseek"
    config["model_options"]["orchestrator"].update(thinking="enabled", reasoning_effort="low")
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    runtime = create_runtime(root=project, mode="multi")
    try:
        models = [runtime.model, runtime.specialist_model, runtime.reviewer_model]
        assert len({id(m) for m in models}) == 3
        assert [m.request_options["max_tokens"] for m in models] == [8192, 4096, 2048]
        assert models[0].request_options["reasoning_effort"] == "low"
        assert models[1].request_options["extra_body"]["thinking"]["type"] == "disabled"
        runtime.session.messages = [
            ModelResponse(text="reply", reasoning_content="keep").assistant_message()
        ]
        runtime.session.state["complete"] = True
        runtime.compact_history()
        assert runtime.session.messages[0]["reasoning_content"] == "keep"
    finally:
        await runtime.close_model()
        runtime.close()


async def test_openai_does_not_receive_deepseek_options(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    config = {
        "llm": {"deepseek": {"thinking": "enabled"}},
        "model_options": {"orchestrator": {"max_tokens": 123}},
    }
    model = build_model("openai", "test", config, None)
    try:
        assert model.request_options == {}
    finally:
        await model.close()


def test_deepseek_never_falls_back_to_old_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "old-test")
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        OpenAIModel("deepseek-flash", provider="deepseek")


@pytest.mark.parametrize(
    "options",
    [
        {"system_role": "developer"},
        {"thinking": "typo"},
        {"reasoning_effort": "low"},
        {"max_tokens": 0},
    ],
)
def test_invalid_deepseek_config_fails_before_request(monkeypatch, options):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    with pytest.raises(ValueError):
        OpenAIModel("deepseek-flash", provider="deepseek", **options)
