"""Bazi pilot r15 findings (docs/verification/p3/bazi-pilot-r15-deepseek-flash/review-claude.md),
fixed in r16.

A fact error and known escapes (owner, 2026-11-14), all passed by every check:

- Trait #1: “你现在处在……首步大运辛未（1997年交运，2007年换下一步）这一阶段” in 2026, when the
  cycle is 己巳 from 2017; the trait sheet's only luck-cycle fact is the first one.
- Luck cycles #2: “木和水在数字上占得较多” after 木4、火0、土3、金0、水1.
- Luck cycles #3: “两处偏财线索呼应：时柱己卯（天干己为偏财）与年柱戊辰（天干戊为正财）”, the
  summary before its list (r7's escape, the other way round).
- Luck cycles #2 and trait #2: the convention “子时按23点换日” written where a cycle belongs.
- Investment #1, layer “2月到5月”: “更适合把‘先学清楚、再小步验证’放在前面”, a trial investment.

Two false rejections in investment #3: the second draft's “明年更适合把‘全部投入’的念头先搁一搁”
(a thought held back; the reading degraded), and the first draft's “倒推参与比例” read as 逆排.

Guards next to each change: what still passes next to a new refusal, and what is still refused
next to a relaxed one (another item in the sentence, a denial then a statement, an outer
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
    (Path(__file__).parent / "fixtures/bazi_pilot_r15_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 13, 23, 32, tzinfo=UTC)  # the r15 pipeline run
STAGE = "当成了现在这步大运"
COUNT = "原局五行计数是木4、火0、土3、金0、水1"
AGGREGATE = "与后面写的十神不符"
CONVENTION = "是排盘口径的约定，不是某一步大运"
DIRECTION = "正文不能写成逆排"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r16-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r16-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r16-{case_id}")
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


def refused(session, title: str, body: str) -> bool:
    return TRADE_PROBLEM in findings(session, title, body) or TRADE_PROBLEM in problems(
        session, body
    )


@pytest.fixture
async def trait(run_at):
    runtime, *_ = await run_at("bazi_pilot_trait", written)
    return runtime.session


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


# ---- the first cycle said to be where you are now --------------------------------------------

FIRST = "首步大运辛未（1997年交运，2007年换下一步）"
CURRENT = "第3步大运己巳（2017年交运，2027年换下一步）"


async def test_the_r15_trait_stage_is_refused(trait):
    assert has(problems(trait, FIXTURE["trait_stage"]), STAGE)


@pytest.mark.parametrize(
    "text",
    [
        f"你现在处在{FIRST}这一阶段。",
        f"你现在处在{FIRST}这一阶段，性格温和。",  # another item in the sentence
        f"你现在完全处在{FIRST}这个阶段。",  # a degree word
        f"你现在不是处在{CURRENT}这一阶段，而是现在处在{FIRST}这一阶段。",  # denial then statement
        f"不能说你现在不是处在{FIRST}这一阶段。",  # an outer negation
        f"你现在不是不处在{FIRST}这一阶段。",  # a double negation
        f"你现在并不处在{FIRST}这一阶段，但其实现在还处在{FIRST}这一阶段。",  # after a turn
        f"你现在并不处在{CURRENT}这一阶段。",  # the right cycle denied
    ],
)
async def test_the_first_cycle_as_now_is_refused(trait, text):
    assert has(problems(trait, text), STAGE), text


@pytest.mark.parametrize(
    "text",
    [
        f"你现在处在{CURRENT}这一阶段，按今天算已走到第10年。",
        f"你现在并不处在{FIRST}这一阶段。",
        f"你在{FIRST}这一阶段打下了学习的底子。",  # no “now”
        f"1997年9月27日起运（出生后3年1个月10天），{FIRST}说明你的排法是逆排。",  # r15 trait #3
    ],
)
async def test_the_current_cycle_and_a_past_one_pass(trait, text):
    assert not has(problems(trait, text), STAGE), text


async def test_the_trait_sheet_says_the_first_cycle_is_not_now(trait):
    lines = Bazi(None).context(trait)
    assert any("首步大运辛未只说明何时起运，不是现在这步大运" in line for line in lines)


# ---- a summary of the natal count, said “in numbers” ------------------------------------------


async def test_the_r15_count_summary_is_refused(luck):
    assert has(problems(luck, FIXTURE["count_summary"]), COUNT)


@pytest.mark.parametrize(
    "text",
    [
        "原局五行计数里，木和水在数字上占得较多。",
        "原局五行计数里，水在数量上偏多。",
        "原局五行计数里，土的数量最少。",
    ],
)
async def test_wrong_summaries_in_numbers_are_refused(luck, text):
    assert has(problems(luck, text), COUNT), text


@pytest.mark.parametrize(
    "text",
    [
        "原局五行计数里，木和土在数字上占得较多，火金为零。",
        "原局五行计数里，木的数量最多，水仅一处。",  # r15 luck cycles #3
        "原局五行计数里，并不是木和水在数字上占得较多。",  # a wrong summary denied
    ],
)
async def test_right_summaries_in_numbers_pass(luck, text):
    assert not has(problems(luck, text), COUNT), text


# ---- a ten-god summary before its list ---------------------------------------------------------


async def test_the_r15_aggregate_before_its_list_is_refused(luck):
    assert has(problems(luck, FIXTURE["aggregate"]), AGGREGATE)


@pytest.mark.parametrize(
    "text",
    [
        "原局里两柱都是偏财：时柱己卯（天干己为偏财）与月柱乙卯（天干乙为比肩）。",
        "这两处正财：时柱己卯（天干己为偏财）、年柱戊辰（天干戊为正财）。",
    ],
)
async def test_other_aggregates_before_their_list_are_refused(luck, text):
    assert has(problems(luck, text), AGGREGATE), text


@pytest.mark.parametrize(
    "text",
    [
        "这里有两处财星：时柱己卯（天干己为偏财）与年柱戊辰（天干戊为正财）。",
        "这两处并不都是偏财：时柱己卯（天干己为偏财）与年柱戊辰（天干戊为正财）。",
        "原局里有一处偏财：时柱己卯（天干己为偏财），年柱戊辰（天干戊为正财）则是正财。",
        "年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）分别带正财、偏财。",
    ],
)
async def test_right_aggregates_pass(luck, text):
    assert not has(problems(luck, text), AGGREGATE), text


# ---- the convention written where a luck cycle belongs -----------------------------------------


@pytest.mark.parametrize("index", [0, 1, 2])
async def test_the_r15_conventions_as_cycles_are_refused(luck, trait, index):
    session = trait if index == 2 else luck
    assert has(problems(session, FIXTURE["conventions"][index]), CONVENTION)


@pytest.mark.parametrize(
    "text",
    [
        "上一步是子时按23点换日。",
        "现在处在子时按23点换日这一步。",
        "子时按23点换日对应的大运已经过半。",
    ],
)
async def test_other_conventions_as_cycles_are_refused(luck, text):
    assert has(problems(luck, text), CONVENTION), text


@pytest.mark.parametrize(
    "text",
    [
        # r13, r12, r3 final answers.
        "第4步大运己未（2023年交运，2033年换下一步）的顺排起运和子时按23点换日所说明的排盘口径，都只是计算约定。",
        "子时按23点换日只是排盘口径的说明，不影响大运的顺序。",
        "按子时换日的可选口径子时按23点换日，若你出生在深夜，日柱会按次日算。",
        "下一步，子时按23点换日只影响日柱。",
    ],
)
async def test_the_convention_named_as_itself_passes(luck, text):
    assert not has(problems(luck, text), CONVENTION), text


async def test_the_sheets_say_the_convention_is_no_cycle(luck, trait):
    for session in (luck, trait):
        assert any(
            "的编号只说明排盘口径，不是某一步大运" in line for line in Bazi(None).context(session)
        )


# ---- a trial in small steps, recommended in a dated layer --------------------------------------


async def test_the_r15_small_step_trial_is_refused(money):
    assert refused(money, FIXTURE["trial_title"], FIXTURE["trial"])


@pytest.mark.parametrize(
    "body",
    [
        "这段时间更适合小步验证。",
        "适合先学清楚、再小步尝试。",
        "这段时间建议小步试水，边看边调。",
        "不能说不适合小步验证。",  # an outer negation
        "不是不建议小步投入。",  # a double negation
        "不建议一次投入，但其实适合小步验证。",  # a statement after a turn
    ],
)
async def test_small_step_trials_in_a_dated_layer_are_refused(money, body):
    assert refused(money, FIXTURE["trial_title"], body), body


@pytest.mark.parametrize(
    "body",
    [
        "这段时间不适合小步验证。",
        "如果你正处在这样的节奏里，更稳妥的做法是把大额投入的事往后放，先用小步验证自己的判断。",
        "流月乙巳提醒先用小范围验证检验新想法，不要一次下结论。",
    ],
)
async def test_small_steps_without_a_recommendation_pass(money, body):
    assert not refused(money, FIXTURE["trial_title"], body), body


# ---- a thought of the trade held back ---------------------------------------------------------


async def test_the_r15_held_thought_passes(money):
    assert TRADE_PROBLEM not in problems(money, FIXTURE["held"])


@pytest.mark.parametrize(
    "text",
    [
        "明年更适合把“全投”的想法放一放。",
        "这段时间最好把一次性投入的冲动先压一压。",
        "明年先把“全部投入”的打算暂时搁置。",
    ],
)
async def test_held_thoughts_pass(money, text):
    assert TRADE_PROBLEM not in problems(money, text), text


@pytest.mark.parametrize(
    "text",
    [
        "明年更适合把“全部投入”的念头付诸行动。",
        "明年更适合把“全部投入”的念头先搁一搁，再全仓买入。",  # another item in the sentence
        "明年不适合把“全部投入”的念头搁一搁，而是适合全部投入。",  # a denial then a statement
        "明年不能说更适合把“全部投入”的念头先搁一搁。",  # an outer negation
        "明年根本不必把“全部投入”的念头搁一搁。",  # a degree word
        "明年不是不适合把“全部投入”的念头先搁一搁。",  # a double negation
        "明年更适合把“全部投入”的念头先搁一搁，但其实更适合全部投入。",  # after a turn
    ],
)
async def test_turned_or_denied_holding_back_is_refused(money, text):
    assert TRADE_PROBLEM in problems(money, text), text


async def test_the_r15_investment_drafts_are_repaired_without_degrading(run_at):
    _, outcome, composer = await run_at(
        "bazi_pilot_investment_risk", *FIXTURE["investment_drafts"], written
    )
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    # The first draft's real problem stays; its 倒推 is no direction of the luck cycles.
    first = composer.seen[1][0][-1]["content"]
    assert "拆小、设好止损和退出条件" in first
    assert DIRECTION not in first


# ---- 倒推 outside the luck cycles ---------------------------------------------------------------


async def test_the_r15_back_calculation_passes(money):
    assert not has(problems(money, FIXTURE["reverse"]), DIRECTION)


@pytest.mark.parametrize(
    "text",
    [
        "用最坏情况倒推参与比例，你的大运是逆推的。",  # another item in the sentence
        "你的大运不是顺推，而是逆推。",  # a denial then a statement
        "不能说你的大运不是逆推。",  # an outer negation
        "你的大运完全是逆推的。",  # a degree word
        "你的大运并非不是逆推。",  # a double negation
        "你的大运不是逆推，但其实是逆推。",  # a statement again after a turn
        "起运按倒推从上一个节数到出生。",
    ],
)
async def test_directions_of_the_cycles_are_still_refused(money, text):
    assert has(problems(money, text), DIRECTION), text


@pytest.mark.parametrize("text", ["从目标倒推每月预算。", "把计划逆推回今天，先定最晚的节点。"])
async def test_back_calculations_pass(money, text):
    assert not has(problems(money, text), DIRECTION), text
