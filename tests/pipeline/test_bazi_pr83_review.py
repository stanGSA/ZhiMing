"""PR #83 review: conditional entry advice and safe learning / historical cycle statements."""

import pytest

from pipeline.bazi import entry_offered
from tests.pipeline.test_bazi_pilot_r21 import (
    NOW,
    citing,
    entered,
    findings,
    problems,
)
from tests.pipeline.test_bazi_pilot_r21 import career as career
from tests.pipeline.test_bazi_pilot_r21 import money as money
from tests.pipeline.test_bazi_pilot_r21 import run_at as run_at
from tests.pipeline.test_runner_bazi import written


@pytest.mark.parametrize(
    "text",
    [
        "如果你已经核实财务就可以少量参与。",
        "如果你已经核实财务，就可以少量参与。",
        "若你准备好了就少量参与。",
        "若你准备好了则可以少量参与。",
        "如果你准备好了那么可以参与市场。",
        "如果你已经核实财务可以少量参与。",
        "可以买一点基金。",
        "适合投资指数基金。",
        "建议将资金配置到指数基金。",
        "不要参与知识培训，而是买一点基金。",
        "可以参与投资知识培训，然后入场。",
        "不要买基金，但可以买一点股票。",
        "不能说不可以买一点基金。",
        "并非不能投资指数基金。",
        "少量参与不是好办法，但可以投资指数基金。",
    ],
)
def test_entry_advice_is_not_excused_by_its_condition_or_word_order(text):
    assert entry_offered(text)


@pytest.mark.parametrize(
    "text",
    [
        "可以参与投资知识培训。",
        "可以参与线上理财培训。",
        "可以参与基金知识讨论。",
        "建议学习投资指数基金的知识。",
        "买一点基金的冲动要先搁一搁。",
        "不要买一点基金去试水。",
        "不建议投资指数基金。",
        "如果你正想买一点基金，先停下来核实预算。",
        "如果你已经准备买入基金，先核对财务。",
        "少量参与不是好办法。",
    ],
)
def test_learning_restraint_and_described_intentions_still_pass(text):
    assert not entry_offered(text)


async def test_new_entries_are_checked_in_dated_sections_and_summary(money):
    for text in (
        "如果你已经核实财务就可以少量参与。",
        "可以买一点基金。",
        "适合投资指数基金。",
    ):
        assert entered(findings(money, "4月到8月", text)), text
        assert entered(findings(money, "财务底色", "先核实。", summary=text)), text
    for text in ("可以参与投资知识培训。", "少量参与不是好办法。"):
        assert not findings(money, "4月到8月", text), text


async def test_cycle_role_denial_and_historical_year_are_not_current(career):
    for text in (
        "首步大运己丑并非现在所处的大运。",
        "首步大运己丑不是目前所处的大运。",
        "2002年首步大运己丑正处在前半段。",
    ):
        assert not problems(career, text), text
    for text in (
        "首步大运己丑并非现在所处的大运，但现在仍在走首步大运己丑。",
        "首步大运己丑并非现在所处的大运但现在仍处在这步。",
        "首步大运己丑并非不在现在所处的大运中。",
        "不能说首步大运己丑并非现在所处的大运。",
        "首步大运己丑并非完全是现在所处的大运。",
        "2026年首步大运己丑正处在前半段。",
    ):
        assert any(NOW in p for p in problems(career, text)), text


@pytest.mark.parametrize(
    "text, calls",
    [
        ("如果你已经核实财务就可以少量参与。", 2),
        ("可以买一点基金。", 2),
        ("适合投资指数基金。", 2),
        ("可以参与投资知识培训。", 1),
    ],
)
async def test_review_examples_are_repaired_or_submitted_as_appropriate(run_at, text, calls):
    def draft(messages):
        return written(messages).replace("提示你把精力放在长期目标上。", text, 1)

    _, outcome, composer = await run_at("bazi_pilot_investment_risk", draft, written)
    assert len(composer.seen) == calls
    assert (text in outcome.text) == (calls == 1)
    if calls == 2:
        assert entered(outcome.data["pipeline"]["problems"][0])


async def test_a_cited_cycle_with_a_denied_present_role_submits_first(run_at):
    _, _, composer = await run_at(
        "bazi_pilot_next_month_career", citing("大运", "并非现在所处的大运。")
    )
    assert len(composer.seen) == 1
