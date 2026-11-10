"""Bazi pilot r6 findings (docs/verification/p3/bazi-pilot-r6/review.md), fixed in r7.

- Investment #1–#3: nine sentences that hold back or deny a trade were refused by the trade
  check; investment #2's second draft was refused only for “谈不上是让人放心全押的一年” and the
  reading was degraded to keywords.
- Overseas #3: the title “中旬到月底” over 流月庚子 from 12月6日; typed birth #3: “年底两个月”
  over 流月戊戌 from 10月8日. The title check only asked for one cited period to overlap the
  title. Owner decision 2026-11-10: under a title naming part of a month, a cited flow month
  starting or ending more than two days outside it is refused.

Relaxations carry their guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

from datetime import date

import pytest

from pipeline import bazi
from pipeline.bazi import title_spans
from pipeline.compose import BAZI_SYSTEM
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import INVESTMENT_CASE, computed, has, refused
from tests.pipeline.test_runner_bazi import NEXT_MONTH, SHANGHAI, facts_in, make, written  # noqa: F401

TRADE = "八字不能推出仓位、买卖时点或投入节奏"
# Every sentence of the refused r6 investment drafts that raised the trade problem.
R6_HELD_BACK = (
    "这些流月只作节奏参考，不构成买卖时点。",
    "明年整体不算适合把积蓄全投进股市的一年，冲、害、刑、破等关系反复出现，容易伴随冲动、牵绊与判断松动的倾向。",
    "建议这段时间把“决定”放慢，涉及大额投入的事多找人复核。",
    "整体看，明年不像是适合一把投入的年份。",
    "明年更适合先稳住节奏、看清风险，再谈投入多少，别把全部积蓄押在一次判断上。",
    "明年整体谈不上是让人放心全押的一年，冲、害、刑、破等关系反复出现，容易伴随冲动、牵绊与判断松动的倾向。",
    "明年整体不算适合把积蓄全部投入股市的年份，首要是守住本金安全。",
    "流年丁未与本命月柱庚子地支害（2月4日至12月31日）则提示隐性摩擦、协作掣肘，合伙或跟风操作尤其要边界清楚。",
    "这段时间的应对不是找时机，而是把资金分出安全垫，给自己设一个冷静期再决定任何投入。",
)


@pytest.fixture
async def money(make):  # noqa: F811
    chart, _ = await computed(make, INVESTMENT_CASE, INVESTMENT)
    return chart


# ---- the trade check -------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", R6_HELD_BACK, ids=[f"r6-{i}" for i in range(9)])
async def test_the_r6_held_back_sentences_pass(money, sentence):
    assert not has(refused(money, sentence), TRADE)


async def test_what_only_looks_held_back_is_still_refused(money):
    for text in (
        "明年整体不算适合全投，流月辛丑适合小额度试探。",  # another item in the sentence
        "明年不算适合全投，但8月适合加仓。",  # a denial, then a statement after a turn
        "这些流月不构成买卖时点，但8月是买入时点。",
        "谈不上是让人放心全押的一年，但8月适合加仓。",
        "不能说明年不算适合全投。",  # an outer negation
        "明年不一定不算适合全投。",  # a degree word
        "8月不太不适合加仓。",
        "这些流月并非不构成买卖时点。",  # a double negation
        "谈不上不适合加仓的8月。",
        "8月适合跟风操作尤其要边界清楚。",  # a recommendation before the caution
        "8月适合大额投入，事后找人复核。",
        "8月再决定加仓。",  # a period sets the time of the deferred trade
        "流年以劫财为主题，不能说“全投”超出八字能判断的范围。",
    ):
        assert has(refused(money, text), TRADE), text


# ---- section titles --------------------------------------------------------------------------


def scope(title, start, end, cited, today):
    """What the code checks for these cited flow months; on a version without the stricter
    check (66c6bd5) that is title_findings alone."""
    stricter = getattr(bazi, "title_scope_findings", None)
    plain = bazi.title_findings(title, start, end, [(a, b) for a, b, _ in cited], today)
    return plain or (stricter(title, start, end, cited, today) if stricter else [])


def test_the_r6_titles_are_refused():
    # Overseas #3: America/Los_Angeles, range 2026-12-01..12-31; 流月庚子 from 12-06 18:52.
    (problem,) = scope(
        "中旬到月底：联结增多，但要防隐性牵扯",
        date(2026, 12, 1),
        date(2026, 12, 31),
        [(date(2026, 12, 6), date(2026, 12, 31), "流月庚子")],
        date(2026, 11, 9),
    )
    assert "12月11日至12月31日" in problem and "流月庚子在12月6日至12月31日" in problem
    # Typed birth #3: range 2026-07-01..12-31; 流月戊戌 10-08..11-07 under “年底两个月”.
    july, december = date(2026, 7, 1), date(2026, 12, 31)
    months = [
        (date(2026, 10, 8), date(2026, 11, 7), "流月戊戌"),
        (date(2026, 11, 7), date(2026, 12, 7), "流月己亥"),
        (date(2026, 12, 7), date(2026, 12, 31), "流月庚子"),
    ]
    (problem,) = scope(
        "年底两个月：先理顺自己，再谈关系", july, december, months, date(2026, 11, 10)
    )
    assert "流月戊戌在10月8日至11月7日" in problem


def test_titles_against_flow_months():
    july, december, today = date(2026, 7, 1), date(2026, 12, 31), date(2026, 11, 10)
    yi_wei = (date(2026, 7, 7), date(2026, 8, 7), "流月乙未")
    bing_shen = (date(2026, 8, 7), date(2026, 9, 7), "流月丙申")
    jia_wu = (date(2026, 6, 6), date(2026, 7, 7), "流月甲午")  # clipped to 7月1日 by the range
    geng_zi = (date(2026, 12, 7), date(2026, 12, 31), "流月庚子")
    ji_hai = (date(2026, 11, 7), date(2026, 12, 7), "流月己亥")
    for title, cited in (
        ("7月中到8月初：容易有直接碰撞", [yi_wei]),  # r4 typed birth #2: starts 4 days early
        ("12月上中旬：先稳住", [geng_zi]),  # ends 11 days late
        ("九月到年底先松后紧", [bing_shen]),  # r3 typed birth #3: mostly in August
        ("12月：收尾", [ji_hai]),  # 己亥 lies mostly in November
    ):
        assert scope(title, july, december, cited, today), title
    for title, cited in (
        ("12月7日起：重心转向秩序", [geng_zi]),
        ("12月：收尾", [geng_zi]),
        ("11月：各自坚持", [ji_hai]),  # runs on into December, mostly in November
        ("年底两个月：先理顺自己", [ji_hai, geng_zi]),
        ("7到9月：有联结也有拉扯", [jia_wu, yi_wei, bing_shen]),
        ("七八月是全年波动较明显的一段", [jia_wu, yi_wei]),
        ("这段时间的节奏", [geng_zi]),  # no time in the title
    ):
        assert scope(title, july, december, cited, today) == [], title


def test_month_pairs_in_titles_are_read():
    july, december, today = date(2026, 7, 1), date(2026, 12, 31), date(2026, 11, 10)
    assert title_spans("7到9月：关系", july, december, today) == [
        (date(2026, 7, 1), date(2026, 9, 30))
    ]
    assert title_spans("七八月是全年", july, december, today) == [
        (date(2026, 7, 1), date(2026, 8, 31))
    ]
    assert title_spans("十一二月要稳住", july, december, today) == [
        (date(2026, 11, 1), date(2026, 12, 31))
    ]
    assert title_spans("十一月", july, december, today) == [(date(2026, 11, 1), date(2026, 11, 30))]
    assert title_spans("1到2个月里先观察", july, december, today) == []


def test_the_prompt_asks_for_the_flow_month_boundaries():
    assert "按这一层所引流月的实际起止写" in BAZI_SYSTEM


async def test_a_part_of_month_title_is_repaired_with_the_title_quoted(make):  # noqa: F811
    def titled(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流月" and "己亥" in text
        ]
        return (
            "【表态】平稳\n【摘要】下个月整体平稳。\n"
            f"【分层】中下旬：留意协作\n{{{{{alias}}}}}提示你把精力放在长期目标上。\n【引用】{alias}\n"
            "【建议】\n- 先排序：把最重要的两件事写下来。\n【收尾】按自己的节奏来。"
        )

    runtime, composer, _ = make(titled, written, birth=SHANGHAI)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any("“中下旬：留意协作”这一层的标题" in p for p in info["problems"][0])
    assert "出问题的句子：“中下旬：留意协作”" in composer.seen[1][0][-1]["content"]
