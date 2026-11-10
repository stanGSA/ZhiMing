"""PR67: bind a recommendation, restraint and aggregate to their actual subjects."""

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import DAYUN_CASE, INVESTMENT_CASE
from tests.pipeline.test_runner_bazi import make, written  # noqa: F401

RECOMMENDED = (
    "8月如果资金充足就加仓。",
    "8月若能承受风险可以全仓。",
    "如果8月资金充足就适合加仓。",
    "8月适合先控制情绪再加仓。",
    "8月建议降低成本后买入。",
    "8月适合控制情绪后可以加仓。",
    "8月建议守住本金后分批买入。",
    "8月若资金充足则买入股票。",
    "8月如果准备加仓就适合买入。",
)
HELD_BACK = (
    "8月不要急于寻找买入时机。",
    "8月不宜寻找加仓机会。",
    "8月不要追逐加仓机会。",
    "8月适合控制自己的仓位。",
    "8月建议降低操作频率。",
    "8月如果你正在考虑大额投入，先核实自己的财务状况。",
    "这些时段如果你正在考虑大额投入，更适合先做检查与修补，而不是一次性押上全部。",
)
LISTED = "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财），第4步大运己未天干己为偏财，"
SUBSETS = (
    LISTED + "后两处都是偏财。",
    LISTED + "其中两处偏财提示机会。",
    LISTED + "两处偏财、一处正财。",
    "第4步大运己未天干己为偏财、时柱己卯（天干己为偏财）、年柱戊辰（天干戊为正财），前两处都是偏财。",
)
WRONG_SUBSETS = (
    LISTED + "都是偏财。",
    LISTED + "三处偏财。",
    LISTED + "后两处都是正财。",
    LISTED + "前两处都是偏财。",
    LISTED + "其中两处正财。",
)


@pytest.mark.parametrize("text", RECOMMENDED)
def test_conditions_and_unrelated_bounds_do_not_exempt_recommendations(text):
    assert Bazi.trade_problems(text), text


@pytest.mark.parametrize("text", HELD_BACK)
def test_restraint_and_contemplated_conditions_pass(text):
    assert Bazi.trade_problems(text) == [], text


@pytest.mark.parametrize("text", SUBSETS)
def test_correct_local_aggregates_pass(text):
    assert Bazi.aggregate_problems(text) == [], text


@pytest.mark.parametrize("text", WRONG_SUBSETS)
def test_wrong_local_and_whole_aggregates_are_refused(text):
    assert Bazi.aggregate_problems(text), text


@pytest.mark.parametrize(
    "text,repairs",
    [(t, 1) for t in RECOMMENDED[:5]] + [(t, 0) for t in HELD_BACK[:2]],
)
async def test_trade_predicates_control_actual_repairs(make, text, repairs):  # noqa: F811
    runtime, composer, _ = make(
        lambda m: written(m, extra=text), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1 + repairs, repairs, None)
    if repairs:
        assert f"出问题的句子：“{text}”" in composer.seen[1][0][-1]["content"]
    else:
        assert text in outcome.text


@pytest.mark.parametrize("text", SUBSETS[:2])
async def test_correct_subsets_are_submitted_without_repair(make, text):  # noqa: F811
    runtime, _, _ = make(lambda m: written(m, extra=text), written, birth=DAYUN_CASE["profile"])
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert text in outcome.text
