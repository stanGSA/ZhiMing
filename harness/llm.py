from __future__ import annotations

import json
import os
from typing import Any, Protocol

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from harness.models import ModelResponse, ToolCall


class ChatModel(Protocol):
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResponse: ...


def _transient(exc: BaseException) -> bool:
    return (
        getattr(exc, "status_code", None) in (408, 429, 500, 502, 503, 504)
        or isinstance(exc, TimeoutError)
        or type(exc).__name__ in ("APITimeoutError", "APIConnectionError")
    )


class OpenAIModel:
    def __init__(self, model: str, timeout: float = 30):
        from openai import AsyncOpenAI

        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("未设置 OPENAI_API_KEY")
        self.model = model
        self.client = AsyncOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            timeout=timeout,
            max_retries=0,
        )

    async def close(self) -> None:
        await self.client.close()

    @retry(
        retry=retry_if_exception(_transient),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(min=0.2, max=3),
        reraise=True,
    )
    async def chat(self, messages, tools) -> ModelResponse:
        result = await self.client.chat.completions.create(
            model=self.model, messages=messages, tools=tools or None
        )
        message = result.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            arguments = json.loads(call.function.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        usage = result.usage
        return ModelResponse(
            text=message.content or "",
            model=result.model,
            tool_calls=calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=getattr(
                getattr(usage, "prompt_tokens_details", None), "cached_tokens", None
            ),
        )


def anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system = "\n".join(m.get("content", "") for m in messages if m["role"] == "system")
    converted = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "tool":
            out_role = "user"
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": message["content"],
                    "is_error": not json.loads(message["content"]).get("ok", True),
                }
            ]
        else:
            out_role = role
            blocks = []
            if message.get("content"):
                blocks.append({"type": "text", "text": message["content"]})
            for call in message.get("tool_calls", []):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["function"]["name"],
                        "input": json.loads(call["function"]["arguments"]),
                    }
                )
        if not blocks:
            continue
        if converted and converted[-1]["role"] == out_role:
            converted[-1]["content"].extend(blocks)
        else:
            converted.append({"role": out_role, "content": blocks})
    return system, converted


class AnthropicModel:
    def __init__(self, model: str, timeout: float = 30):
        from anthropic import AsyncAnthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("未设置 ANTHROPIC_API_KEY")
        self.model = model
        self.client = AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"], timeout=timeout, max_retries=0
        )

    async def close(self) -> None:
        await self.client.close()

    @retry(
        retry=retry_if_exception(_transient),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(min=0.2, max=3),
        reraise=True,
    )
    async def chat(self, messages, tools) -> ModelResponse:
        system, converted = anthropic_messages(messages)
        result = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=converted,
            max_tokens=4096,
            tools=[
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ],
        )
        text = "".join(block.text for block in result.content if block.type == "text")
        calls = [
            ToolCall(id=block.id, name=block.name, arguments=block.input)
            for block in result.content
            if block.type == "tool_use"
        ]
        return ModelResponse(
            text=text,
            model=result.model,
            tool_calls=calls,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
