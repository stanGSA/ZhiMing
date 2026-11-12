"""Bazi pilot r11 findings (docs/verification/p3/bazi-pilot-r11/review.md), fixed in r12.

- Luck cycles #3: “往前一步是第1步大运丙辰” beside the 4th cycle (the one before is the 3rd, 戊午)
  and “按虚岁习惯大约在4岁多到5岁之间进入第一步大运” (start_age 6) passed every check. The sheet
  lists only the first and the current cycle, and no traditional age.
- Investment #1: the title “立春后到年中” was read as 年中 (5月–8月) alone and refused for 流月壬寅
  from 2月4日; its second draft's “如果你正被某个“稳赚”说法打动，先回到预算和规则上……” was read by
  the shared hard_claim as a promise, and the reading was degraded to the safety reply.
- Investment #3: “大额投入前先把……核实清楚”, “面对大额投入的诱惑”, “大额投入的念头” were read as
  “大额” recommending the trade; both drafts were refused and degraded to keywords.
- Owner, 2026-11-12: investment #2's “如果真想接触，先用不影响生活的金额熟悉规则” is no known escape.

The relaxations carry their guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

import json
from pathlib import Path

import pytest

from common.output_policy import hard_claim
from pipeline.bazi import Bazi
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import DAYUN_CASE, INVESTMENT_CASE, has
from tests.pipeline.test_runner_bazi import facts_in, make, written  # noqa: F401

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r11_review.json").read_text(encoding="utf-8")
)
NEIGHBOUR = "当前大运的前一步是第3步戊午"
VIRTUAL = "按传统岁数（虚岁），第一步大运在6岁交运"


async def session_for(make, case, question):  # noqa: F811
    runtime, composer, _ = make(written, written, birth=case["profile"])
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    return runtime.session, composer


@pytest.fixture
async def luck(make):  # noqa: F811
    session, composer = await session_for(make, DAYUN_CASE, DAYUN_CASE["question"])
    return session, composer


@pytest.fixture
async def money(make):  # noqa: F811
    session, _ = await session_for(make, INVESTMENT_CASE, INVESTMENT)
    return session


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


# ---- the cycles next to the current one ----------------------------------------------------


async def test_the_r11_neighbour_is_refused(luck):
    session, _ = luck
    assert has(problems(session, FIXTURE["neighbour"]), NEIGHBOUR)


async def test_neighbours_against_the_sequence(luck):
    session, _ = luck
    for text in (
        "往前一步是第1步大运丙辰。",
        "前一步大运丙辰的主题是伤官。",
        "上一步大运是首步大运丙辰。",
        "下一步是辛酉。",
        "往前一步是第3步大运丙辰。",  # the right number with the wrong cycle
        "往前一步并不是戊午。",  # the right cycle denied
        "往前一步不是戊午，但其实是丙辰。",  # a statement after a turn
    ):
        assert has(problems(session, text), "当前大运的"), text
    for text in (
        "往前一步是第3步大运戊午。",
        "前一步是戊午，下一步是第5步大运庚申。",
        "往前一步不是丙辰，而是戊午。",
        "往后一步要等2033年换运。",
        "首步大运丙辰（1993年交运，2003年换下一步）的下一步是丁巳。",  # counted from 丙辰
    ):
        assert not has(problems(session, text), "当前大运的"), text


async def test_the_r11_virtual_age_is_refused(luck):
    session, _ = luck
    assert has(problems(session, FIXTURE["virtual_age"]), VIRTUAL)


async def test_virtual_ages_against_the_start_age(luck):
    session, _ = luck
    for text in ("按虚岁算，5岁起运。", "虚岁大约4岁就进入第一步大运。"):
        assert has(problems(session, text), VIRTUAL), text
    for text in (
        "按虚岁算，6岁进入第一步大运。",
        "周岁约4岁多、虚岁6岁进入第一步大运。",
        "虚岁16岁换第二步大运。",
        "虚岁不等于周岁，4岁多是周岁。",
        "按虚岁算，并不是5岁起运。",
    ):
        assert not has(problems(session, text), VIRTUAL), text


async def test_the_sheet_names_the_neighbours_and_the_age(luck):
    _, composer = luck
    sheet = composer.seen[0][0][1]["content"]
    assert "前一步是第3步大运戊午（2013年交运）" in sheet
    assert "下一步是第5步大运庚申（2033年交运）" in sheet
    assert "第一步大运在6岁交运" in sheet


async def test_a_wrong_neighbour_is_repaired(make):  # noqa: F811
    sentence = "往前一步是第1步大运丙辰，主题偏向创新与质疑。"
    runtime, composer, _ = make(
        lambda m: written(m, extra=sentence),
        lambda m: written(m, extra="往前一步是第3步大运戊午，主题偏向竞争与共享。"),
        birth=DAYUN_CASE["profile"],
    )
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any(NEIGHBOUR in p for p in info["problems"][0])
    assert f"出问题的句子：“{sentence}”" in composer.seen[1][0][-1]["content"]


# ---- 立春 in a section title -----------------------------------------------------------------


def findings(session, sections) -> list[str]:
    args = {"summary": "整体平稳。", "sections": [{**s, "ref_ids": []} for s in sections]}
    return [problem for problem, _ in Bazi(None).section_findings(args, [], session)]


async def test_the_r11_spring_title_passes(money):
    assert findings(money, [FIXTURE["spring_section"]]) == []


async def test_spring_titles_against_flow_months(money):
    for title, body in (
        ("立春后到年中：摩擦增多", "流月壬寅、流月己酉提示节奏变化。"),  # 己酉 from 9月8日
        ("立春后到6月：压力", "流月丁未提示节奏变化。"),  # 7月7日–8月8日
        ("立春前到年中：压力", "流月壬寅提示节奏变化。"),  # 立春前 is not read as a start
    ):
        assert findings(money, [{"title": title, "body": body}]), title
    for title, body in (
        ("立春后到年中：摩擦增多", "流月壬寅、流月丙午提示节奏变化。"),
        ("立春起至6月：压力", "流月壬寅、流月乙巳提示节奏变化。"),
    ):
        assert findings(money, [{"title": title, "body": body}]) == [], title


# ---- 大额 before a trade that is only a temptation or a check -------------------------------

TRADE = "八字不能推出仓位、买卖时点或投入节奏"


@pytest.mark.parametrize("text", FIXTURE["trade_held_back"])
def test_the_r11_held_back_trades_pass(text):
    assert Bazi.trade_problems(text) == [], text


def test_the_r11_small_amount_passes():
    """Owner, 2026-11-12: no known escape, as r8 investment #1."""
    assert Bazi.trade_problems(FIXTURE["small_amount"]) == []


@pytest.mark.parametrize(
    "text",
    [
        "8月大额投入前先把资金安排确认清楚。",
        "如果你面对大额投入的冲动，先冷静。",
        "这段时间大额投入的想法放一放。",
    ],
)
def test_temptations_and_checks_pass(text):
    assert Bazi.trade_problems(text) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "8月大额投入。",
        "8月适合大额投入的计划。",  # a recommendation before the noun
        "8月适合大额投入的诱惑。",
        "8月大额投入前先加仓再核实。",  # another trade before the check
        "8月大额投入的念头放一放，9月适合加仓。",  # another item after a turn
        "8月大额投入前不用核实。",  # the check denied
        "8月是大额投入的好时机。",
        "8月未必要把大额投入的念头放一放。",  # an outer, weakening negation
        "8月适合大额投入，事后找人复核。",
    ],
)
def test_what_only_looks_held_back_is_still_refused(text):
    assert Bazi.trade_problems(text), text


async def test_a_held_back_trade_is_submitted_without_repair(make):  # noqa: F811
    text = FIXTURE["trade_held_back"][0]
    runtime, _, _ = make(
        lambda m: written(m, extra=text), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


# ---- a quoted 稳赚 in a condition, answered with restraint (shared hard_claim) ----------------


def test_the_r11_tempted_mention_passes():
    assert hard_claim([FIXTURE["gain_mention"]]) is None
    assert hard_claim(["若被“稳赚”的说法吸引，别急着动用积蓄。"]) is None


@pytest.mark.parametrize(
    "text",
    [
        "如果你被“稳赚”说法打动，就全仓买入。",  # no restraint answers it
        "如果你被“稳赚”说法打动，说明它确实稳赚。",  # a statement after it
        "如果你被“稳赚”说法打动，先回到预算，这笔投资稳赚。",  # another item in the sentence
        "不能说如果你被“稳赚”说法打动就要先冷静。",  # an outer negation
        "如果你被稳赚说法打动，先冷静。",  # not quoted
        "如果你被“稳赚”说法打动。",
        "“稳赚”说法是真的，如果你被打动先冷静。",
    ],
)
def test_what_only_looks_tempted_is_still_refused(text):
    assert hard_claim([text]) == "稳赚", text


async def test_a_tempted_mention_is_submitted_without_repair(make):  # noqa: F811
    text = FIXTURE["gain_mention"]
    runtime, _, _ = make(
        lambda m: written(m, extra=text), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
