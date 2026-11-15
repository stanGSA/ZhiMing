"""Bazi pilot r17 findings (docs/verification/p3/bazi-pilot-r17/review-claude.md), fixed in r18.

- Investment #3, a false rejection that degraded the reading: both drafts wrote “……流月丙午与本命
  月柱庚子地支冲（6月6日至7月7日）、与时柱辛亥（天干辛为偏财）……”; the relation's 地支 earlier in
  the clause sent the right 偏财 of the hour stem to the hidden-stem check.
- Investment #2, a known escape (owner, 2026-11-15): the summary's “明年……更适合以保守、分散、先保
  生活底线的方式管理资金”, a manner of investing recommended for the year.

Guards next to each change: what still passes next to the new refusal, and what is still refused
next to the relaxed one (another item in the sentence, a denial then a statement, an outer
negation, a degree word, a double negation, a statement again after a turn).
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
    (Path(__file__).parent / "fixtures/bazi_pilot_r17_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 14, 21, 35, tzinfo=UTC)  # the r17 pipeline run
HIDDEN = "这次的地支藏干里没有"
RELATION = "流月丙午与本命月柱庚子地支冲（6月6日至7月7日）、"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r18-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r18-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r18-{case_id}")
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


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


# ---- a stem's ten god after a relation's 地支 ---------------------------------------------------


async def test_the_r17_stem_god_passes(money):
    assert not has(problems(money, FIXTURE["stem_god"]), HIDDEN)


async def test_the_r17_stem_god_after_a_relation_passes(money):
    text = f"流月丙午（十神劫财）与{RELATION}与时柱辛亥（天干辛为偏财）有天干合，留意冲动消费。"
    assert not problems(money, text)


@pytest.mark.parametrize(
    "text",
    [
        # another item in the sentence: a hidden god the chart lacks
        f"{RELATION}与时柱辛亥（天干辛为偏财）相合，地支藏干里也有偏财。",
        f"{RELATION}与时柱辛亥地支亥里藏着偏财。",  # a hidden stem named, not 天干X为
        f"{RELATION}地支里没有七杀，但其实地支藏干里有偏财。",  # a denial then a statement
        f"{RELATION}不能说时柱的地支里没有偏财。",  # an outer negation
        f"{RELATION}地支藏干里完全有偏财。",  # a degree word
        f"{RELATION}地支藏干不含偏财，不过地支藏干里其实有偏财。",  # after a turn
    ],
)
async def test_hidden_gods_are_still_checked(money, text):
    assert has(problems(money, text), HIDDEN), text


@pytest.mark.parametrize(
    ("text", "words"),
    [
        (f"{RELATION}与时柱辛亥（天干辛为正财）有天干合。", "天干辛对日主丁是偏财"),
        (f"{RELATION}与年柱丙寅（天干丙为偏财）相关。", "天干丙对日主丁是劫财"),
        (f"{RELATION}与时柱辛亥（天干辛不为偏财）有天干合。", "天干辛对日主丁是偏财"),
        ("时柱辛亥（天干辛为七杀）。", "天干辛对日主丁是偏财"),
    ],
)
async def test_wrong_stem_gods_after_a_relation_are_refused(money, text, words):
    assert has(problems(money, text), words), text


async def test_the_r17_investment_drafts_are_repaired_without_degrading(run_at):
    _, outcome, composer = await run_at(
        "bazi_pilot_investment_risk", *FIXTURE["investment_drafts"], written
    )
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    repair = composer.seen[1][0][-1]["content"]
    assert "2月4日起：摩擦增多，宜守不宜押" in repair  # the first draft's real title problem
    assert HIDDEN not in repair


# ---- a spread manner of investing recommended for the year -------------------------------------


async def test_the_r17_spread_summary_is_refused(money):
    assert TRADE_PROBLEM in problems(money, FIXTURE["spread_summary"])


@pytest.mark.parametrize(
    "text",
    [
        "明年更适合分散投资。",
        "明年建议分散配置，留足底线。",
        "明年以分散为主。",
        "不能说明年不适合分散投入。",  # an outer negation
        "明年不是不建议分散配置。",  # a double negation
        "明年不宜全投，但其实适合分散投入。",  # a statement after a turn
    ],
)
async def test_spread_investing_recommended_for_a_time_is_refused(money, text):
    assert TRADE_PROBLEM in problems(money, text), text


@pytest.mark.parametrize(
    "text",
    [
        "明年不适合分散投资，也不适合全投。",
        "明年情绪起伏时注意力容易分散。",
        "明年更适合把精力分散到学习和工作上，而不是盯盘。",
        "全年看，把“全投”换成“分批、留底、按预算”更稳妥。",  # r8 investment #1 (owner: passes)
        "如果你正在考虑大额投入，先把生活费和应急钱单独留出来，任何操作都设好上限。",  # r17 #1
    ],
)
async def test_other_spreads_and_restraint_pass(money, text):
    assert TRADE_PROBLEM not in problems(money, text), text
