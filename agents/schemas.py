"""Structured messages between the orchestrator and specialists (no free-text dialogue)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from common.schemas import Confidence
from harness.models import StrictInput


class Timeframe(StrictInput):
    start: str = Field(description="用户指定区间的开始日期，YYYY-MM-DD")
    end: str = Field(description="结束日期，日期型含当天")
    tz: str | None = Field(default=None, description="咨询区间的IANA时区；不确定时省略")


class ConsultInput(StrictInput):
    system: str = Field(description="专家体系代码，如 astro、bazi、tarot")
    sub_question: str = Field(min_length=1, max_length=500)
    timeframe: Timeframe | None = None
    location_id: str | None = Field(
        default=None, description="已由 resolve_location 解析的出生地编号"
    )
    spread: Literal["single", "three_card", "decision"] | None = Field(
        default=None, description="仅塔罗：牌阵"
    )


class ReportPoint(StrictInput):
    ref_id: str
    text: str = Field(min_length=1, max_length=300)


class ReportInput(StrictInput):
    """What a specialist may write; signals are attached by the harness afterwards."""

    answer: str = Field(min_length=1, max_length=300)
    analysis: str = Field(
        default="",
        max_length=1500,
        description="本体系内的推演：各计算事实之间的作用关系、挑战与机遇、应对",
    )
    points: list[ReportPoint] = Field(min_length=1, max_length=12)
    missing: list[str] = Field(default_factory=list)
    confidence: Confidence


class SpecialistReport(BaseModel):
    system: str
    label: str
    status: Literal["ok", "needs_input", "failed"]
    answer: str = ""
    analysis: str = ""
    points: list[ReportPoint] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None
    needs_input: dict[str, Any] | None = None
    failure: str | None = None
    signals: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str
    latency_ms: float
    queue_ms: float = 0.0
    tokens: int
    model_calls: int
    # Snapshots are populated by the service, never written by the model. The version is a
    # conservative fallback for older reports without field-level dependencies.
    profile_version: int = 0
    profile_dependencies: dict[str, Any] | None = None
    # Set when a retry failed but this system's earlier valid report was kept.
    retained_previous: bool = False
