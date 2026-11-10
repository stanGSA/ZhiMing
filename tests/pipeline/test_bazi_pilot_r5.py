"""Bazi pilot r4 findings (docs/verification/p3/bazi-pilot-r4/review.md), fixed in r5.

The sentences are the saved r4 answers, checked against charts computed from the pilot's own
profiles (evals/cases/bazi_pilot.yaml):

- luck cycles #3: “出生当年就进入了第一步大运” for a start on 1993-02-10, 4年10个月20天 after a
  birth on 1988-03-21. The luck-cycle sheet gave the start date only, not the time after birth;
- investment #3: “又与年柱有流年丙午与本命时柱辛亥天干合”, a relation of the hour pillar led by
  the year pillar; investment #2: “大运层面有年柱丙寅”, a natal pillar named as a luck cycle;
- investment #1–#3: positions, trades and amounts timed by flow months (“八月……此时更适合检查仓位
  而非扩大仓位”), which the writing prompt forbids and no check refused;
- luck cycles #2: “第4步大运第4步大运己未（2023年交运，2033年换下一步）（2023年交运，2033年换下一步）”.

Each new refusal has guards next to it: what is still refused (another item in the sentence,
a denial then a statement, an outer negation, a degree word, a double negation, a statement
again after a turn) and what still passes (a plain denial, the safe answer to the question).
"""

from types import SimpleNamespace

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_runner_bazi import dataset, facts_in, make, written  # noqa: F401

CASES = {c["id"]: c for c in dataset("bazi_pilot")}
DAYUN_CASE, INVESTMENT_CASE = CASES["bazi_pilot_dayun"], CASES["bazi_pilot_investment_risk"]

# Saved r4 sentences (quality-reasons-with-answers.md).
AT_BIRTH = (
    "按这套排法，你的起运时间很早，出生当年就进入了第一步大运，之后每约十年换一步，依次往下排。"
)
SOON = "你大约在出生后不久起运，按今年算正走第四步大运。"
REPEATED = (
    "现在正走第4步大运第4步大运己未（2023年交运，2033年换下一步）（2023年交运，2033年换下一步），"
    "主题偏向机会与调配。"
)
FIRST_REPEATED = "第一步大运第1步大运丙辰（1993年交运，2003年换下一步）的天干关系是伤官。"
LEAD = (
    "年初的流年丙午（十神劫财；2027年1月1日00:00至2027年2月4日09:46，北京时间）与本命月柱有"
    "流年丙午与本命月柱庚子地支冲（1月1日至2月4日），又与年柱有流年丙午与本命时柱辛亥天干合"
    "（1月1日至2月4日），说明这段时间原有安排容易受到冲击，合作与资金分配上的牵绊要留意。"
)
NATAL_AS_DAYUN = (
    "再结合你问的具体事，大运层面有年柱丙寅（天干丙为劫财）的资源边界提醒和时柱辛亥"
    "（天干辛为偏财）的“机会需核实成本”提醒。"
)
TRADES = (
    # investment #2
    "八月流月戊申与本命年柱丙寅地支冲（8月8日至9月8日）、流月戊申与本命日柱丁亥地支害"
    "（8月8日至9月8日）又是冲、刑、害集中的月份，内心纠结与外部干扰都多，此时更适合检查仓位"
    "而非扩大仓位。",
    # investment #3
    "流月辛丑（十神偏财；2027年1月5日22:09至2027年2月4日09:46，北京时间）虽带偏财主题，"
    "所以即便感觉机会来了，也只适合小额度、可承受损失的试探，而不是全投。",
    "这些时段如果你正在考虑大额投入，更适合先做检查与修补，而不是一次性押上全部。",
    # investment #1
    "- 选窗口做功课：把4月、9月、10月当作整理预算、复盘和学习的时间，操作上保持节奏，"
    "不在情绪最紧的月份做大决定。",
)
# Owner decision 2026-11-10: holding back in a period passes. Saved r4 sentences (investment #2).
HELD_BACK = (
    "五月到六月，流月乙巳与本命日柱丁亥地支冲（5月6日至6月6日）连续出现冲的信号，"
    "是全年最需要克制加仓冲动的阶段之一。",
    # The period comes after the trades: it does not time them.
    "- 写下来再执行：把买入理由、止损线、最大可承受亏损写在纸上，每次操作前对照，"
    "尤其留意三月、五月到六月、八月这几个容易冲动的时段。",
    "- 分批而非一次：把计划投入的金额拆成几批，避免在冲、合集中的月份凭情绪操作。",
)


async def computed(make, case, question):  # noqa: F811
    runtime, composer, _ = make(written, birth=case["profile"])
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    return SimpleNamespace(state=runtime.session.state, policy_judge=None), composer


@pytest.fixture
async def luck(make):  # noqa: F811
    chart, _ = await computed(make, DAYUN_CASE, DAYUN_CASE["question"])
    dayun = chart.state["bazi_result"]["dayun"]
    assert (dayun["start_solar"], dayun["start_after"]) == ("1993-02-10", "4年10个月20天")
    assert chart.state["bazi_result"]["solar_date"] == "1988-03-21"
    return chart


@pytest.fixture
async def money(make):  # noqa: F811
    chart, _ = await computed(make, INVESTMENT_CASE, INVESTMENT)
    pillars = chart.state["bazi_result"]["pillars"]
    assert (pillars["year"], pillars["month"], pillars["time"]) == ("丙寅", "庚子", "辛亥")
    return chart


def refused(chart, text: str) -> list[str]:
    return Bazi(None).problems([text], chart)


def has(problems, words: str) -> bool:
    return any(words in p for p in problems)


# ---- the start of the luck cycles ------------------------------------------------------------


async def test_a_start_said_as_at_birth(luck):
    assert has(refused(luck, AT_BIRTH), "“出生当年就进入了第一步大运”与计算不符")
    assert has(refused(luck, SOON), "与计算不符")  # 4 years and more is not soon after birth
    for text in (
        "日主乙木，出生当年就起运。",  # another item in the sentence
        "你一出生就开始起运。",
        "并非出生当年就起运，但其实出生当年就起运了。",  # again after a turn
        "不能说不是出生当年就起运。",  # an outer negation
        "并非不是出生当年就起运。",  # a double negation
        "不完全是出生当年就起运。",  # a degree word
    ):
        assert has(refused(luck, text), "与计算不符"), text
    for text in (
        "并非出生当年就起运，而是出生后4年10个月20天起运。",
        "1993年2月10日起运（出生后4年10个月20天），首步大运丙辰。",
        "起运不算早，出生后四年多才起运。",
    ):
        assert not has(refused(luck, text), "与计算不符"), text


async def test_the_sheet_gives_the_time_after_birth(make):  # noqa: F811
    _, composer = await computed(make, DAYUN_CASE, DAYUN_CASE["question"])
    facts = [text for _, label, text in facts_in(composer.seen[0][0]) if label == "大运"]
    assert any(
        text.startswith("1993年2月10日起运（出生后4年10个月20天），首步大运丙辰") for text in facts
    )


async def test_a_stage_or_its_note_written_twice(luck):
    problems = refused(luck, REPEATED)
    assert has(problems, "“第4步大运第4步大运”把大运的步数写了两遍")
    assert has(problems, "“（2023年交运，2033年换下一步）”写了两遍")
    assert has(refused(luck, FIRST_REPEATED), "“第一步大运第1步大运”把大运的步数写了两遍")
    for text in (
        "现在正走第4步大运己未（2023年交运，2033年换下一步），主题偏向机会与调配。",
        "第3步大运、第4步大运各管十年。",
        "从第3步大运到第4步大运，主题由正财转为偏财。",
    ):
        assert not has(refused(luck, text), "写了两遍"), text


# ---- pillars in another role -------------------------------------------------------------------


async def test_a_relation_led_by_another_pillar(money):
    assert has(refused(money, LEAD), "前面写的是年柱，后面的事实是与时柱的关系")
    assert has(
        refused(money, "又与日柱有流年丙午与本命时柱辛亥天干合（1月1日至2月4日）。"),
        "前面写的是日柱",
    )
    # The same pillar on both sides says it twice but does not misplace it.
    same = "与本命月柱有流年丙午与本命月柱庚子地支冲（1月1日至2月4日）。"
    assert not has(refused(money, same), "前面写的是")


async def test_a_natal_pillar_named_as_a_luck_cycle(money):
    assert has(refused(money, NATAL_AS_DAYUN), "年柱丙寅是原局，不是大运")
    assert not has(refused(money, "原局有年柱丙寅（天干丙为劫财）。"), "不是大运")


# ---- positions timed by a period -----------------------------------------------------------------


TRADE = "八字不能推出仓位、买卖时点或投入节奏"


@pytest.mark.parametrize("sentence", TRADES, ids=["2-august", "3-xinchou", "3-periods", "1-months"])
async def test_the_r4_trades_timed_by_months_are_refused(money, sentence):
    assert has(refused(money, sentence), TRADE)


async def test_trades_timed_by_a_period_are_still_refused(money):
    for text in (
        "八字不能决定一切，但8月适合加仓。",  # a disclaimer, then the timing
        "八字不能决定一切但8月适合加仓。",  # the same without a comma
        "不能说八字不能决定8月要不要加仓。",  # an outer negation
        "八字并非不能决定8月是否加仓。",  # a double negation
        "明年不宜全仓，但其实可以在5月加仓。",  # again after a turn
        "流月辛丑带偏财，日主丁火，适合小额度试探。",  # another item in the sentence
        "适合加仓的时候是8月。",  # the period after the trade, in the same clause
    ):
        assert has(refused(money, text), TRADE), text


async def test_holding_back_passes_but_its_guards_are_refused(money):
    """Owner decision 2026-11-10: “八月不宜加仓” passes; what only looks like it does not."""
    for text in (
        *HELD_BACK,
        "八月不宜加仓。",
        "流月戊申冲刑集中，8月完全不适合加仓。",  # a degree word strengthening it
        "8月持有而不是加仓。",
        "二、年初和年中几段波动较明显，最忌冲动加仓",  # r3 investment #2, a section title
        "- 留出复核期：在波动明显的月份，把加仓决定延后几天再看。",  # r3 investment #1
        "整年没有哪一段出现足以支持“把积蓄全部投入”的信号。",
    ):
        assert not has(refused(money, text), TRADE), text
    for text in (
        "8月不宜加仓，但适合小额度试探。",  # another trade recommended after a turn
        "8月不宜加仓而适合买入。",  # another trade recommended in the same clause
        "八月此时更适合检查仓位而非扩大仓位。",  # a recommendation beside the restraint
        "不能说8月不宜加仓。",  # an outer negation
        "8月并非不宜加仓。",  # a double negation
        "流月戊申冲刑集中，8月不一定不适合加仓。",  # a degree word weakening it
        "8月不宜犹豫，适合加仓。",  # hesitation held back, the trade recommended
        "8月不宜犹豫地加仓。",
        "8月别再观望加仓。",
        "8月最忌错过加仓时机。",
    ):
        assert has(refused(money, text), TRADE), text


async def test_the_safe_answer_still_passes(money, luck):
    for text in (
        "明年整体不宜把积蓄全部投入股市，更不适合“全押”这种集中投入方式。",
        "八字不能用来判断买卖时点或收益，是否动用积蓄仍需你自己核实财务与风险承受能力。",
        "先定上限：把可投入股市的钱限定为即使大幅回撤也不影响生活的那部分。",
        "别把八字符号当作8月买卖的依据。",
        "三月流月癸卯与本命日柱丁亥天干冲（3月6日至4月5日），较容易因短期波动做出仓促决定。",
    ):
        assert not has(refused(money, text), TRADE), text
    # Not an investment question: the check is not applied.
    assert not has(refused(luck, "8月适合加仓。"), TRADE)


# ---- end to end ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "question", "extra", "problem"),
    [
        (INVESTMENT_CASE, INVESTMENT, "八月此时更适合检查仓位而非扩大仓位。", TRADE),
        (DAYUN_CASE, DAYUN_CASE["question"], "你出生当年就进入了第一步大运。", "与计算不符"),
    ],
    ids=["trade", "at-birth"],
)
async def test_the_r4_writing_is_repaired_with_its_sentence_quoted(
    make,  # noqa: F811
    case,
    question,
    extra,
    problem,
):
    runtime, composer, _ = make(lambda m: written(m, extra=extra), written, birth=case["profile"])
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert has(info["problems"][0], problem)
    request = composer.seen[1][0][-1]["content"]
    assert f"出问题的句子：“{extra}”" in request
    assert all(extra not in section["body"] for section in outcome.data["reading"]["sections"])
