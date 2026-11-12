"""PR71 review: predicate scope, virtual handover ages and explicit cycle topics."""

import pytest

from common.output_policy import hard_claim
from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r5 import DAYUN_CASE, INVESTMENT_CASE
from tests.pipeline.test_runner_bazi import make, written  # noqa: F401


@pytest.mark.parametrize(
    "consequent",
    [
        "先全仓买入",
        "不要犹豫",
        "不必核实，直接投入",
        "先不要核实",
        "不用冷静，直接行动",
        "先冷静加仓",
        "不能说不要犹豫",
    ],
)
def test_gain_condition_requires_an_actual_restraint(consequent):
    assert hard_claim([f"如果你被“稳赚”说法打动，{consequent}。"]) == "稳赚"


@pytest.mark.parametrize(
    "consequent",
    [
        "先回到预算和规则上",
        "先冷静下来",
        "请先核实风险",
        "把这个念头放一放",
        "不要急着动用积蓄",
    ],
)
def test_gain_condition_still_allows_a_governing_restraint(consequent):
    assert hard_claim([f"如果你被“稳赚”说法打动，{consequent}。"]) is None


@pytest.mark.parametrize(
    "text",
    [
        "8月大额投入的想法可以执行。",
        "8月大额投入的念头值得采纳。",
        "8月大额投入的打算应该落实。",
        "8月适度投入的想法不妨执行。",
    ],
)
def test_a_recommended_nominal_trade_is_refused(text):
    assert Bazi.trade_problems(text)


@pytest.mark.parametrize(
    "text",
    [
        "8月大额投入的想法不值得采纳。",
        "8月大额投入的想法不应该落实。",
        "8月大额投入的念头先放一放。",
        "如果你面对大额投入的诱惑，先冷静。",
    ],
)
def test_a_nominal_trade_with_no_recommendation_still_passes(text):
    assert Bazi.trade_problems(text) == []


@pytest.mark.parametrize(
    "text,refused",
    [
        ("你今年虚岁39岁，目前在第4步大运己未。", False),
        ("虚岁是出生算1岁。", False),
        ("按虚岁算，16岁进入第一步大运。", True),
        ("按虚岁算，6岁进入第二步大运。", True),
        ("虚岁6岁进入第一步大运。", False),
        ("虚岁16岁换第二步大运。", False),
        ("第一步大运在虚岁16岁交运。", True),
        ("第二步大运在虚岁6岁交运。", True),
        ("第一步大运在虚岁6岁交运。", False),
        ("第二步大运在虚岁16岁交运。", False),
        ("虚岁6岁到16岁之间进入第一步大运。", True),
        ("虚岁并不是6岁进入第一步大运。", True),
        ("虚岁并不是5岁进入第一步大运。", False),
        ("第一步大运是丙辰，下一步是丁巳。", False),
        ("首步大运丙辰，后一步是丁巳。", False),
        ("第1步大运丙辰之后，下一步是丁巳。", False),
        ("第一步大运是丙辰，下一步是戊午。", True),
        ("前一步是第3步大运戊午，下一步是第5步大运庚申。", False),
        ("前一步是第3步大运戊午，下一步是第4步大运己未。", True),
        ("第一步大运是丙辰。下一步是庚申。", False),
    ],
)
async def test_ages_and_neighbours_in_the_chart_context(make, text, refused):  # noqa: F811
    runtime, _, _ = make(written, birth=DAYUN_CASE["profile"])
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    assert bool(Bazi(None).problems([text], runtime.session)) is refused


@pytest.mark.parametrize(
    "case,sentence,repairs",
    [
        (DAYUN_CASE, "你今年虚岁39岁，目前在第4步大运己未。", 0),
        (DAYUN_CASE, "第一步大运是丙辰，下一步是丁巳。", 0),
        (DAYUN_CASE, "按虚岁算，16岁进入第一步大运。", 1),
        (DAYUN_CASE, "第一步大运是丙辰，下一步是戊午。", 1),
        (INVESTMENT_CASE, "如果你被“稳赚”说法打动，先全仓买入。", 1),
        (INVESTMENT_CASE, "8月大额投入的想法可以执行。", 1),
    ],
)
async def test_review_sentences_take_the_expected_submission_path(
    make,  # noqa: F811
    case,
    sentence,
    repairs,
):
    runtime, _, _ = make(
        lambda messages: written(messages, extra=sentence), written, birth=case["profile"]
    )
    outcome = await runtime.turn(case["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1 + repairs, repairs, None)
