from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    raw_arguments: str | None = None
    argument_error: bool = False


class ToolResult(BaseModel):
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    code: str | None = None
    cached: bool = False

    @classmethod
    def failure(cls, code: str, message: str) -> ToolResult:
        return cls(ok=False, code=code, error=message)


class ModelResponse(BaseModel):
    text: str = ""
    model: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int | None = None
    usage_available: bool = True


class TurnOutcome(BaseModel):
    status: str
    text: str
    data: dict[str, Any] = Field(default_factory=dict)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
