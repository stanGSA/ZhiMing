from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harness.registry import Tool
from knowledge.review import ReviewStatus, review_status


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
    review_status: ReviewStatus

    @field_validator("horizon", mode="before")
    @classmethod
    def legacy_horizon(cls, value):
        return {"long_term": "trait", "short_term": "timing"}.get(value, value)

    @model_validator(mode="before")
    @classmethod
    def legacy_reviewed(cls, data):
        # Saved readings and daily caches from before the three levels carry ``reviewed``.
        if isinstance(data, dict) and "reviewed" in data:
            level = review_status(data)
            data = {k: v for k, v in data.items() if k != "reviewed"}
            data.setdefault("review_status", level)
        return data


# Copied from an entry into tool results; ``reviewed`` stays the human flag beside the level.
MEANING_FIELDS = ("text", "keywords", "theme_map", "reviewed", "review_status", "ref_id")


def meaning_view(meaning: dict) -> dict:
    """What the model sees of a meaning: text and review state (cached results may be old)."""
    return dict(
        text=meaning["text"],
        reviewed=meaning.get("reviewed") is True,
        review_status=review_status(meaning),
    )


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
