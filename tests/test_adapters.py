import json

import httpx
import pytest

from harness.llm import AnthropicModel, OpenAIModel, anthropic_messages


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
