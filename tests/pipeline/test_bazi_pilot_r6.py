"""Bazi pilot r5 findings (docs/verification/p3/bazi-pilot-r5/review.md), fixed in r6.

Saved r5 sentences, checked against charts computed from the pilot's own profiles:

- overseas #3: “按五行简单计数，这段时间木2、火4、土2、金0、水0”. The count is the natal chart's
  wuxing_count; no period has one (r3 overseas #1 wrote the same of “这个月”);
- luck cycles #1: “日主为日主乙木乙木”; luck cycles #3, after its repair: “第一步第1步大运丙辰”;
- investment #1, a refusal: “而‘全投’本身也超出八字能判断的范围” denies that bazi can judge
  going all in, yet the trade check asked for a repair.

Each change has its guards: what is still refused around it (another item in the sentence, a
denial then a statement, an outer negation, a degree word, a double negation, a statement again
after a turn) and what still passes.
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
from tests.pipeline.test_runner_bazi import NEXT_MONTH, SHANGHAI, make, written  # noqa: F401

# The saved clause; the rest of the sentence names overseas #3's own pillars.
R5_COUNT = "按五行简单计数，这段时间木2、火4、土2、金0、水0，火偏多而金水不显。"
R3_COUNT = "从五行计数看，这个月木2、火4、土2、金0、水0，火偏多、金水缺。"
R5_MASTER = "结合月令在木、日主为日主乙木乙木，可以理解为自身与同伴的力量不弱。"
R5_STAGE = "从排法看，第一步第1步大运丙辰天干丙为伤官的主题是创新与质疑。"
R5_TRADE = (
    "流年以劫财、比肩为主题，容易放大冲动与资源边界问题，而“全投”本身也超出八字能判断的范围，"
    "更关键是先核实自己的财务缓冲和风险承受能力。"
)
COUNT = "五行计数是原局（出生八字）的，不是这段时间的"
TRADE = "八字不能推出仓位、买卖时点或投入节奏"


@pytest.fixture
async def luck(make):  # noqa: F811
    chart, _ = await computed(make, DAYUN_CASE, DAYUN_CASE["question"])
    return chart


@pytest.fixture
async def money(make):  # noqa: F811
    chart, _ = await computed(make, INVESTMENT_CASE, INVESTMENT)
    return chart


# ---- the natal count said of a period ------------------------------------------------------


async def test_a_natal_count_said_of_a_period(money):
    for text in (
        R5_COUNT,
        R3_COUNT,
        "流月丙午火旺，这个月木2、火4、土2、金0、水0。",  # another item in the sentence
        "原局如此，这段时间木2、火4、土2、金0、水0。",  # 原局 earlier, the period nearer
        "不是原局的计数，而是这个月木2、火4、土2、金0、水0。",  # a denial, then a statement
        "这不是原局，这段时间木2、火4、土2。",  # 原局 denied
        "不能说这个月不是木2、火4、土2。",  # an outer negation
        "这个月并非不是木2、火4、土2。",  # a double negation
        "下个月五行大约是木2、火4、土2。",  # a degree word
        "原局木2、火4、土2，但其实这段时间也是木2、火4、土2。",  # again after a turn
    ):
        assert has(refused(money, text), COUNT), text
    for text in (
        "原局五行计数木2、火4、土2、金0、水0，火偏多。",
        "按五行简单计数，原局木2、火4、土2、金0、水0，这段时间流月丙午火旺。",
        "这段时间看原局，木2、火4、土2、金0、水0。",  # the nearest scope is the natal one
        "木2、火4、土2、金0、水0是出生八字的计数。",
        "从五行计数看，木4、土3、水1、火金为0，木土偏多。",  # no period (r5 luck cycles #1)
        "流月丙午（6月6日至7月7日）火旺。",
    ):
        assert not has(refused(money, text), COUNT), text


async def test_the_sheet_says_the_count_is_natal(make):  # noqa: F811
    runtime, composer, _ = make(written, birth=SHANGHAI)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    sheet = composer.seen[0][0][1]["content"]
    assert (
        "原局五行简单计数（出生八字的天干地支各算一个，不是旺衰权重，也不是这段时间的分布）"
        in sheet
    )


# ---- a label, a value or a stage written twice -----------------------------------------------


async def test_a_label_or_value_written_twice(luck):
    problems = refused(luck, R5_MASTER)
    assert has(problems, "“日主为日主”把“日主”写了两遍")
    assert has(problems, "“乙木乙木”把“乙木”写了两遍")
    assert has(refused(luck, R5_STAGE), "“第一步第1步大运”把大运的步数写了两遍")
    assert has(refused(luck, "你的日柱是日柱乙亥。"), "“日柱是日柱”把“日柱”写了两遍")
    for text in (
        "日主乙木，乙木像花草藤蔓。",
        "第一步、第二步大运各管十年。",
        "从第3步到第4步大运，主题由正财转为偏财。",
        "流年丙午、流月丙午都提示竞争。",
        "日主是乙木。",
    ):
        assert not has(refused(luck, text), "写了两遍"), text


# ---- investment: a disclaimer after the action -----------------------------------------------


async def test_a_trade_said_to_be_beyond_bazi_passes(money):
    assert not has(refused(money, R5_TRADE), TRADE)
    assert not has(refused(money, "流年劫财，“全投”不是八字能判断的。"), TRADE)
    for text in (
        "流年以劫财为主题，不能说“全投”超出八字能判断的范围。",  # an outer negation
        "流年以劫财为主题，“全投”不一定超出八字能判断的范围。",  # a degree word
        "流年以劫财为主题，“全投”并非超出八字能判断的范围。",  # a denial of the disclaimer
        "流年以劫财为主题，“全投”超出八字能判断的范围，但8月适合加仓。",  # after a turn
        "流年劫财，“全投”超出八字能判断的范围，流月丙午适合加仓。",  # another item
        "流年以劫财为主题，适合全投，这超出八字能判断的范围。",  # a statement first
    ):
        assert has(refused(money, text), TRADE), text


# ---- end to end -----------------------------------------------------------------------------


async def test_a_natal_count_for_a_period_is_repaired(make):  # noqa: F811
    extra = "按五行简单计数，这段时间木2、火4、土2、金0、水0。"
    runtime, composer, _ = make(lambda m: written(m, extra=extra), written, birth=SHANGHAI)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert has(info["problems"][0], COUNT)
    assert f"出问题的句子：“{extra}”" in composer.seen[1][0][-1]["content"]


async def test_the_r5_disclaimer_is_submitted_without_repair(make):  # noqa: F811
    runtime, _, _ = make(
        lambda m: written(m, extra=R5_TRADE), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert any(R5_TRADE in section["body"] for section in outcome.data["reading"]["sections"])
