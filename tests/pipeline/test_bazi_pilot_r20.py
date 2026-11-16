"""Bazi pilot r19 findings (docs/verification/p3/bazi-pilot-r19/review-claude.md), fixed in r20.

Known escapes, all passed by every check:

- Luck cycles #2: “第1步大运丙辰天干丙为伤官对应的是前一步第3步大运戊午，2013年交运，那时天干带伤官
  主题” for the 4th cycle: the first cycle named as the one before, and 戊午 given 伤官 (戊 is 正财
  for 乙), the first cycle's ten god again.
- Investment #3, layer “5月到年底”: “这段时间的波动更支持你保留余地、分批规划，而不是一次性押上”
  (owner, 2026-11-16: a known escape), a pace the period is said to favour.

False rejections, each repaired without degrading:

- Investment #1's first draft, for “全年看，适合把‘全投’改成‘先核实、再规划’”, which recommends
  verifying, not a trade.
- Luck cycles #1 and #3, first drafts: “前一步是{{R?前一步戊午}}——第3步大运戊午（……），下一步是
  第5步大运庚申（……）” and “前一步是日主乙木所对应的第3步大运戊午，下一步是第5步大运庚申” were
  refused as if 庚申 followed 戊午; both name the current cycle's neighbours. The second also
  writes the day master where the cycle belongs, now refused for that.
- Found while guarding the above: “下一步不是第5步大运庚申” passed, the denial before the label
  unread.

Guards next to each change: what still passes (the right value, a denial, another time) and,
next to the relaxed rejection, what is still refused.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from pipeline.bazi import TRADE_PROBLEM, Bazi
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES, has
from tests.pipeline.test_bazi_pilot_r10 import TYPED_PROFILE
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r19_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 16, 10, 36, tzinfo=UTC)  # the r19 pipeline run
PREVIOUS = "当前大运的前一步是第3步戊午"
NEXT = "当前大运的后一步是第5步庚申"
STEM_GOD = "大运戊午的天干戊对日主是正财"
DAY_MASTER = "日主乙木是原局的日主，不对应哪一步大运"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r20-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r20-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r20-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        if outcome.status == "ask_user":
            outcome = await runtime.turn(case["clarification"])
        assert outcome.status == "submit_reading", outcome.text
        return runtime, outcome, composer

    yield build
    for runtime in runtimes:
        runtime.close()


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


def findings(session, title: str, body: str) -> list[str]:
    args = {"summary": "整体平稳。", "sections": [{"title": title, "body": body, "ref_ids": []}]}
    return [p for p, _ in Bazi(None).section_findings(args, [], session)]


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


# ---- a cycle named first as the one before (“对应的是 / 指的是”) --------------------------------


async def test_the_r19_previous_named_first_is_refused(luck):
    assert has(problems(luck, FIXTURE["previous_named"]), PREVIOUS)


@pytest.mark.parametrize(
    "text, words",
    [
        ("第1步大运丙辰对应前一步。", PREVIOUS),
        ("第1步大运丙辰指的是前一步大运。", PREVIOUS),
        ("首步大运丙辰对应的是上一步。", PREVIOUS),
        ("第2步大运丁巳对应的是前一步。", PREVIOUS),
        ("第1步大运丙辰对应的是后一步。", NEXT),
        # An outer negation states the claim again.
        ("不能说第1步大运丙辰不对应前一步。", PREVIOUS),
    ],
)
async def test_wrong_cycles_named_first_with_correspond_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


@pytest.mark.parametrize(
    "text",
    [
        "第3步大运戊午对应的是前一步。",
        "第3步大运戊午对应的就是前一步。",
        "第5步大运庚申对应的是下一步。",
        "第1步大运丙辰并不对应前一步。",
    ],
)
async def test_right_or_denied_neighbours_pass(luck, text):
    assert problems(luck, text) == [], text


# ---- the next step after a named previous one ---------------------------------------------


@pytest.mark.parametrize("key", ["next_after_previous", "day_master_previous"])
async def test_the_r19_next_after_previous_is_not_counted_from_it(luck, key):
    assert not has(problems(luck, FIXTURE[key]), NEXT), FIXTURE[key]
    assert not has(problems(luck, FIXTURE[key]), "当前大运的后一步是第4步己未")


async def test_the_r19_day_master_as_previous_is_refused(luck):
    assert has(problems(luck, FIXTURE["day_master_previous"]), DAY_MASTER)


@pytest.mark.parametrize(
    "text",
    [
        "前一步是——第3步大运戊午（2013年交运），下一步是第5步大运庚申（2033年交运）。",
        "第3步大运戊午之后，下一步是第4步大运己未。",
        "第3步大运戊午（2013年交运），下一步是第4步大运己未。",
        "前一步不是日主乙木所对应的那一步，而是第3步大运戊午。",
        "日主乙木所对应的五行是木，前一步是第3步大运戊午。",
        "不能说下一步不是第5步大运庚申。",
        "下一步不是第6步大运辛酉。",
    ],
)
async def test_named_neighbours_pass(luck, text):
    assert problems(luck, text) == [], text


@pytest.mark.parametrize(
    "text, words",
    [
        ("前一步是日主乙木所对应的第3步大运戊午，下一步是第4步大运己未。", NEXT),
        ("前一步是第2步大运丁巳，下一步是第5步大运庚申。", PREVIOUS),
        ("前一步是日主乙木所对应的第3步大运戊午，但下一步是第4步大运己未。", NEXT),
        # Denials of the right neighbour, with the label between: alone, after a named
        # previous one, and a double negation of a wrong one.
        ("下一步不是第5步大运庚申。", NEXT),
        ("前一步不是第3步大运戊午。", PREVIOUS),
        ("前一步是第3步大运戊午，下一步不是第5步大运庚申。", NEXT),
        ("前一步是——第3步大运戊午，下一步并非不是第6步大运辛酉。", NEXT),
        ("下一步是日元乙木所在的第5步大运庚申。", DAY_MASTER),
    ],
)
async def test_wrong_named_neighbours_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


# ---- a cycle's stem given another ten god ---------------------------------------------------


async def test_the_r19_cycle_ten_god_is_refused(luck):
    assert has(problems(luck, FIXTURE["previous_named"]), STEM_GOD)


@pytest.mark.parametrize(
    "text, words",
    [
        ("第3步大运戊午，2013年交运，那时天干带伤官主题。", STEM_GOD),
        ("前一步第3步大运戊午，2013年交运，那时天干带伤官主题。", STEM_GOD),
        ("第5步大运庚申（2033年交运），天干为伤官。", "大运庚申的天干庚对日主是正官"),
        # A double negation and an outer negation state it again.
        ("第3步大运戊午那时天干并非不带伤官主题。", STEM_GOD),
        ("不能说第3步大运戊午那时天干不带伤官主题。", STEM_GOD),
    ],
)
async def test_wrong_cycle_ten_gods_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


@pytest.mark.parametrize(
    "text",
    [
        "第3步大运戊午，2013年交运，那时天干带正财主题。",
        "第3步大运戊午这十年的天干为正财。",
        "首步大运丙辰，1993年交运，那时天干带伤官主题。",
        "第5步大运庚申（2033年交运），天干为正官。",
        "第3步大运戊午，那时天干不是伤官，而是正财。",
        "第3步大运戊午那时天干并不带伤官主题。",
        "第4步大运己未天干己为偏财，主题是机会与调配。",
    ],
)
async def test_right_or_denied_cycle_ten_gods_pass(luck, text):
    assert problems(luck, text) == [], text


async def test_a_written_stem_is_left_to_the_stem_check(luck):
    found = problems(luck, "第4步大运己未天干己为正官。")
    assert has(found, "“天干己为正官”与计算不符")
    assert not has(found, "大运己未的天干己对日主是")


# ---- a pace the period favours (“更支持你……分批规划”) ------------------------------------------


async def test_the_r19_favoured_batch_is_refused(money):
    assert TRADE_PROBLEM in findings(money, FIXTURE["batch_title"], FIXTURE["batch"])


@pytest.mark.parametrize(
    "body",
    [
        "这段时间的波动更支持分批规划。",
        "这段时间的波动更加支持你分批投入。",
        # A denial turned back, a double negation, a turn after a denial.
        "不能说这段时间不支持你分批规划。",
        "这段时间并非不支持你分批规划。",
        "这段时间的波动不支持你分批规划，但支持你分批投入。",
    ],
)
async def test_favoured_batches_for_a_time_are_refused(money, body):
    assert TRADE_PROBLEM in findings(money, FIXTURE["batch_title"], body), body


@pytest.mark.parametrize(
    "body",
    [
        "这段时间的波动并不支持你分批规划，先把底线守住。",
        "这段时间有家人支持，先把预算和底线写清楚。",
        "这段时间更支持你保留余地、先核实财务状况，而不是一次性押上。",
        "这段时间流月的正印支持你学习理财知识。",
    ],
)
async def test_other_support_passes(money, body):
    assert TRADE_PROBLEM not in findings(money, FIXTURE["batch_title"], body), body


# ---- the trade swapped for verifying ------------------------------------------------------


async def test_the_r19_swap_for_verifying_passes(money):
    assert problems(money, FIXTURE["swap"]) == []


async def test_the_r19_investment_draft_is_accepted_first(run_at):
    _, _, composer = await run_at(
        "bazi_pilot_investment_risk", lambda messages: FIXTURE["investment_draft"], written
    )
    assert len(composer.seen) == 1


@pytest.mark.parametrize(
    "text",
    [
        "全年看，适合把“全投”换成“先学清楚、再做计划”。",
        "全年看，适合把全投改为先核实、再规划。",
        "明年适合把积蓄全投改成先核实、再规划。",
    ],
)
async def test_swaps_for_verifying_pass(money, text):
    assert problems(money, text) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "明年更适合把‘全投’改成‘有边界地参与’。",  # owner, still refused
        "全年看，适合把“全投”改成“分批买入”。",
        "全年看，更适合把“全投”改成“小步验证”。",
        "全年看，最适合把“全投”改成“先核实、再少量买入”。",
        "全年看，适合把“全投”改成“先核实”再全投。",
        "全年看，适合把“全投”改成“不是先核实而是分批买入”。",
        "全年看，适合把“全投”改成“先核实、再规划”，再分批买入。",
        # An outer negation, a double negation, a turn that recommends the trade again.
        "全年看，不能说适合把“全投”改成“先核实、再规划”。",
        "全年看，不是不适合直接全投，把“全投”改成“先核实”也行。",
        "全年看，适合把“全投”改成“先核实、再规划”，但其实还是适合全投。",
    ],
)
async def test_swaps_that_still_trade_are_refused(money, text):
    assert TRADE_PROBLEM in problems(money, text), text
