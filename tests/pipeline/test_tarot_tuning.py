"""What the tarot tuning set found (docs/verification/p1/tarot/analysis.md), each as a test."""

import re

import pytest

from agents.orchestrator import MULTI_SYSTEM_PROMPT, SCENARIO_RULE, SYSTEM_PROMPT
from app import create_runtime
from pipeline.compose import TAROT_SYSTEM
from tests.pipeline.drafts import QUESTION, Composer, followup_answer, good
from tests.validation.test_negation_and_dates import REFUSED_DRAFTS

RISKY = "只用塔罗三张牌帮我反思：是否应该把积蓄全部买入一只股票？"
SHEET_LINE = re.compile(r"^(R\d+)｜第(\d)张·(.+?)位｜(.+)$", re.M)


@pytest.fixture
def make(project):
    runtimes = []

    def build(*drafts, user_id="tuning-user"):
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project, user_id=user_id, seed=42, model=composer, mode="pipeline"
        )
        runtimes.append(runtime)
        return runtime, composer

    yield build
    for runtime in runtimes:
        runtime.close()


def sheet(composer, call=0) -> str:
    return composer.seen[call][0][1]["content"]


def with_sentence(sentence: str):
    def draft(messages):
        return good(messages).replace("【建议】", f"【分层】补充\n{sentence}\n【建议】", 1)

    return draft


def test_the_writer_keeps_the_scenario_rule_of_the_agent_loop():
    # The judge fails answers that state a scenario as the user's own experience; the pipeline's
    # condensed prompt had lost the one rule the agent loop's prompt has against it.
    for prompt in (TAROT_SYSTEM, SYSTEM_PROMPT, MULTI_SYSTEM_PROMPT):
        assert SCENARIO_RULE in prompt
    assert "不描述事实表没有的牌面画面" in TAROT_SYSTEM
    assert "问怎么做、怎么安排时直接给出最关键的做法" in TAROT_SYSTEM


async def test_the_fact_sheet_numbers_the_cards_and_leaves_out_the_caveat(make):
    runtime, composer = make(good)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    lines = SHEET_LINE.findall(sheet(composer))
    assert [(n, label) for _, n, label, _ in lines] == [("1", "过去"), ("2", "现在"), ("3", "未来")]
    text = sheet(composer)
    assert "这是象征性反思线索" not in text and "必然" not in text
    # The meaning itself stays: the knowledge base's sentence before the caveat.
    for card in runtime.session.state["tarot_result"]["cards"]:
        meaning = card["meaning"]["text"].split("这是象征性反思线索")[0]
        assert meaning and meaning in text


async def test_a_later_draw_still_names_its_second_card(make):
    # After a redraw the numbers run on (R4…R6); “第二张牌” is found by its place in the draw.
    runtime, composer = make(good, good, followup_answer)
    await runtime.turn(QUESTION)
    await runtime.turn("请重新抽一次，仍用三张牌看近期事业状态。")
    outcome = await runtime.turn("第二张牌具体什么意思？请解释原牌，不要重新抽牌。")
    assert outcome.status == "submit_reading"
    lines = SHEET_LINE.findall(sheet(composer, 2))
    second = next(alias for alias, n, _, _ in lines if n == "2")
    assert second != "R2"
    card = runtime.session.state["tarot_result"]["cards"][1]
    assert f"{second}｜第2张·现在位｜【{card['name']}】" in sheet(composer, 2)


@pytest.mark.parametrize(
    "sentence",
    [
        *REFUSED_DRAFTS,
        "这不代表这只股票一定会涨，也不代表全部投入必然亏损。",
        "这不是一种必然，选择权在你。",
        "并非这只股票一定会涨。",
    ],
)
async def test_a_negated_claim_about_the_question_is_not_repaired(make, sentence):
    runtime, composer = make(with_sentence(sentence))
    outcome = await runtime.turn(RISKY)
    assert outcome.status == "submit_reading"
    assert (outcome.data["pipeline"]["model_calls"], outcome.data["pipeline"]["repairs"]) == (1, 0)
    assert sentence in outcome.text


async def test_a_negated_claim_in_both_drafts_is_not_a_safety_failure(make):
    # PR #37 review: with the sentence in the draft and in its repair, the high-risk question
    # ended in the safety template instead of the reading.
    sentence = "它不代表行情必然上涨。"
    runtime, composer = make(with_sentence(sentence), with_sentence(sentence))
    outcome = await runtime.turn(RISKY)
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert outcome.data["reading"]["sections"] and sentence in outcome.text


@pytest.mark.parametrize(
    "sentence",
    # The negations the certainty check knowingly refuses (the strict xfails in
    # tests/validation/test_negation_and_dates.py).
    ["并非亏损股票一定会涨。", "这不代表下个月的面试结果一定会好。"],
)
async def test_a_known_false_refusal_in_both_drafts_ends_in_the_safety_reply(make, sentence):
    # The cost of that conservatism on a high-risk question (fourth review of PR #37): when the
    # repair repeats the sentence, the hard safety rule replaces the whole reading. The status
    # is still submit_reading, so the submission rate alone does not show it. The owner accepts
    # this for now (analysis 5.4, option A) and the rerun counts it; changing it is a visible step.
    runtime, composer = make(with_sentence(sentence), with_sentence(sentence))
    outcome = await runtime.turn(RISKY)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, "safety")
    assert outcome.data["reading"]["sections"] == [] and sentence not in outcome.text


@pytest.mark.parametrize(
    "sentence",
    # The others follow an unrelated negation (re-check of 1fe9499 and review of 1a4b377).
    [
        "这只股票一定会涨。",
        "这不是坏事这只股票一定会涨。",
        "这不代表坏事股价一定会涨。",
        "这不代表过去的亏损股价一定会涨。",
    ],
)
async def test_a_certainty_claim_about_the_stock_is_still_repaired(make, sentence):
    runtime, composer = make(with_sentence(sentence), good)
    outcome = await runtime.turn(RISKY)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert "确定性说法" in info["problems"][0][0]
    assert "一定会涨" not in outcome.text
