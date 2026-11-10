"""PR #68 review: verdict scope, nested denials and unclipped flow-month starts."""

from datetime import date
from types import SimpleNamespace

import pytest

from pipeline.bazi import Bazi, start_findings
from plugins.bazi.calculator import bazi_period, compute_bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import INVESTMENT_CASE
from tests.pipeline.test_bazi_pilot_r9 import make_at  # noqa: F401
from tests.pipeline.test_runner_bazi import facts_in, make, written  # noqa: F401


@pytest.mark.parametrize("separator", ["；", ";", "。", "，", ",", "，但"])
def test_another_subjects_verdict_cannot_exempt_a_timed_trade(separator):
    assert Bazi.trade_problems(f"8月适合加仓{separator}外出旅游不太合适。")


@pytest.mark.parametrize(
    "verdict",
    [
        "不是完全不合适",
        "并不是那么不合适",
        "不算不合适",
        "没有不合适",
        "未必很不合适",
        "不一定很不合适",
        "并非全然不合适",
        "谈不上特别不合适",
    ],
)
def test_a_hedged_or_double_denial_is_not_plain_restraint(verdict):
    assert Bazi.trade_problems(f"8月加仓{verdict}。")


@pytest.mark.parametrize("verdict", ["完全不合适", "根本不适合", "并不明智", "不太合适"])
def test_strengthening_a_plain_denial_still_holds_back_the_trade(verdict):
    assert Bazi.trade_problems(f"8月加仓{verdict}。") == []


@pytest.mark.parametrize(
    "prefix", ["不是在", "并非要到", "不是等到", "根本不是在", "不在", "并不在", "没在", "未在"]
)
def test_a_prepositional_denial_of_a_festival_boundary_passes(prefix):
    assert Bazi.festival_problems(f"{prefix}春节之后进入流年丁未，而是在立春。") == []


@pytest.mark.parametrize(
    "prefix", ["不是在", "并非要到", "不是等到", "根本不是在", "不在", "并不在", "没在", "未在"]
)
def test_a_prepositional_denial_of_a_month_boundary_passes(prefix):
    assert (
        start_findings(
            f"{prefix}下旬之后进入流月庚子，而是在12月7日。",
            date(2026, 12, 1),
            date(2026, 12, 31),
            {"庚子": [date(2026, 12, 7)]},
        )
        == []
    )


@pytest.mark.parametrize("prefix", ["不能说不是在", "并非不是在", "不完全是在", "不一定要到"])
def test_a_turned_or_hedged_time_denial_still_needs_checking(prefix):
    assert Bazi.festival_problems(f"{prefix}春节之后进入流年丁未。")
    assert start_findings(
        f"{prefix}下旬之后进入流月庚子。",
        date(2026, 12, 1),
        date(2026, 12, 31),
        {"庚子": [date(2026, 12, 7)]},
    )


@pytest.mark.parametrize("tz, day", [("Asia/Shanghai", 7), ("America/Los_Angeles", 6)])
@pytest.mark.parametrize(
    "start, end, granularity",
    [
        ("2026-12-01", "2026-12-31", "month"),
        ("2026-12-20", "2026-12-31", "month"),
        ("2026-12-25", "2026-12-25", "day"),
        ("2027-01-01", "2027-01-03", "day"),
    ],
)
def test_query_boundaries_do_not_change_the_actual_flow_month_start(
    tz, day, start, end, granularity
):
    chart = compute_bazi("1991-02-26 15:05", "Asia/Shanghai", 120.15, "male")
    period = bazi_period(chart, start, end, granularity, tz)
    session = SimpleNamespace(
        state={"bazi_question_type": "timing", "bazi_period_result": period},
        calendar_anchor="2026-11-10",
    )
    args = {"sections": [{"title": "这段时间", "body": "12月上旬起进入流月庚子。"}]}
    assert Bazi(None).section_findings(args, [], session) == []

    args["sections"][0]["body"] = "12月下旬起进入流月庚子。"
    found = Bazi(None).section_findings(args, [], session)
    assert len(found) == 1
    assert f"实际从12月{day}日开始" in found[0][0]


async def test_a_correct_festival_denial_needs_no_repair(make_at):  # noqa: F811
    def denied(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流年" and "丁未" in text
        ]
        return written(messages, extra=f"不是在春节之后进入{{{{{alias}}}}}，而是在立春。")

    _, _, outcome = await make_at("bazi_pilot_investment_risk", denied, written)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


async def test_an_explicit_trade_before_a_semicolon_is_repaired(make):  # noqa: F811
    runtime, _, _ = make(
        lambda m: written(m, extra="8月适合加仓；外出旅游不太合适。"),
        written,
        birth=INVESTMENT_CASE["profile"],
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
