"""Bazi pilot r7 findings (docs/verification/p3/bazi-pilot-r7/review.md), fixed in r8.

- Investment #1, #2: ten held-back sentences were refused by the trade check; investment #2's
  second draft was refused only for them and degraded to keywords. Three rounds running, a new
  held-back wording was refused. Owner decision 2026-11-10: refuse only an explicit
  recommendation of a timed trade; anything else that names a trade passes.
- Luck cycles #2: “年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处偏财线索”, a summary that
  disagrees with the ten gods it follows, passed every check.

The relaxation carries its guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

import pytest

from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import (
    DAYUN_CASE,
    INVESTMENT_CASE,
    computed,
    has,
    refused,
)
from tests.pipeline.test_runner_bazi import make, written  # noqa: F401

TRADE = "八字不能推出仓位、买卖时点或投入节奏"
# Every sentence of the refused r7 investment drafts that raised the trade problem, except the
# one the owner found to recommend a trade (R7_RECOMMENDED).
R7_HELD_BACK = (
    "全年冲、害、刑、破交错，情绪与判断容易受牵动，全投的风险远超命理解读能覆盖的范围。",
    "【收尾】明年更适合稳中求进、边学边调，把“全投”换成“留余地”，才是对自己积蓄更负责的做法。",
    "年初先把“全投”的念头放一放，用一两个月观察自己的风险承受力更实际。",
    "【分层】2月到6月：压力与支持交替，学习比出手重要",
    "3月前后流月癸卯（十神七杀；2027年3月6日03:39至2027年4月5日08:17，北京时间）带来任务和压力感，"
    "容易觉得被推着走，这时先明确边界再谈投入。",
    "- 借力学习：把4月到6月当作补课期，学基础、看流程，比追涨杀跌更稳。",
    "【摘要】明年整体不支撑“把积蓄全投股市”这类判断，更适合把重心放在核实自身财务和风险承受力上。",
    "年初先把“全押”这类念头搁一搁，多花时间确认自己能承受多大波动，比急着行动更实在。",
    "如果你正在做资金安排，这几个月更适合把规则、凭证和止损条件想清楚，而不是一次性把积蓄押上去。",
)
R7_RECOMMENDED = (
    "如果你正在做资金安排，这几个月更适合小额验证、设好止损线，而不是一次性押上全部积蓄。"
)
# Earlier saved answers that hold back, refused until r8 (r3 investment #1–#3, r4 investment #2).
EARLIER_HELD_BACK = (
    "流年丙午与本命时柱辛亥天干合（1月1日至2月4日）提示信息和人脉容易互相牵绊，别把某个朋友的建议当成全投理由。",
    "全年需留意流年丁未与本命月柱庚子地支害（2月4日至12月31日），意味表面看着顺、实际配合有暗中的不畅，"
    "投入越多越容易在细节处消耗。",
    "流月戊申与本命时柱辛亥地支害（8月8日至9月8日）冲刑害交织，说明这段时间外部变动多、"
    "隐性摩擦也不少，操作上宜降低频率。",
    "流月庚戌（十神正财；2027年10月8日20:17至2027年11月7日23:38，北京时间）再次出现正财，"
    "是适合复盘预算、控制仓位的时段，而不是加大投入的时段。",
    "把明年看作需要慢慢铺排、分批验证的阶段，会比一次性全投从容得多。",
)
# Earlier saved answers that recommend a timed trade, still refused.
EARLIER_RECOMMENDED = (
    "整体看，下半年更适合用固定节奏小额投入、定期复盘，而不是把积蓄一次压上。",  # r3 #2
    "八月流月戊申与本命年柱丙寅地支冲（8月8日至9月8日）又是冲、刑、害集中的月份，"
    "此时更适合检查仓位而非扩大仓位。",  # r4 #2
    "流月辛丑（十神偏财；2027年1月5日22:09至2027年2月4日09:46，北京时间）虽带偏财主题，"
    "所以即便感觉机会来了，也只适合小额度、可承受损失的试探，而不是全投。",  # r4 #3
)
R7_AGGREGATE = (
    "这个倾向和你原局里年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处偏财线索放在一起看，"
    "更像是提醒你把机会转成预算和可交付的成果，而不是凭符号判断收益。"
)


@pytest.fixture
async def money(make):  # noqa: F811
    chart, _ = await computed(make, INVESTMENT_CASE, INVESTMENT)
    return chart


@pytest.fixture
async def luck(make):  # noqa: F811
    chart, _ = await computed(make, DAYUN_CASE, DAYUN_CASE["question"])
    pillars = chart.state["bazi_result"]["pillars"]
    gods = chart.state["bazi_result"]["ten_gods_stems"]
    assert (pillars["year"], gods["year"], pillars["time"], gods["time"]) == (
        "戊辰",
        "正财",
        "己卯",
        "偏财",
    )
    return chart


# ---- the trade check: explicit recommendations only -------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    R7_HELD_BACK + EARLIER_HELD_BACK,
    ids=[f"r7-{i}" for i in range(len(R7_HELD_BACK))]
    + [f"earlier-{i}" for i in range(len(EARLIER_HELD_BACK))],
)
async def test_held_back_wording_passes(money, sentence):
    assert not has(refused(money, sentence), TRADE)


@pytest.mark.parametrize(
    "sentence",
    (R7_RECOMMENDED, *EARLIER_RECOMMENDED),
    ids=["r7-recommended", "r3-2", "r4-2", "r4-3"],
)
async def test_recommended_timed_trades_are_refused(money, sentence):
    assert has(refused(money, sentence), TRADE)


async def test_what_only_looks_held_back_is_still_refused(money):
    for text in (
        "年初先把“全押”这类念头搁一搁，流月辛丑适合小额度试探。",  # another item in the sentence
        "明年整体不支撑全投，但8月适合加仓。",  # a denial, then a statement after a turn
        "这些流月不构成买卖时点，但8月是买入时点。",
        "不能说8月不宜加仓。",  # an outer negation
        "8月不一定不适合加仓。",  # a degree word
        "8月不太需要谨慎买入。",  # the need for caution denied
        "8月并非不宜加仓。",  # a double negation
        "流年以劫财为主题，“全投”不一定超出八字能判断的范围。",
        "8月加仓。",  # a period right before the trade
        "8月核实可投入金额并加仓。",  # an instruction opening its clause
        "8月是买入时点。",  # a timing noun asserted
        "8月岂能错过加仓机会。",
        "8月不要犹豫地加仓。",
        "8月可以比7月多加仓。",  # a comparison with a recommendation
        "8月不建议等待时机而要全仓。",
    ):
        assert has(refused(money, text), TRADE), text
    for text in (
        "8月要谨慎加仓。",  # as “加仓需要谨慎”
        "8月谨慎买入。",
        "下个月加仓需要谨慎。",
        "先观望，等情绪平稳再谈投入。",
    ):
        assert not has(refused(money, text), TRADE), text


# ---- a summary of ten gods ----------------------------------------------------------------------


async def test_a_summary_of_ten_gods_must_agree(luck):
    problem = "与前面写的十神不符：前面依次是正财、偏财"
    for text in (
        R7_AGGREGATE,
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）都是偏财。",
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）两处都带偏财。",
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处并不都是偏财，但其实都是偏财。",
    ):
        assert has(refused(luck, text), problem), text
    for text in (
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处并不都是偏财。",  # a denial
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处财星放在一起看。",
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）一处正财、一处偏财。",
        "时柱己卯（天干己为偏财），第4步大运己未天干己为偏财，两处偏财。",  # they agree
    ):
        assert not has(refused(luck, text), "与前面写的十神不符"), text


# ---- end to end -----------------------------------------------------------------------------


async def test_the_r7_held_back_draft_is_submitted_without_repair(make):  # noqa: F811
    extra = "年初先把“全押”这类念头搁一搁，多花时间确认自己能承受多大波动，比急着行动更实在。"
    runtime, _, _ = make(
        lambda m: written(m, extra=extra), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


async def test_the_r7_summary_is_repaired_with_its_sentence_quoted(make):  # noqa: F811
    runtime, composer, _ = make(
        lambda m: written(m, extra=R7_AGGREGATE), written, birth=DAYUN_CASE["profile"]
    )
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert has(info["problems"][0], "与前面写的十神不符")
    assert f"出问题的句子：“{R7_AGGREGATE}”" in composer.seen[1][0][-1]["content"]
