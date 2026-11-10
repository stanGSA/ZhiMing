"""PR66: restraint must negate trading, rather than caution or a missed opportunity."""

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_runner_bazi import dataset, make, written  # noqa: F401

PILOT = next(c for c in dataset("bazi_pilot") if c["id"] == "bazi_pilot_investment_risk")


@pytest.mark.parametrize(
    "text",
    [
        "8月岂能错过加仓机会。",
        "8月怎么会错过加仓机会。",
        "下个月岂能错过买入机会。",
        "明年怎么会错过全押机会。",
        "8月买入谨慎型产品。",
        "8月投入谨慎型基金。",
        "下个月买入冷静型组合。",
        "8月买入慎重策略基金。",
        "8月买入需要谨慎型产品。",
        "8月买入核实型基金。",
        "8月投入确认策略产品。",
        "8月不太需要谨慎买入。",
        "8月并不需要谨慎加仓。",
        "下个月并不需要小心投入。",
        "明年不算需要冷静买入的年份。",
        "8月算不上需要慎重加仓的月份。",
        "8月不像是需要谨慎买入的月份。",
        "8月不能说需要谨慎加仓。",
        "8月谈不上需要谨慎加仓。",
    ],
)
def test_recommendations_disguised_as_restraint_are_refused(text):
    assert Bazi.trade_problems(text), text


@pytest.mark.parametrize(
    "text",
    [
        "8月不太适合买入。",
        "8月并不适合加仓。",
        "明年算不上让人放心全押的一年。",
        "明年不像是适合投入的年份。",
        "明年谈不上是让人放心全押的一年。",
        "8月买入之前务必谨慎。",
        "8月涉及投入的事多找人复核。",
        "8月操作尤其要边界清楚。",
        "8月操作时要小心一些。",
        "8月投入前先核实财务状况。",
        "下个月加仓需要谨慎。",
        "下个月买入需谨慎。",
        "下个月买入前确认你的风险承受能力。",
        "下个月投入之前评估自身财务状况。",
    ],
)
def test_denied_suitability_and_actual_cautions_still_pass(text):
    assert Bazi.trade_problems(text) == [], text


@pytest.mark.parametrize(
    "text,repairs",
    [
        ("8月岂能错过加仓机会。", 1),
        ("8月买入谨慎型产品。", 1),
        ("8月不太需要谨慎买入。", 1),
        ("8月并不适合加仓。", 0),
        ("8月买入之前务必谨慎。", 0),
    ],
)
async def test_trade_restraint_controls_repair(make, text, repairs):  # noqa: F811
    runtime, composer, _ = make(lambda m: written(m, extra=text), written, birth=PILOT["profile"])
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1 + repairs, repairs, None)
    if repairs:
        assert f"出问题的句子：“{text}”" in composer.seen[1][0][-1]["content"]
    else:
        assert any(text in s["body"] for s in outcome.data["reading"]["sections"])
