import json

import httpx
import pytest

from harness.llm import AnthropicModel, OpenAIModel, anthropic_messages
from harness.loop import run_turn
from harness.models import StrictInput
from harness.registry import Registry, Tool
from harness.session import Session
from harness.trace import Tracer


@pytest.mark.parametrize(
    "tool_name,repair",
    [("submit_reading", True), ("submit_report", True), ("update_profile", False)],
)
async def test_quote_recovery_only_applies_to_reports(monkeypatch, tool_name, repair):
    from types import SimpleNamespace as NS

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    adapter = OpenAIModel("synthetic")
    raw = '{"body":"起运就是"人生阶段分段"的意思。"}'

    async def respond(**kwargs):
        return NS(
            model="synthetic",
            usage=None,
            choices=[
                NS(
                    finish_reason="tool_calls",
                    message=NS(
                        content=None,
                        tool_calls=[NS(id="quote", function=NS(name=tool_name, arguments=raw))],
                    ),
                )
            ],
        )

    monkeypatch.setattr(adapter.client.chat.completions, "create", respond)
    try:
        result = await adapter.chat([], [])
    finally:
        await adapter.close()
    call = result.tool_calls[0]
    assert call.arguments_repaired is repair
    assert call.argument_error is not repair
    assert call.raw_arguments == raw
    if repair:
        assert call.arguments["body"] == '起运就是"人生阶段分段"的意思。'


@pytest.mark.parametrize("system_role", ["system", "developer"])
async def test_openai_sdk_protocol_with_mock_http(monkeypatch, system_role):
    from openai import AsyncOpenAI

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    received = []

    def respond(request):
        received.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-test",
                                    "type": "function",
                                    "function": {"name": "get_profile", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 3,
                    "total_tokens": 12,
                    "prompt_tokens_details": {"cached_tokens": 4},
                },
            },
        )

    adapter = OpenAIModel("test-model", system_role=system_role)
    await adapter.client.close()
    adapter.client = AsyncOpenAI(
        api_key="test-placeholder",
        base_url="https://example.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    try:
        messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "test"}]
        result = await adapter.chat(messages, [])
        assert received[0]["messages"][0] == {"role": system_role, "content": "policy"}
        assert messages[0]["role"] == "system"
        assert result.tool_calls[0].name == "get_profile"
        assert result.input_tokens == 9 and result.output_tokens == 3
        assert result.model == "test-model"
        assert result.cached_input_tokens == 4
        assert received[0]["model"] == "test-model"
    finally:
        await adapter.client.close()


async def test_anthropic_sdk_protocol_with_mock_http(monkeypatch):
    from anthropic import AsyncAnthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    received = []

    def respond(request):
        received.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": [
                    {"type": "tool_use", "id": "tool-test", "name": "get_profile", "input": {}}
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 11, "output_tokens": 4},
            },
        )

    adapter = AnthropicModel("test-model")
    await adapter.client.close()
    adapter.client = AsyncAnthropic(
        api_key="test-placeholder",
        base_url="https://example.test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    try:
        result = await adapter.chat(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "test"}], []
        )
        assert result.tool_calls[0].name == "get_profile"
        assert result.input_tokens == 11 and result.output_tokens == 4
        assert result.model == "test-model"
        assert received[0]["system"] == "sys"
    finally:
        await adapter.client.close()


def anthropic_adapter(monkeypatch, content, stop_reason, usage=None):
    """An adapter whose HTTP client returns one fixed Messages API response to every call."""
    from anthropic import AsyncAnthropic

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    adapter = AnthropicModel("test-model")
    adapter.calls = 0

    def respond(request):
        adapter.calls += 1
        return httpx.Response(
            200,
            json={
                "id": "test",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": content,
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": usage or {"input_tokens": 11, "output_tokens": 4},
            },
        )

    adapter.client = AsyncAnthropic(
        api_key="test-placeholder",
        base_url="https://example.test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    return adapter


async def test_anthropic_max_tokens_stops_before_partial_tool_call(monkeypatch, tmp_path):
    # Cut off mid tool_use: the API still returns the block, with whatever input it had parsed.
    # Here the partial input even passes the schema, so only the stop reason can catch it.
    adapter = anthropic_adapter(
        monkeypatch,
        [
            {"type": "text", "text": "我先提交解读。"},
            {"type": "tool_use", "id": "tool-cut", "name": "submit", "input": {"text": "下个月"}},
        ],
        "max_tokens",
    )

    class Draft(StrictInput):
        text: str
        advice: list[str] = []

    executed = []
    registry = Registry()
    registry.register(
        Tool(
            "submit",
            "submit a reading",
            Draft,
            lambda args, session: executed.append(args) or {"ok": True},
        )
    )
    session = Session(user_id="test")
    try:
        result = await run_turn(
            session, "下个月适合跳槽吗？", adapter, registry, Tracer(tmp_path), max_steps=2
        )
    finally:
        await adapter.close()
    assert result.status == "output_truncated"
    assert executed == [] and adapter.calls == 1
    assert not any(m["role"] == "tool" for m in session.messages)
    trace = [
        json.loads(line)
        for line in next(tmp_path.rglob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    assert [row["finish_reason"] for row in trace if row["event"] == "model_response"] == ["length"]


@pytest.mark.parametrize(
    "stop_reason,finish_reason",
    [
        ("tool_use", "tool_calls"),
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("model_context_window_exceeded", "length"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
    ],
)
async def test_anthropic_stop_reason_maps_to_finish_reason(monkeypatch, stop_reason, finish_reason):
    adapter = anthropic_adapter(monkeypatch, [{"type": "text", "text": "ok"}], stop_reason)
    try:
        result = await adapter.chat([{"role": "user", "content": "test"}], [])
    finally:
        await adapter.close()
    assert result.finish_reason == finish_reason


async def test_anthropic_cache_reads_reported_like_openai(monkeypatch):
    adapter = anthropic_adapter(
        monkeypatch,
        [{"type": "text", "text": "ok"}],
        "end_turn",
        {
            "input_tokens": 11,
            "output_tokens": 4,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 5,
        },
    )
    try:
        cached = await adapter.chat([{"role": "user", "content": "test"}], [])
    finally:
        await adapter.close()
    # Same definition as OpenAI's prompt_tokens / cached_tokens: the cached part of the whole
    # prompt, so a cache-hit rate can never exceed 100% and the budget counts every token.
    assert cached.input_tokens == 46 and cached.cached_input_tokens == 30
    assert cached.output_tokens == 4

    adapter = anthropic_adapter(monkeypatch, [{"type": "text", "text": "ok"}], "end_turn")
    try:
        unreported = await adapter.chat([{"role": "user", "content": "test"}], [])
    finally:
        await adapter.close()
    assert unreported.input_tokens == 11 and unreported.cached_input_tokens is None


def test_anthropic_parallel_tool_messages_are_grouped():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "a", "function": {"name": "lookup", "arguments": "{}"}},
                {"id": "b", "function": {"name": "lookup", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "a", "content": '{"ok":true,"data":{}}'},
        {"role": "tool", "tool_call_id": "b", "content": '{"ok":false,"data":{}}'},
    ]
    system, converted = anthropic_messages(messages)
    assert system == "sys"
    assert len(converted[-1]["content"]) == 2
    assert converted[-1]["content"][1]["is_error"] is True


@pytest.mark.parametrize(
    "kind,key", [(OpenAIModel, "OPENAI_API_KEY"), (AnthropicModel, "ANTHROPIC_API_KEY")]
)
def test_missing_key_fails_early(monkeypatch, kind, key):
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        kind("test-model")
