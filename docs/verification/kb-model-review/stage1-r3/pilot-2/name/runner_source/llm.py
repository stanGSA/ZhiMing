from __future__ import annotations

import json
import os
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    def __init__(
        self,
        model: str,
        timeout: float = 30,
        system_role: str = "system",
        *,
        provider: str = "openai",
        thinking: str = "disabled",
        reasoning_effort: str | None = None,
        max_tokens: int | None = None,
        api_key_env: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        http_client=None,
    ):
        from openai import AsyncOpenAI

        key_name = api_key_env or (
            "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
        )
        if not os.getenv(key_name):
            raise ValueError(f"未设置 {key_name}")
        self.provider = provider
        self.request_options = {}
        if provider == "deepseek":
            if system_role != "system":
                raise ValueError("DeepSeek requires system_role: system")
            if thinking not in ("disabled", "enabled"):
                raise ValueError("thinking must be disabled or enabled")
            if reasoning_effort not in (None, "low", "high", "max"):
                raise ValueError("unsupported DeepSeek reasoning_effort")
            if thinking == "disabled" and reasoning_effort is not None:
                raise ValueError("reasoning_effort requires enabled thinking")
            self.request_options["extra_body"] = {"thinking": {"type": thinking}}
            if reasoning_effort is not None:
                self.request_options["reasoning_effort"] = reasoning_effort
        if max_tokens is not None:
            if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
                raise ValueError("max_tokens must be a positive integer")
            self.request_options["max_tokens"] = max_tokens
        if temperature is not None:
            self.request_options["temperature"] = temperature
        self.model = model
        if system_role not in ("system", "developer"):
            raise ValueError("system_role must preserve privileged instructions")
        self.system_role = system_role
        self.request_attempts = 0
        self.client = AsyncOpenAI(
            api_key=os.environ[key_name],
            base_url=base_url
            or (
                (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com")
                if provider == "deepseek"
                else (os.getenv("OPENAI_BASE_URL") or None)
            ),
            timeout=timeout,
            max_retries=0,
            **({"http_client": http_client} if http_client is not None else {}),
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
        self.request_attempts += 1
        request_messages = []
        for original in messages:
            message = dict(original)
            if message["role"] == "system":
                message["role"] = self.system_role
            if self.provider == "deepseek" and message["role"] == "assistant":
                # Locally rendered terminal replies have no reasoning. Model-generated
                # reasoning is retained by ModelResponse.assistant_message, verbatim.
                message.setdefault("reasoning_content", "")
            request_messages.append(message)
        result = await self.client.chat.completions.create(
            model=self.model,
            messages=request_messages,
            tools=tools or None,
            **self.request_options,
        )
        message = result.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            raw = call.function.arguments
            try:
                arguments = json.loads(raw)
                if not isinstance(arguments, dict):
                    raise ValueError("object required")
                calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
            except (ValueError, TypeError):
                calls.append(
                    ToolCall(
                        id=call.id, name=call.function.name, raw_arguments=raw, argument_error=True
                    )
                )
        usage = result.usage
        return ModelResponse(
            text=message.content or "",
            model=result.model,
            reasoning_content=getattr(message, "reasoning_content", None),
            finish_reason=result.choices[0].finish_reason,
            reasoning_tokens=getattr(
                getattr(result.usage, "completion_tokens_details", None), "reasoning_tokens", None
            ),
            usage_available=usage is not None,
            tool_calls=calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=(
                cached
                if (
                    cached := getattr(
                        getattr(usage, "prompt_tokens_details", None), "cached_tokens", None
                    )
                )
                is not None
                else getattr(usage, "prompt_cache_hit_tokens", None)
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
    def __init__(
        self,
        model: str,
        timeout: float = 30,
        *,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float | None = None,
        http_client=None,
    ):
        from anthropic import AsyncAnthropic

        if not os.getenv(api_key_env):
            raise ValueError(f"未设置 {api_key_env}")
        self.model = model
        self.max_tokens = max_tokens
        self.request_options = {} if temperature is None else {"temperature": temperature}
        self.request_attempts = 0
        self.client = AsyncAnthropic(
            api_key=os.environ[api_key_env],
            timeout=timeout,
            max_retries=0,
            **({"base_url": base_url} if base_url else {}),
            **({"http_client": http_client} if http_client is not None else {}),
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
        self.request_attempts += 1
        system, converted = anthropic_messages(messages)
        tool_specs = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]
        result = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=converted,
            # A layered reading is submitted as one tool call; leave room for it.
            max_tokens=self.max_tokens,
            **({"tools": tool_specs} if tool_specs else {}),
            **self.request_options,
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


class RoleModelSpec(BaseModel):
    """One model role outside the runtime (a knowledge reviewer, later a rubric judge).

    The vendor is recorded with every result; the key is read from ``api_key_env`` and never
    stored. ``api`` selects the wire protocol, so any OpenAI-compatible service works.
    """

    model_config = ConfigDict(extra="forbid")
    vendor: str = Field(min_length=1)
    api: Literal["openai", "anthropic"]
    model: str = Field(min_length=1)
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    base_url: str | None = None
    # An address that should not be committed (a third-party relay) is read from here.
    base_url_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=4096, gt=0)
    # None preserves the historical role default (DeepSeek thinking disabled).
    thinking: Literal["disabled", "enabled"] | None = None
    reasoning_effort: Literal["low", "high", "max"] | None = None

    @model_validator(mode="after")
    def one_base_url(self):
        if self.base_url and self.base_url_env:
            raise ValueError("base_url 与 base_url_env 只能配置一个")
        if self.thinking is not None or self.reasoning_effort is not None:
            if self.api != "openai" or self.vendor.strip().lower() != "deepseek":
                raise ValueError("审核角色的 thinking/reasoning_effort 仅支持 DeepSeek")
        if self.reasoning_effort is not None and self.thinking != "enabled":
            raise ValueError("reasoning_effort requires enabled thinking")
        return self

    def endpoint(self) -> str | None:
        """The service address. An unset base_url_env is an error: the key belongs to that
        service and must never fall back to the vendor's default endpoint."""
        if self.base_url_env is None:
            return self.base_url
        value = os.getenv(self.base_url_env, "").strip()
        if not value:
            raise ValueError(f"未设置 {self.base_url_env}")
        return value


def role_model(spec: RoleModelSpec, timeout: float = 120, http_client=None) -> ChatModel:
    if spec.api == "anthropic":
        return AnthropicModel(
            spec.model,
            timeout,
            api_key_env=spec.api_key_env,
            base_url=spec.endpoint(),
            max_tokens=spec.max_tokens,
            temperature=spec.temperature,
            http_client=http_client,
        )
    return OpenAIModel(
        spec.model,
        timeout,
        provider="deepseek" if spec.vendor.strip().lower() == "deepseek" else "openai",
        thinking=spec.thinking or "disabled",
        reasoning_effort=spec.reasoning_effort,
        max_tokens=spec.max_tokens,
        api_key_env=spec.api_key_env,
        base_url=spec.endpoint(),
        temperature=spec.temperature,
        http_client=http_client,
    )
