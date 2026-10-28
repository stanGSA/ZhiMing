from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str | None = None
    argument_error: bool = False


class ValidationMessage(str):
    """String-compatible validator feedback with a separate, stable retry identity."""

    def __new__(cls, message: str, *, retry_key: str):
        value = super().__new__(cls, message)
        value.retry_key = retry_key
        return value


class ToolResult(BaseModel):
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    code: str | None = None
    cached: bool = False
    # Local control metadata; neither model-facing results nor stored payloads need it.
    retry_key: str | None = Field(default=None, exclude=True)

    @classmethod
    def failure(cls, code: str, message: str) -> ToolResult:
        return cls(
            ok=False, code=code, error=str(message), retry_key=getattr(message, "retry_key", None)
        )


class ModelResponse(BaseModel):
    planned: bool = False  # Code-generated tool step; no model invocation or billed usage.
    text: str = ""
    model: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int | None = None
    usage_available: bool = True
    reasoning_content: str | None = None
    reasoning_tokens: int | None = None
    finish_reason: str | None = None

    def assistant_message(self) -> dict[str, Any]:
        """Preserve provider reasoning on every model message, including text-only turns."""
        import json

        message: dict[str, Any] = {"role": "assistant", "content": self.text or None}
        if self.reasoning_content is not None:
            message["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.name,
                        "arguments": c.raw_arguments
                        if c.argument_error
                        else json.dumps(c.arguments, ensure_ascii=False),
                    },
                }
                for c in self.tool_calls
            ]
        return message


class TurnOutcome(BaseModel):
    status: str
    text: str
    data: dict[str, Any] = Field(default_factory=dict)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
