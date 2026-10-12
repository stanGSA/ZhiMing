from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from harness.registry import Tool


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)
    ref_id: str
    system: str
    theme: str
    valence: float = Field(ge=-1, le=1)
    strength: float = Field(ge=0, le=1)
    horizon: str
    timeframe: str | None = None
    keywords: tuple[str, ...] = ()
    kb_ref: str
    rule_version: int
    reviewed: bool


class DivinationPlugin(Protocol):
    name: str
    tools: list[Tool]
    required_profile: set[str]
    themes: set[str]
    kb_partition: str
    eval_dir: Path

    def extract_signals(self, results: list[dict]) -> list[Signal]: ...
