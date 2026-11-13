"""Bazi pilot r14 findings (docs/verification/p3/bazi-pilot-r14/review-claude.md), fixed in r15.

Owner, 2026-11-13, two known escapes in dated investment layers:

- Investment #1, layer “2月4日至6月6日”: “……适合拿来补基础、做小范围验证，而不是一次性押上全部”,
  a trial investment recommended for the period.
- Investment #3, layer “7月7日至12月31日”: “应对上，以固定预算和分批规划为主”, a pace of investing
  as the period's principle, without a recommending word.

And a submission error: career #1's first draft titled a layer “{{R11}}期间：……”, 23 characters
as written and 63 once the flow month expanded with its dates; the reading's schema refused it,
and the repair request quoted nothing.

Guards next to each new refusal: what is still refused (an outer negation, a double negation, a
statement again after a turn) and what still passes (a denial, a restraint, a check of an idea).
"""

import json
from pathlib import Path

import pytest

from pipeline.bazi import TRADE_PROBLEM, Bazi
from tests.pipeline.test_bazi_pilot_r5 import has
from tests.pipeline.test_bazi_pilot_r14 import run_at  # noqa: F401
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r14_review.json").read_text(encoding="utf-8")
)
TITLE = "标题的编号展开成事实后有"


def findings(session, title: str, body: str) -> list[str]:
    args = {"summary": "整体平稳。", "sections": [{"title": title, "body": body, "ref_ids": []}]}
    return [p for p, _ in Bazi(None).section_findings(args, [], session)]


def refused(session, title: str, body: str) -> bool:
    return TRADE_PROBLEM in findings(session, title, body) or TRADE_PROBLEM in Bazi(None).problems(
        [body], session
    )


@pytest.fixture
async def money(run_at):  # noqa: F811
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


async def test_the_r14_trial_is_refused(money):
    assert refused(money, FIXTURE["trial_title"], FIXTURE["trial"])


async def test_the_r14_batch_principle_is_refused(money):
    assert refused(money, FIXTURE["batch_title"], FIXTURE["batch"])


@pytest.mark.parametrize(
    "body",
    [
        "这段时间适合试水。",
        "适合拿来补基础、做小范围尝试。",
        "应对上，以预算和分批投入为主。",
        "应对上，以分批为宜。",
        "不能说不适合小范围尝试。",  # an outer negation
        "不是不建议试水。",  # a double negation
        "不建议一次投入，但其实适合小范围验证。",  # a statement after a turn
    ],
)
async def test_trials_and_principles_in_a_dated_layer(money, body):
    assert refused(money, FIXTURE["batch_title"], body), body


@pytest.mark.parametrize(
    "body",
    [
        "这段时间不适合试水。",
        "应对上，不以分批规划为主。",
        "应对上，以固定预算为主。",
        "流月乙巳提醒先用小范围验证检验新想法，不要一次下结论。",  # r14 #2, no recommending word
        "如果你正处在这样的节奏里，更稳妥的做法是把大额投入的事往后放，先用小步验证自己的判断。",
        "全年看，把“全投”换成“分批、留底、按预算”更稳妥。",  # r8 investment #1 (owner: passes)
    ],
)
async def test_restraint_and_checks_in_a_dated_layer_pass(money, body):
    assert not refused(money, FIXTURE["batch_title"], body), body


# ---- a title's length after its numbers expand -----------------------------------------------


def test_titles_are_measured_as_expanded():
    long = "流月己亥（十神食神；2026年12月1日00:00至2026年12月7日10:52，北京时间）期间：先输出、先协调，别忽略小缝"
    args = {
        "sections": [
            {"title": long, "body": "正文。"},
            {"title": "12月7日起：收口", "body": "正文。"},
        ]
    }
    assert has(Bazi.length_problems(args), "第1层" + TITLE)
    assert not has(Bazi.length_problems(args), "第2层" + TITLE)


async def test_the_r14_career_draft_is_repaired_with_its_title(run_at):  # noqa: F811
    _, outcome, composer = await run_at(
        "bazi_pilot_next_month_career", FIXTURE["career_draft"], written
    )
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any(TITLE in p for p in info["problems"][0])
    repair = composer.seen[1][0][-1]["content"]
    assert "期间：先输出、先协调，别忽略小缝" in repair
