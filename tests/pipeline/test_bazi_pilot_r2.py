"""Bazi pilot r1 findings (docs/verification/p3/bazi-pilot/review.md), fixed in r2.

1. A section title outside the computed range passed (“先甜后磨的上半年尾巴” over 7–12月).
2. A denial of certainty in quotation marks was refused (“不是‘必然发财’”) where the same
   words without them pass.
3. The note on an overseas birth now says that the birth clock and the dates' clock differ.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from common.output_policy import certainty_claim
from pipeline.bazi import title_findings, title_spans
from tests.pipeline.test_runner_bazi import LOS_ANGELES, NEXT_MONTH, make, planned  # noqa: F401
from tests.pipeline.test_runner_bazi import written as bazi_written

PILOT = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r1_titles.json").read_text("utf-8")
)
RUN_DAY = date(2026, 11, 8)
ESCAPE = ("bazi_pilot_typed_birth#1", "先甜后磨的上半年尾巴")


def findings(section, today=RUN_DAY):
    start, end = (date.fromisoformat(d) for d in section["range"])
    cited = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in section["cited"]]
    return title_findings(section["title"], start, end, cited, today)


# ---- 1. section titles ---------------------------------------------------------------------


def test_the_pilot_escape_is_refused_and_every_other_pilot_title_accepted():
    """All 34 sections of the 12 timing answers: only the known escape is refused."""
    refused = [(s["case"], s["title"]) for s in PILOT["sections"] if findings(s)]
    assert refused == [ESCAPE]
    assert len(PILOT["sections"]) == 34


def test_the_escape_names_what_is_wrong():
    section = next(s for s in PILOT["sections"] if (s["case"], s["title"]) == ESCAPE)
    (problem,) = findings(section)
    assert "1月1日至6月30日" in problem and "2026-07-01至2026-12-31" in problem


SECOND_HALF = (date(2026, 7, 1), date(2026, 12, 31))
JULY = (date(2026, 7, 1), date(2026, 7, 6))  # 甲午 before 小暑
YI_WEI = (date(2026, 7, 7), date(2026, 8, 7))
GENG_ZI = (date(2026, 12, 7), date(2026, 12, 31))
DECEMBER = (date(2026, 12, 1), date(2026, 12, 31))
JI_HAI = (date(2026, 12, 1), date(2026, 12, 6))


@pytest.mark.parametrize(
    "title, span, cited",
    [
        # Accepted: months and parts of a year the range holds, citing a period in them.
        ("七月先甜后紧", SECOND_HALF, [JULY]),
        ("7月中到8月初，压力感最明显的一段", SECOND_HALF, [YI_WEI]),
        ("八月到九月：拉扯之后见温暖", SECOND_HALF, [YI_WEI]),  # 乙未 runs into 8月
        ("十月到年底：竞争感与回暖交替", SECOND_HALF, [GENG_ZI]),
        ("下半年整体起伏", SECOND_HALF, [JULY, GENG_ZI]),
        ("今年下半年：先紧后松", SECOND_HALF, [JULY]),
        ("年底有回暖", SECOND_HALF, [GENG_ZI]),
        # A section that runs on past its title (pilot typed#2) is not refused.
        ("九月到十月有联结机会", SECOND_HALF, [(date(2026, 9, 7), date(2026, 10, 8)), GENG_ZI]),
        # Parts of a single month.
        ("上旬：变动多", DECEMBER, [JI_HAI]),
        ("中下旬：关系回暖", DECEMBER, [GENG_ZI]),
        ("月中之后转向流程", DECEMBER, [GENG_ZI]),
        ("上旬先稳住", DECEMBER, [(date(2026, 12, 7), date(2026, 12, 31))]),  # starts within slack
        # No time in the title, or no period cited.
        ("先把边界讲清楚", SECOND_HALF, [JULY]),
        ("十二月：把话说开", SECOND_HALF, []),
    ],
)
def test_titles_a_correct_reading_may_write(title, span, cited):
    assert title_findings(title, *span, cited, RUN_DAY) == [], title


@pytest.mark.parametrize(
    "title, span, cited",
    [
        # Still refused: a time outside the range, or a section whose periods are all elsewhere.
        ("先甜后磨的上半年尾巴", SECOND_HALF, [JULY]),
        ("年初先别急着推进", SECOND_HALF, [JULY]),
        ("上半年：关系升温", SECOND_HALF, []),
        ("三月到五月", SECOND_HALF, [JULY]),
        ("明年七月", SECOND_HALF, [JULY]),
        ("十二月：关系回暖", SECOND_HALF, [JULY]),
        ("七月先甜后紧", SECOND_HALF, [GENG_ZI]),
        ("下旬：关系回暖", DECEMBER, [JI_HAI]),
        ("月初先稳住", DECEMBER, [(date(2026, 12, 21), date(2026, 12, 31))]),
        # A relative word names a month outside the range (asked on 2026-11-08 about 12月).
        ("这个月先稳住", DECEMBER, [JI_HAI]),
    ],
)
def test_titles_still_refused(title, span, cited):
    assert title_findings(title, *span, cited, RUN_DAY), title


def test_title_spans_read_the_common_wordings():
    assert title_spans("7月中到8月初", *SECOND_HALF, RUN_DAY) == [
        (date(2026, 7, 11), date(2026, 8, 10))
    ]
    assert title_spans("十月到年底", *SECOND_HALF, RUN_DAY) == [
        (date(2026, 10, 1), date(2026, 12, 31))
    ]
    assert title_spans("月中之后", *DECEMBER, RUN_DAY) == [(date(2026, 12, 11), date(2026, 12, 31))]
    assert title_spans("上旬", *SECOND_HALF, RUN_DAY) == []  # not a single month


async def test_a_title_outside_the_range_is_repaired_with_the_title_quoted(make):  # noqa: F811
    def wrong_title(messages):
        return bazi_written(messages).replace("【分层】这段时间的节奏", "【分层】上半年的尾巴")

    runtime, composer, events = make(wrong_title, bazi_written)
    outcome = await runtime.turn("用八字看看我今年下半年的感情运。")
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert any("上半年的尾巴" in p for p in info["problems"][0])
    repair = next(e for e in events if e["event"] == "pipeline_stage" and e["stage"] == "repair")
    assert "上半年的尾巴" in next(iter(repair["quotes"].values()))


# ---- 2. a quoted denial of certainty ---------------------------------------------------------


def quoted(text: str, word: str) -> str:
    return text.replace(word, f"“{word}”", 1)


@pytest.mark.parametrize(
    "text, word",
    [
        ("传统上偏财这类标签对应的不是必然发财，而是先核实成本。", "必然发财"),
        ("这并非必然的结果。", "必然的结果"),
        ("合不等于一定会顺利。", "一定会顺利"),
        # Still refused, with or without quotation marks.
        ("你必然发财。", "必然发财"),
        ("这不是坏事，必然发财。", "必然发财"),
        ("不是必然发财，而是一定会发财。", "一定会发财"),
        ("不能说不是必然发财。", "必然发财"),
        ("并非不是必然发财。", "必然发财"),
        ("偏财不是必然发财，但其实一定会发财。", "一定会发财"),
        ("这不是坏事，你注定会成功。", "注定会成功"),
    ],
)
def test_quotation_marks_do_not_change_what_is_refused(text, word):
    assert certainty_claim([quoted(text, word)]) == certainty_claim([text])


def test_the_pilot_sentence_is_accepted_and_assertions_are_not():
    sentence = (
        "传统上偏财这类标签对应的不是“必然发财”，而是探索机会时先核实成本、不据符号做投资预测。"
    )
    assert certainty_claim([sentence]) is None
    assert certainty_claim(["你会“必然发财”。"]) == "必然"
    assert certainty_claim(["这不是坏事，“必然发财”。"]) == "必然"


# ---- 3. the note on an overseas birth --------------------------------------------------------


async def test_the_note_separates_the_birth_clock_from_the_dates_clock(make):  # noqa: F811
    runtime, *_ = make(bazi_written, birth={**LOS_ANGELES, "true_solar_time": False})
    outcome = await runtime.turn(NEXT_MONTH)
    closing = outcome.data["reading"]["closing"]
    assert "出生时刻按固定UTC+8排盘" in closing
    assert "日期按出生地洛杉矶的时区（America/Los_Angeles）计算" in closing
