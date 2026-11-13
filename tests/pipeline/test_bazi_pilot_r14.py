"""Bazi pilot r13 findings (docs/verification/p3/bazi-pilot-r13/review-claude.md), fixed in r14.

Owner, 2026-11-13: three known escapes, all passed by every check.

- Luck cycles #3: after the right count 木4、火0、土3、金0、水1, “木水出现得多，火与金则一个也没有
  出现”; 水 is 1 and 土 3. No check read a summary of the natal count.
- Typed birth #1: “中旬到8月初，流月乙未” for 乙未 from 7月7日; a range from a part of a month
  before a flow month names where it begins, like “X旬之后 / 起”.
- Career #3: “首步大运己丑（1998年交运，2008年换下一步）显示你正走在这步十年大运的后半段” in
  2026, when the cycle is 丁亥 from 2018.

Guards next to each new refusal: what is still refused (another item in the sentence, a denial
then a statement, an outer negation, a double negation, a statement again after a turn) and what
still passes (a right summary, a flow month running when the range begins).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from pipeline.bazi import Bazi, batch_recommended
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES, has
from tests.pipeline.test_bazi_pilot_r10 import TYPED_PROFILE
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r13_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 12, 17, 58, tzinfo=UTC)  # the r13 pipeline run
COUNT = "原局五行计数是木4、火0、土3、金0、水1"
START = "说流月乙未从这时开始"
STAGE = "当成了现在这步大运"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r14-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r14-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r14-{case_id}")
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


# ---- a summary of the natal five-element count ----------------------------------------------


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime.session


async def test_the_r13_count_summary_is_refused(luck):
    assert has(problems(luck, FIXTURE["count_summary"]), COUNT)


@pytest.mark.parametrize(
    "text",
    [
        "原局五行里水偏多。",
        "原局五行里木和水偏多，火金缺位。",  # another item in the sentence
        "原局五行里土最多。",
        "原局五行里火偏多。",
        "原局五行里木偏少。",
        "原局五行里土缺位。",
        "原局五行里不能说不是水偏多。",  # an outer negation
        "原局五行里不是不水偏多。",  # a double negation
        "原局五行里并不是水偏多，但其实水偏多。",  # a statement again after a turn
    ],
)
async def test_wrong_count_summaries_are_refused(luck, text):
    assert has(problems(luck, text), COUNT), text


@pytest.mark.parametrize(
    "text",
    [
        "原局五行计数木4、火0、土3、金0、水1，木和土偏多、火金缺位。",
        "原局五行里木最多，水偏少。",
        "原局五行里不是水偏多。",  # a wrong summary denied
        "原局五行计数里并不是木水偏多，而是木土偏多。",
        "原局五行计数木4，但流年火多。",  # a period's elements
        "原局五行计数中，资金偏少不代表什么。",  # 资金 is no element
        "单看这些元素在盘中的分布，木土出现得多，火与金则一个也没有出现。",
    ],
)
async def test_right_count_summaries_pass(luck, text):
    assert not has(problems(luck, text), COUNT), text


# ---- a range from a part of a month before a flow month -------------------------------------


@pytest.fixture
async def love(run_at):
    runtime, *_ = await run_at("bazi_pilot_typed_birth", written)
    return runtime.session


async def test_the_r13_range_before_a_flow_month_is_refused(love):
    found = findings(love, FIXTURE["typed_title"], FIXTURE["typed_body"])
    assert has(found, "“中旬到8月初”" + START), found


@pytest.mark.parametrize(
    "body",
    [
        "7月中旬到8月初，流月乙未带来压力。",
        "中旬到8月初，流月乙未带来压力。",  # the month from the layer's title
        "7月上旬，流月甲午提示责任。中旬至8月初，流月乙未带来压力。",
    ],
)
async def test_ranges_against_the_flow_month_start(love, body):
    assert has(findings(love, "7月：开头几天", body), START), body


@pytest.mark.parametrize(
    "body",
    [
        "7月上旬，流月甲午提示责任。7月7日到8月初，流月乙未带来压力。",
        "7月上旬到中旬，流月甲午提示责任。",  # 甲午 runs when the range begins (7月1日)
        "7月上旬，流月甲午提示责任。上旬之后，流月乙未带来压力。",  # 乙未 from 7月7日
        "不是中旬到8月初，流月乙未带来压力。",  # denied
    ],
)
async def test_ranges_that_hold_the_flow_month_start_pass(love, body):
    assert findings(love, "7月：开头几天", body) == [], body


async def test_a_range_is_repaired_with_its_layer(run_at):
    """The typed birth #1 layer as a draft: one repair, the title quoted."""
    layer = f"【分层】{FIXTURE['typed_title']}\n{FIXTURE['typed_body']}\n【建议】"
    _, outcome, composer = await run_at(
        "bazi_pilot_typed_birth",
        lambda m: written(m).replace("【建议】", layer, 1),
        written,
    )
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any(START in p for p in info["problems"][0])
    assert "中旬到8月初" in composer.seen[1][0][-1]["content"]


# ---- the first cycle given as what shows the current one ------------------------------------


@pytest.fixture
async def career(run_at):
    runtime, *_ = await run_at("bazi_pilot_next_month_career", written)
    return runtime.session


async def test_the_r13_first_cycle_as_this_stage_is_refused(career):
    assert has(problems(career, FIXTURE["career_stage"]), STAGE)


@pytest.mark.parametrize(
    "text,refused",
    [
        ("首步大运己丑（1998年交运，2008年换下一步）说明你现在处在这步大运。", True),
        ("第2步大运戊子（2008年交运）显示你目前在这一步大运。", True),
        ("首步大运己丑显示你正走在当前大运的后半段。", True),
        ("第3步大运丁亥（2018年交运，2028年换下一步）显示你正走在这步大运的后半段。", False),
        ("首步大运己丑（1998年交运，2008年换下一步）显示起运时间。", False),
        ("你正走在这步十年大运的后半段，2028年才换下一步。", False),
        ("你正走在这步十年大运的前半段。", True),  # the position, 9th year of 丁亥
    ],
)
async def test_cycles_given_as_the_current_one(career, text, refused):
    found = problems(career, text)
    assert (has(found, STAGE) or has(found, "当前大运丁亥")) is refused, (text, found)


def test_a_decided_investment_is_no_fixed_investment():
    """r13 dayun #2, #3 advice: “再决定投入多少” holds 定投 inside 决定投入."""
    assert not batch_recommended("建议你决定投入多少精力")
    assert batch_recommended("建议定投")
