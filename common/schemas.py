from typing import Any, Literal

from pydantic import Field

from harness.models import StrictInput


class EmptyInput(StrictInput):
    pass


class StartInput(StrictInput):
    question: str = Field(min_length=1, max_length=2000)
    parent_reading_id: str | None = Field(
        default=None,
        description="可选：跨会话回访或更正时，关联的本用户历史记录编号（来自最近记录或read_reading）",
    )


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
        "system_weights",
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


class Section(StrictInput):
    title: str = Field(min_length=1, max_length=60, description="本层标题，如“核心碰撞：辰戌相冲”")
    body: str = Field(
        min_length=1,
        max_length=1200,
        description="本层分析正文：作用关系、挑战与机遇、怎么应对；可分行写要点",
    )
    ref_ids: list[str] = Field(
        default_factory=list, description="本段依据的计算事实ref_id，挂在段落上，不必逐句绑定"
    )


class Reading(StrictInput):
    question_type: Literal["timing", "decision", "trait", "tarot", "daily", "name", "dream"]
    systems_used: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=200, description="定调：第一句直接回答问题")
    sections: list[Section] = Field(
        default_factory=list, max_length=6, description="分层分析正文，通常2-5层"
    )
    evidence: list[Evidence] = Field(min_length=1)
    resonances: list[str] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    timeline: list[Timeline] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    closing: str = Field(default="", max_length=200, description="收尾一句")
    confidence: Confidence
    safety: Safety
    followups: list[str] = Field(default_factory=list)
