from typing import Any, Literal

from pydantic import Field

from harness.models import StrictInput


class EmptyInput(StrictInput):
    pass


class StartInput(StrictInput):
    question: str = Field(min_length=1, max_length=2000)


class LookupInput(StrictInput):
    system: str
    kind: str
    key: str


class ProfileInput(StrictInput):
    field: Literal[
        "name",
        "gender",
        "birth_local_dt",
        "birth_place",
        "time_known",
        "tz",
        "calendar_input",
        "zishi_rule",
        "true_solar_time",
        "prefs_json",
        "lat",
        "lon",
        "location_id",
        "consultation_tz",
    ]
    value: Any
    evidence: str = Field(min_length=1)


class AskInput(StrictInput):
    question: str = Field(min_length=1, max_length=500)


class ReadInput(StrictInput):
    reading_id: str | None = None


class Evidence(StrictInput):
    ref_id: str
    reading: str = Field(min_length=1, max_length=500)


class Confidence(StrictInput):
    level: Literal["low", "medium", "high"]
    reason: str


class Safety(StrictInput):
    flag: bool
    note: str


class Tension(StrictInput):
    theme: str
    sides: list[str]
    how_to_read: str


class Timeline(StrictInput):
    period: str
    note: str


class Reading(StrictInput):
    question_type: Literal["timing", "decision", "trait", "tarot", "daily", "name", "dream"]
    systems_used: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=80)
    evidence: list[Evidence] = Field(min_length=1)
    resonances: list[str] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    timeline: list[Timeline] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    confidence: Confidence
    safety: Safety
    followups: list[str] = Field(default_factory=list)
