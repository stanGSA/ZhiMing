"""Bazi pilot r18 findings (docs/verification/p3/bazi-pilot-r18/review-claude.md), fixed in r19.

Known escapes (owner, 2026-11-16), all passed by every check:

- Trait #1: “你正处在……首步大运辛未（……）所说的这一步大运中，按逆排走到后半段” in 2026 (己巳).
- Luck cycles #1: “第1步大运丙辰天干丙为伤官是上一步大运的主题” for the 4th cycle (the 3rd is 戊午).
- Luck cycles #2: “前一步是日柱乙亥地支亥所在那一步”, a natal pillar as a cycle.
- Luck cycles #3: “第5步大运庚申，主题会转向创新与质疑”; 庚 is 正官 for 乙, 创新与质疑 is 伤官's.
- Typed birth #1: “9月上中旬流月丁酉与本命月柱庚辰地支六合（9月7日至10月8日）”, a bare part of a
  month right before a flow month that begins on 9月7日.
- Investment #1, layer “5月到8月”: “……只用小比例、可承受损失的部分去验证判断”, a trial with a
  small part of the money for the period.

Guards next to each new refusal: what still passes (the right value, a denial, another time).
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
    (Path(__file__).parent / "fixtures/bazi_pilot_r18_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 15, 12, 11, tzinfo=UTC)  # the r18 pipeline run
STAGE = "当成了现在这步大运"
PREVIOUS = "当前大运的前一步是第3步戊午"
NATAL = "是原局的柱，不是大运"
THEME = "大运庚申的天干庚对日主是正官，主题是职责与规范"
START = "紧接的流月丁酉在9月7日至10月8日"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r19-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r19-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r19-{case_id}")
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
async def trait(run_at):
    runtime, *_ = await run_at("bazi_pilot_trait", written)
    return runtime.session


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


@pytest.fixture
async def typed(run_at):
    runtime, *_ = await run_at("bazi_pilot_typed_birth", written)
    return runtime.session


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


# ---- the first cycle as now, with “正” alone and “所说的” -------------------------------------

FIRST = "首步大运辛未（1997年交运，2007年换下一步）"
CURRENT = "第3步大运己巳（2017年交运，2027年换下一步）"


async def test_the_r18_trait_stage_is_refused(trait):
    assert has(problems(trait, FIXTURE["trait_stage"]), STAGE)


@pytest.mark.parametrize(
    "text",
    [f"你正处在{FIRST}所指的这一步大运中。", f"你现在处在{FIRST}所说的这个阶段。"],
)
async def test_the_first_cycle_as_now_is_refused(trait, text):
    assert has(problems(trait, text), STAGE), text


@pytest.mark.parametrize(
    "text",
    [
        f"你正处在{CURRENT}所说的这一步大运中。",
        f"你在{FIRST}所说的这一步大运里打下了底子。",  # no “now”
    ],
)
async def test_the_current_cycle_and_a_past_one_pass(trait, text):
    assert not has(problems(trait, text), STAGE), text


# ---- a cycle named, then said to be the one before or after -----------------------------------


async def test_the_r18_previous_named_first_is_refused(luck):
    assert has(problems(luck, FIXTURE["previous_named"]), PREVIOUS)


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("第2步大运丁巳是上一步。", PREVIOUS),
        ("第1步大运丙辰是下一步大运。", "当前大运的后一步是第5步庚申"),
        ("第3步大运戊午不是上一步。", PREVIOUS),  # the right cycle denied
    ],
)
async def test_wrong_cycles_named_first_are_refused(luck, text, words):
    assert has(problems(luck, text), words), text


@pytest.mark.parametrize(
    "text",
    [
        "第3步大运戊午天干戊为正财是上一步大运的主题。",
        "第5步大运庚申是下一步。",
        "第1步大运丙辰不是上一步。",  # a wrong cycle denied
    ],
)
async def test_right_cycles_named_first_pass(luck, text):
    assert not has(problems(luck, text), "当前大运的"), text


# ---- a natal pillar as the cycle before or after -----------------------------------------------


async def test_the_r18_natal_pillar_as_previous_is_refused(luck):
    assert has(problems(luck, FIXTURE["natal_neighbour"]), NATAL)


@pytest.mark.parametrize(
    "text",
    [
        "前一步是第3步大运戊午。",
        "前一步不是日柱乙亥。",  # denied
        "日柱乙亥地支亥与前一步大运无关。",
    ],
)
async def test_other_neighbours_pass(luck, text):
    assert not has(problems(luck, text), NATAL), text


# ---- a cycle's theme ---------------------------------------------------------------------------


async def test_the_r18_wrong_theme_is_refused(luck):
    assert has(problems(luck, FIXTURE["theme"]), THEME)


@pytest.mark.parametrize(
    "text",
    [
        "2033年接上的第5步大运庚申，主题会转向职责与规范。",
        "第4步大运己未（2023年交运，2033年换下一步），主题是机会与调配。",
        "第1步大运丙辰的主题是创新与质疑。",
    ],
)
async def test_right_themes_pass(luck, text):
    assert not has(problems(luck, text), "对日主是"), text


# ---- a bare part of a month before a flow month -------------------------------------------------


async def test_the_r18_bare_part_is_refused(typed):
    assert has(findings(typed, FIXTURE["part_title"], FIXTURE["part"]), START)


@pytest.mark.parametrize(
    "body",
    [
        "7月上旬流月甲午提示责任。",  # 甲午 within the range is 7月1日至7日
        "9月7日起流月丁酉与本命月柱庚辰地支六合（9月7日至10月8日）提示联结。",
        "9月上中旬多留意情绪，流月丁酉的主题是探索。",  # no flow month right after
    ],
)
async def test_right_starts_pass(typed, body):
    assert not has(findings(typed, FIXTURE["part_title"], body), START), body


# ---- a trial with a small part of the money ------------------------------------------------------


async def test_the_r18_small_trial_is_refused(money):
    args = {
        "summary": "整体平稳。",
        "sections": [{"title": FIXTURE["trial_title"], "body": FIXTURE["trial"], "ref_ids": []}],
    }
    found = [p for p, _ in Bazi(None).section_findings(args, [], money)]
    assert TRADE_PROBLEM in found or TRADE_PROBLEM in problems(money, FIXTURE["trial"])


@pytest.mark.parametrize(
    "text",
    [
        "这段时间只用小额资金去尝试。",
        "这段时间可以拿出一小部分积蓄去试水。",
        "这段时间不能说不要用小比例资金去验证。",  # an outer negation
        "这段时间不是不建议用小部分钱去试。",  # a double negation
        "这段时间不要全投，但可以用小部分钱去试。",  # a statement after a turn
    ],
)
async def test_small_trials_for_a_time_are_refused(money, text):
    assert TRADE_PROBLEM in problems(money, text), text


@pytest.mark.parametrize(
    "text",
    [
        "这段时间不要用小比例资金去试。",
        "这段时间别只用小部分钱去验证，先把账算清楚。",
        "这段时间用小部分时间去验证想法。",
        "如果你正处在这样的节奏里，更稳妥的做法是把大额投入的事往后放，先用小步验证自己的判断。",
        "想尝试就用小比例、可承受损失的部分，保持节奏而不是一次押满。",  # no time
    ],
)
async def test_other_small_steps_pass(money, text):
    assert TRADE_PROBLEM not in problems(money, text), text
