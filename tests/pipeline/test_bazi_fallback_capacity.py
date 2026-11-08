"""PR #62 follow-up: bounded fallback output must not silently lose later facts."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pipeline.bazi import Bazi, keyword_sections, short_span
from pipeline.compose import parse
from pipeline.render import reading_args
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT, broken
from tests.pipeline.test_runner_bazi import dataset, make, written  # noqa: F401

PILOT = next(c for c in dataset("bazi_pilot") if c["id"] == "bazi_pilot_investment_risk")
DRAFTS = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r2_investment_drafts.json").read_text("utf-8")
)["drafts"]


@pytest.mark.parametrize("draft", DRAFTS, ids=["first", "repair"])
async def test_original_investment_drafts_fit_after_expansion(make, draft):  # noqa: F811
    # Exercise the original length failure without approving the drafts' investment claims.
    runtime, _, _ = make(written, birth=PILOT["profile"])
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    parsed, problems = parse(draft)
    assert not problems
    args, problems, _ = reading_args(
        parsed, Bazi(runtime).facts(runtime.session), question_type="timing", question=INVESTMENT
    )
    assert not problems
    assert Bazi.length_problems(args) == []
    assert len(args["sections"][1]["body"]) in (985, 869)


@pytest.mark.parametrize(
    "question",
    [INVESTMENT, "用八字看看2026年11月1日到11月3日的事业运。", "用八字看看下个月的事业运。"],
)
async def test_fallback_preserves_every_displayable_fact_within_six_sections(make, question):  # noqa: F811
    runtime, _, _ = make(broken, broken, birth=PILOT["profile"])
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    reading = outcome.data["reading"]
    facts = [f for f in Bazi(runtime).facts(runtime.session) if f.label != "约定"]
    assert any(f.label == "流期与原局" for f in facts)
    sections = reading["sections"]
    assert len(sections) <= 6
    assert {r for s in sections for r in s["ref_ids"]} == {f.ref for f in facts}
    for fact in facts:
        assert any(fact.ref in s["ref_ids"] and fact.text in s["body"] for s in sections)
    assert all(len(s["body"]) <= 1200 and s["body"].endswith("。") for s in sections)
    if question == INVESTMENT:
        assert reading["summary"].split("。")[0] == "不能依据八字作这类重大现实决定"
        assert reading["safety"]["flag"]


def test_indivisible_overflow_is_counted_without_cutting_a_sentence():
    rows = [("四柱", "甲" * 699 + "。", f"R{i}") for i in range(7)]
    sections, omitted = keyword_sections(rows)
    assert len(sections) == 6 and omitted == 1
    assert [r for s in sections for r in s["ref_ids"]] == [f"R{i}" for i in range(6)]
    assert all(s["body"] == rows[0][1] for s in sections)


async def test_unavoidable_omissions_are_disclosed(make):  # noqa: F811
    runtime, _, _ = make(broken, broken)
    await runtime.turn(INVESTMENT)
    system = Bazi(runtime)
    facts = [f for f in system.facts(runtime.session) if f.label != "约定"]
    # Preserve valid refs but simulate facts too large to share one section.
    oversized = [replace(f, text=f.text + "，" + "说明" * 400) for f in facts[:7]]
    args = system.degraded(
        runtime.session, oversized, "timing", INVESTMENT, False, safety_only=False
    )
    assert len(args["sections"]) == 6
    assert any("另有1项依据未在正文展开" in item for item in args["advice"])
    assert len(args["evidence"]) == 7


@pytest.mark.parametrize(
    "start,end,tz,range_start,expected",
    [
        (
            "2026-12-31T16:00:00+00:00",
            "2027-01-01T16:00:00+00:00",
            "Asia/Shanghai",
            "2027-01-01",
            "1月1日",
        ),
        (
            "2027-12-31T04:00:00+00:00",
            "2028-01-01T04:00:00+00:00",
            "Asia/Shanghai",
            "2027-01-01",
            "12月31日至2028年1月1日",
        ),
        (
            "2026-12-31T04:00:00+00:00",
            "2027-01-01T04:00:00+00:00",
            "Asia/Shanghai",
            "2027-01-01",
            "2026年12月31日至1月1日",
        ),
        (
            "2026-11-01T08:30:00+00:00",
            "2026-11-02T08:00:00+00:00",
            "America/Los_Angeles",
            "2026-11-01",
            "11月1日",
        ),
        (
            "2027-01-01T04:00:00+00:00",
            "2027-01-01T16:00:00.000001+00:00",
            "Asia/Shanghai",
            "2027-01-01",
            "1月1日至1月2日",
        ),
        (
            "2027-12-31T04:00:00+00:00",
            "2028-01-01T04:00:00+00:00",
            "Asia/Shanghai",
            None,
            "12月31日至2028年1月1日",
        ),
    ],
)
def test_short_dates_respect_local_years_and_exclusive_midnight(
    start, end, tz, range_start, expected
):
    assert short_span({"start_utc": start, "end_utc": end}, tz, range_start) == expected
