from typing import Any, Literal

from pydantic import Field

from harness.models import StrictInput


class EmptyInput(StrictInput):
    pass


class StartInput(StrictInput):
    systems: list[Literal["astro", "bazi", "tarot", "name", "dream", "daily"]] | None = None
    requested_spread: Literal["single", "three_card", "decision"] | None = None
    question: str = Field(min_length=1, max_length=2000)
    parent_reading_id: str | None = Field(
        default=None,
        description="可选：跨会话回访或更正时，关联的本用户历史记录编号（来自最近记录或read_reading）",
    )


# Entry kinds of each knowledge partition; a test keeps this in step with the built KB.
LOOKUP_KINDS = {
    "tarot": ("card", "position"),
    "astro": ("planet", "sign", "house", "aspect", "planet_sign", "planet_house", "transit"),
    "bazi": (
        "stem",
        "branch",
        "hidden",
        "ten_god",
        "god_pillar",
        "element",
        "element_relation",
        "nayin",
        "relation",
        "convention",
    ),
    "name": ("grid", "shuli", "sancai", "element", "convention"),
    "dream": ("symbol", "convention"),
    "daily": ("day_element", "convention"),
}


class LookupInput(StrictInput):
    system: Literal["tarot", "astro", "bazi", "name", "dream", "daily"]
    kind: Literal[tuple(sorted({k for kinds in LOOKUP_KINDS.values() for k in kinds}))] = Field(
        description="条目类型，须属于该system："
        + "；".join(f"{system}={'/'.join(kinds)}" for system, kinds in LOOKUP_KINDS.items())
    )
    key: str = Field(
        min_length=1,
        description="精确key，照抄工具结果中的meaning_key或key；"
        "塔罗牌面为card_id:upright或card_id:reversed，如cups_four:upright；牌位如three_card:1",
    )


class ProfileInput(StrictInput):
    field: Literal[
        "name",
        "gender",
        "birth_local_dt",
        "birth_place",
        "time_known",
        "consultation_tz",
        "prefs_json",
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
    reading: str = Field(
        default="",
        max_length=500,
        description="可省略，由代码根据本次 ref_id 渲染事实附录；旧文本仍受事实校验",
    )


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
    title: str = Field(
        min_length=1,
        max_length=60,
        description="本层标题，用白话说对用户意味着什么，如“压力偏大，但能逼出成果”；"
        "用户明确询问专业结果时可写必要的名称或计算值并解释",
    )
    body: str = Field(
        min_length=1,
        max_length=1200,
        description="本层正文：先用白话说结论和生活中的表现，再交代依据、挑战与机遇、怎么应对；"
        "术语附白话解释；分行直接换行，不用HTML标签",
    )
    ref_ids: list[str] = Field(
        default_factory=list, description="本段依据的计算事实ref_id，挂在段落上，不必逐句绑定"
    )


class Reading(StrictInput):
    verdict: (
        Literal[
            "favorable",
            "steady",
            "pressured",
            "volatile",
            "suitable",
            "not_now",
            "conditional",
            "prefer_a",
            "prefer_b",
            "describe",
        ]
        | None
    ) = Field(default=None, description="summary第一句的表态，须与首句一致")
    question_type: Literal["timing", "decision", "trait", "tarot", "daily", "name", "dream"]
    systems_used: list[str] = Field(
        default_factory=list, description="可省略，由代码按本次实际调用的体系自动填入"
    )
    summary: str = Field(
        min_length=1,
        max_length=200,
        description="先表态：第一句用白话直接回答所问，前提放在第二句；"
        "用户明确询问专业结果时可写必要的名称或计算值并解释",
    )
    sections: list[Section] = Field(
        default_factory=list, max_length=6, description="分层分析正文，通常2-3层，每层约150-250字"
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="本次引用的计算事实ref_id列表；若sections已填ref_ids也可省略由代码自动汇总",
    )
    resonances: list[str] = Field(default_factory=list)
    tensions: list[Tension] = Field(default_factory=list)
    timeline: list[Timeline] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    closing: str = Field(default="", max_length=200, description="收尾一句")
    confidence: Confidence = Field(
        default_factory=lambda: Confidence(level="medium", reason="基于本次确定性计算结果整理。"),
        description="可省略，由代码按释义审核等级自动校准",
    )
    safety: Safety = Field(default_factory=lambda: Safety(flag=False, note=""))
    followups: list[str] = Field(default_factory=list)


class SectionPatch(StrictInput):
    index: int = Field(ge=0, lt=6, description="要修改的原草稿sections下标（从0开始）")
    title: str | None = Field(default=None, min_length=1, max_length=60)
    body: str | None = Field(default=None, min_length=1, max_length=1200)
    ref_ids: list[str] | None = None


class PatchReadingInput(StrictInput):
    verdict: (
        Literal[
            "favorable",
            "steady",
            "pressured",
            "volatile",
            "suitable",
            "not_now",
            "conditional",
            "prefer_a",
            "prefer_b",
            "describe",
        ]
        | None
    ) = None
    question_type: (
        Literal["timing", "decision", "trait", "tarot", "daily", "name", "dream"] | None
    ) = None
    systems_used: list[str] | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=200)
    section_patches: list[SectionPatch] = Field(
        default_factory=list,
        description="按index局部修改指定段落的title/body/ref_ids，其余已合规段落保持不变",
    )
    sections: list[Section] | None = Field(
        default=None, description="仅在需增删整组段落时提供；局部改某段优先用section_patches"
    )
    evidence: list[Evidence] | None = None
    resonances: list[str] | None = None
    tensions: list[Tension] | None = None
    timeline: list[Timeline] | None = None
    advice: list[str] | None = None
    closing: str | None = Field(default=None, max_length=200)
    confidence: Confidence | None = None
    safety: Safety | None = None
    followups: list[str] | None = None
