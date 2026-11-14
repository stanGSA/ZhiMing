"""Bazi pilot r16 findings (docs/verification/p3/bazi-pilot-r16/review-claude.md), fixed in r17.

- Luck cycles #1, a known escape: the repair of “前一步是第1步大运丙辰” wrote “走到这一步之前的那
  十年，天干为第1步大运丙辰天干丙为伤官”; the cycle before the 4th (己未) is the 3rd (戊午).
- Investment #3, a false rejection that lost the answer: both drafts were refused by the shared
  hard_claim for mentions of 稳赚 it did not read as mentions, “对‘稳赚’‘错过就没有’的话术保持距离”,
  “……不宜当作稳赚”, “面对‘稳赚不赔’‘错过就没有’这类说辞，先问清依据和退出条件”, and the reading
  degraded to the safety reply (owner, 2026-11-14: recognise all three).

Guards next to each change: what still passes next to the new refusal, and what is still refused
next to the relaxed one (another item in the sentence, a denial then a statement, an outer
negation, a degree word, a double negation, a statement again after a turn).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from common.output_policy import hard_claim
from pipeline.bazi import Bazi
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES, has
from tests.pipeline.test_bazi_pilot_r10 import TYPED_PROFILE
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r16_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 14, 6, 49, tzinfo=UTC)  # the r16 pipeline run
NEIGHBOUR = "当前大运的前一步是第3步戊午"
NEXT = "当前大运的后一步是第5步庚申"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r17-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r17-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r17-{case_id}")
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
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


# ---- the decade before or after the current cycle ----------------------------------------------


async def test_the_r16_decade_before_is_refused(luck):
    assert has(problems(luck, FIXTURE["decade"]), NEIGHBOUR)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("走到这一步之前的那十年，是第1步大运丙辰（1993年交运，2003年换下一步）。", NEIGHBOUR),
        ("上一个十年走的是第2步大运丁巳。", NEIGHBOUR),
        ("这一步之后的那十年是第3步大运戊午。", NEXT),
        ("这一步之前的那十年，并非第3步大运戊午。", NEIGHBOUR),  # the right cycle denied
        ("不能说这一步之前的那十年不是第1步大运丙辰。", NEIGHBOUR),  # an outer negation
        ("这一步之前的那十年不是不是第1步大运丙辰。", NEIGHBOUR),  # a double negation
    ],
)
async def test_wrong_neighbouring_decades_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


@pytest.mark.parametrize(
    "text",
    [
        "走到这一步之前的那十年，是第3步大运戊午（2013年交运，2023年换下一步）。",
        "这一步之后的那十年是第5步大运庚申。",
        "上一个十年走的是第3步大运戊午。",
        "这一步之前的那十年不是第1步大运丙辰。",  # a wrong cycle denied
        "这一步之前的那十年早已过去。",
    ],
)
async def test_right_neighbouring_decades_pass(luck, text):
    assert not has(problems(luck, text), "当前大运的"), text


@pytest.mark.parametrize(
    "text",
    [
        "第2步大运丁巳（2003年交运，2013年换下一步）的上一个十年是第1步大运丙辰。",
        "第2步大运丁巳（2003年交运，2013年换下一步），这一步之前的那十年是第1步大运丙辰。",
        "第2步大运丁巳的下一个十年是第3步大运戊午。",
        "第2步大运丁巳，当前大运之前的那十年是第3步大运戊午。",
        "上一个十年是第3步大运戊午，下一个十年是第5步大运庚申。",
        "前一步是第3步大运戊午，下一个十年是第5步大运庚申。",
        "上一个十年是第3步大运戊午，下一步是第5步大运庚申。",
    ],
)
async def test_decades_keep_the_named_cycle_as_reference(luck, text):
    assert problems(luck, text) == [], text


@pytest.mark.parametrize(
    "text",
    [
        "第2步大运丁巳的上一个十年是第3步大运戊午。",
        "第2步大运丁巳，下一个十年是第5步大运庚申。",
        "第2步大运丁巳，当前大运之前的那十年是第1步大运丙辰。",
        "上一个十年是第3步大运戊午，下一个十年是第4步大运己未。",
    ],
)
async def test_wrong_decades_are_checked_against_the_named_cycle(luck, text):
    assert has(problems(luck, text), "当前大运的"), text


# ---- 稳赚 quoted, doubted or dismissed (shared hard_claim) -------------------------------------


@pytest.mark.parametrize("index", [0, 1, 2])
def test_the_r16_gain_mentions_pass(index):
    assert hard_claim([FIXTURE["gain_mentions"][index]]) is None


@pytest.mark.parametrize(
    "text",
    [
        "对“稳赚”的话术保持距离，这笔投资稳赚。",  # another item in the sentence
        "不宜当作稳赚，但其实稳赚。",  # a denial then a statement
        "不能说创意不宜当作稳赚。",  # an outer negation
        "不必对“稳赚”的话术保持距离。",  # the doubt undone
        "对“稳赚”的话术完全不用保持距离。",  # a degree word
        "不是不宜当作稳赚。",  # a double negation
        "面对“稳赚不赔”这类说辞先问清依据，但这次确实稳赚。",  # a statement after a turn
        "面对“稳赚不赔”这类说辞，不必问清依据。",
        "对“稳赚”“错过就没有”的话术，要相信。",
        "这只股票“稳赚不赔”。",
        "“稳赚”的说法很可信。",
    ],
)
def test_promises_of_gain_are_still_refused(text):
    assert hard_claim([text]) == "稳赚", text


@pytest.mark.parametrize(
    "text",
    [
        "对任何“稳赚”说法都要求看到成本和最坏情况。",  # r9
        "如果你正被某个“稳赚”说法打动，先回到预算和规则上。",  # r11
        "别把一时的配合顺畅当成稳赚。",  # P2 r7
    ],
)
def test_earlier_gain_mentions_still_pass(text):
    assert hard_claim([text]) is None, text


async def test_the_r16_investment_draft_is_submitted(run_at):
    _, outcome, _ = await run_at("bazi_pilot_investment_risk", *FIXTURE["investment_drafts"])
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
