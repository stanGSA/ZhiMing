"""PR61 review regressions: preserve compound times and avoid rejecting ordinary titles."""

from datetime import date

import pytest

from pipeline.bazi import title_findings, title_spans
from tests.pipeline.test_runner_bazi import make, written  # noqa: F401

TODAY = date(2026, 11, 8)
DECEMBER = (date(2026, 12, 1), date(2026, 12, 31))


@pytest.mark.parametrize(
    "title, low, high",
    [
        ("十二月中下旬：稳步推进", "2026-12-11", "2026-12-31"),
        ("十二月上中旬：先理顺流程", "2026-12-01", "2026-12-20"),
        ("12月上旬之后：逐渐回暖", "2026-12-01", "2026-12-31"),
        ("十二月中旬后：逐渐回暖", "2026-12-11", "2026-12-31"),
        ("中下旬：稳步推进", "2026-12-11", "2026-12-31"),
        ("月中之后：逐渐回暖", "2026-12-11", "2026-12-31"),
        ("这个月上旬：先理顺流程", "2026-11-01", "2026-11-10"),
        ("下个月中下旬：稳步推进", "2026-12-11", "2026-12-31"),
        ("下下个月月初：先理顺流程", "2027-01-01", "2027-01-10"),
        ("本月初：先理顺流程", "2026-11-01", "2026-11-10"),
        ("下个月中旬之后：逐渐回暖", "2026-12-11", "2026-12-31"),
        ("7月中到8月：先理顺流程", "2026-07-11", "2026-08-31"),
    ],
)
def test_compound_month_expressions_keep_their_anchor_and_extent(title, low, high):
    assert title_spans(title, *DECEMBER, TODAY) == [
        (date.fromisoformat(low), date.fromisoformat(high))
    ]


def test_a_relative_part_crosses_the_year_with_its_month():
    assert title_spans("下个月下旬", *DECEMBER, date(2026, 12, 15)) == [
        (date(2027, 1, 21), date(2027, 1, 31))
    ]


@pytest.mark.parametrize("title", ["十二月中下旬", "12月上旬之后"])
def test_late_december_citations_are_accepted_in_broad_month_parts(title):
    cited = [(date(2026, 12, 24), date(2026, 12, 31))]
    assert title_findings(title, *DECEMBER, cited, TODAY) == []


def test_a_correct_month_does_not_hide_a_wrong_part():
    cited = [(date(2026, 12, 1), date(2026, 12, 6))]
    assert title_findings("十二月中下旬", *DECEMBER, cited, TODAY)


def test_a_relative_month_does_not_borrow_the_requested_month():
    november = (date(2026, 11, 1), date(2026, 11, 30))
    assert title_findings("下个月上旬", *november, [november], TODAY)


@pytest.mark.parametrize("title", ["春风得意也要核实细节", "避免秋后算账，把分工说清", "你的底色"])
def test_non_calendar_titles_do_not_name_a_season_or_a_month_part(title):
    assert title_spans(title, *DECEMBER, TODAY) == []


@pytest.mark.parametrize("title", ["春季的沟通节奏", "夏天的沟通节奏", "秋季的沟通节奏"])
def test_explicit_seasons_outside_the_range_are_still_refused(title):
    assert title_findings(title, *DECEMBER, [], TODAY)


@pytest.mark.parametrize(
    "title, question, repairs",
    [
        ("十二月中下旬：稳步推进", "用八字看看2026年12月24日到2026年12月31日的事业运。", 0),
        ("12月上旬之后：逐渐回暖", "用八字看看2026年12月24日到2026年12月31日的事业运。", 0),
        ("避免秋后算账，把分工说清", "用八字看看2026年12月的事业运。", 0),
        # The scripted pipeline's current day is October 30, so 这个月 means October.
        ("这个月上旬：稳步推进", "用八字看看2026年11月的事业运。", 1),
    ],
)
async def test_titles_through_the_pipeline(make, title, question, repairs):  # noqa: F811
    def draft(messages):
        return written(messages).replace("【分层】这段时间的节奏", f"【分层】{title}")

    runtime, *_ = make(draft, written if repairs else draft)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["model_calls"], info["degraded"]) == (repairs, repairs + 1, None)
    if repairs:
        assert any(title in problem for problem in info["problems"][0])
    else:
        assert outcome.data["reading"]["sections"][0]["title"] == title
