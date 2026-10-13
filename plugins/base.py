from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harness.registry import Tool


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)
    ref_id: str
    system: str
    theme: str
    valence: float = Field(ge=-1, le=1)
    strength: float = Field(ge=0, le=1)
    horizon: Literal["trait", "timing", "moment", "psyche"]
    timeframe: str | None = None
    keywords: tuple[str, ...] = ()
    kb_ref: str
    kb_refs: tuple[str, ...] = ()
    rule_version: int
    reviewed: bool

    @field_validator("horizon", mode="before")
    @classmethod
    def legacy_horizon(cls, value):
        return {"long_term": "trait", "short_term": "timing"}.get(value, value)


@runtime_checkable
class DivinationPlugin(Protocol):
    name: str
    tools: list[Tool]
    required_profile: set[str]
    themes: set[str]
    kb_partition: str
    eval_dir: Path

    def extract_signals(self, results: list[dict]) -> list[Signal]: ...

    def validate_output(self, reading, state) -> str | None: ...
