"""PR64 review: check each timed trading action, including correct acceptance paths."""

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_runner_bazi import dataset, make, written  # noqa: F401

PILOT = next(c for c in dataset("bazi_pilot") if c["id"] == "bazi_pilot_investment_risk")


@pytest.mark.parametrize(
    "text",
    [
        "8月可以全投而不是观望。",
        "8月不建议等待时机而要全仓。",
        "8月不要追涨而要分批买入。",
        "8月不宜追涨而应分批买入。",
        "8月避免冲动并适度加仓。",
        "8月不要追涨、可以分批买入。",
        "8月八字不能预测涨跌却适合加仓。",
        "八字不能预测收益所以8月适合小额度试探。",
        "8月别把八字当买卖依据且适合加仓。",
        "8月八字不能预测涨跌因此适合加仓。",
        "8月八字不能预测涨跌并且适合加仓。",
        "8月八字不能预测涨跌适合加仓。",
        "8月核实财务状况后适合买入。",
        "8月核实可投入金额并加仓。",
        "8月核实后可投入资金。",
        "8月可以先投入，再核实财务状况。",
        "8月不一定不适合加仓。",
        "8月并非不宜加仓。",
        "8月不要犹豫地加仓。",
        "不能说八字不能决定8月是否加仓。",
        "八字并非不能决定8月是否加仓。",
        "不能说八字能预测涨跌8月适合加仓。",
    ],
)
def test_restraining_one_action_does_not_exempt_a_recommendation(text):
    assert Bazi.trade_problems(text), text


@pytest.mark.parametrize(
    "period",
    [
        "下个月",
        "下下个月",
        "这个月",
        "本月",
        "下周",
        "这周",
        "本周",
        "今天",
        "明天",
        "后天",
        "2027年",
        "2027-08-08",
    ],
)
def test_shared_relative_dates_and_explicit_dates_are_time_anchors(period):
    assert Bazi.trade_problems(f"{period}适合买入。")


@pytest.mark.parametrize(
    "text",
    [
        "8月先核实你的可投入资金和风险承受能力。",
        "8月可以先核实财务状况和可投入金额。",
        "下个月先核实你的可投入资金和风险承受能力。",
        "8月确认可投入预算。",
        "8月核实可投入额度。",
        "8月评估额度。",
        "不能说八字能决定8月是否加仓。",
        "不能说八字可以决定8月是否加仓。",
        "8月不能仅凭八字决定买卖时点。",
        "8月没有依据说明适合加仓。",
        "8月不要加仓、买入。",
        "8月不宜加仓或买入。",
        "8月别把八字当买卖依据。",
        "8月八字不能决定仓位、买卖时点。",
        "整年没有哪一段出现足以支持“把积蓄全部投入”的信号。",
        "明年整体不宜把积蓄全部投入股市，更不适合“全押”这种集中投入方式。",
        "在波动明显的月份，把加仓决定延后几天再看。",
        "先核实可投入资金，再根据现实条件做决定。",
        "先写清买入条件，尤其留意三月这个时段。",
    ],
)
def test_reviewing_funds_and_denied_trades_still_pass(text):
    assert Bazi.trade_problems(text) == [], text


@pytest.mark.parametrize(
    "extra,repairs",
    [
        ("8月可以全投而不是观望。", 1),
        ("8月不要追涨而要分批买入。", 1),
        ("八字不能预测收益所以8月适合小额度试探。", 1),
        ("下个月适合加仓。", 1),
        ("8月先核实你的可投入资金和风险承受能力。", 0),
        ("不能说八字能决定8月是否加仓。", 0),
    ],
)
async def test_scope_checks_repair_only_the_recommended_trades(make, extra, repairs):  # noqa: F811
    runtime, composer, _ = make(lambda m: written(m, extra=extra), written, birth=PILOT["profile"])
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1 + repairs, repairs, None)
    if repairs:
        assert f"出问题的句子：“{extra}”" in composer.seen[1][0][-1]["content"]
    else:
        assert any(extra in s["body"] for s in outcome.data["reading"]["sections"])
