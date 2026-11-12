"""Bazi pilot r10 findings (docs/verification/p3/bazi-pilot-r10/review.md, PR #70 review), fixed
in r11.

- Luck cycles #1: “按出生到节令的时间来定，逆排从上一个‘节’数到出生” for a chart counted forward
  (dayun.forward = true) passed every check. The fact sheet gave the rule for both directions
  and its keywords listed both 顺排 and 逆排, but not which one this chart uses.

A direction said of this chart must be the computed one. The rule itself (both directions set out
in one sentence) passes; the relaxation carries its guards (still refused): another item in the
sentence, a denial then a statement, an outer negation, a degree word, a double negation, a
statement again after a turn.
"""

import json
from pathlib import Path

import pytest

from tests.pipeline.test_bazi_pilot_r5 import CASES, DAYUN_CASE, computed, has, refused
from tests.pipeline.test_runner_bazi import facts_in, make, written  # noqa: F401

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r10_review.json").read_text(encoding="utf-8")
)
# The luck-cycle question for the trait case's female born in a yang year: counted backward.
BACKWARD_CASE = {**DAYUN_CASE, "profile": CASES["bazi_pilot_trait"]["profile"]}
DIRECTION = "这次排出的大运是"


@pytest.fixture
async def charts(make):  # noqa: F811
    forward, _ = await computed(make, DAYUN_CASE, DAYUN_CASE["question"])
    backward, _ = await computed(make, BACKWARD_CASE, DAYUN_CASE["question"])
    assert forward.state["bazi_result"]["dayun"]["forward"] is True
    assert backward.state["bazi_result"]["dayun"]["forward"] is False
    return forward, backward


async def test_the_r10_direction_is_refused(charts):
    forward, _ = charts
    item = FIXTURE["direction"]
    assert has(refused(forward, item["sentence"]), DIRECTION)


async def test_directions_against_the_chart(charts):
    forward, backward = charts
    for text, wrong_on in (
        ("你的大运是顺排。", backward),
        ("你的大运是逆排。", forward),
        ("这份命盘不是顺排。", forward),  # the computed direction denied
        ("是逆排，不是顺排。", forward),  # a statement, then a denial of the right one
        ("不是顺排，而是逆排。", forward),  # a denial, then the statement
        ("不能说不是逆排。", forward),  # an outer negation
        ("并非不是逆排。", forward),  # a double negation
        ("你的大运不完全是顺排。", forward),  # a degree word
        ("不是逆排，但其实是逆排。", forward),  # the statement again after a turn
        ("你的大运逆排，顺排则相反。", forward),  # another item in the sentence
        ("首步大运丙辰，大运逆排。", forward),
    ):
        assert has(refused(wrong_on, text), DIRECTION), text
    for text, right_on in (
        ("你的大运是顺排。", forward),
        ("你的大运是逆排。", backward),
        ("不是逆排，而是顺排。", forward),
        ("你的大运逆排，顺排则相反。", backward),
        ("这份命盘不是逆排。", forward),  # the wrong direction denied
        ("根本不是逆排。", forward),  # a degree word before the denial
        ("顺排从出生数到下一个节，逆排从上一个节数到出生。", forward),  # the rule
        ("顺排从出生数到下一个节，逆排从上一个节数到出生。", backward),
        ("阳年男命顺排、阴年男命逆排。", backward),
        ("大运按十年一步推进。", forward),
    ):
        assert not has(refused(right_on, text), DIRECTION), text


async def test_the_sheet_says_which_direction(make):  # noqa: F811
    for case, word, other in ((DAYUN_CASE, "顺排", "逆排"), (BACKWARD_CASE, "逆排", "顺排")):
        _, composer = await computed(make, case, DAYUN_CASE["question"])
        sheet = composer.seen[0][0][1]["content"]
        assert f"这份命盘的大运{word}" in sheet
        keywords = [line for line in sheet.splitlines() if "起运" in line and "关键词" in line]
        assert keywords and all(other not in line.split("｜一般含义")[0] for line in keywords)


async def test_a_wrong_direction_is_repaired_with_the_sentence_quoted(make):  # noqa: F811
    sentence = FIXTURE["direction"]["sentence"]
    runtime, composer, _ = make(
        lambda m: written(m, extra=sentence),
        lambda m: written(m, extra="按出生到节令的时间来定，顺排从出生数到下一个‘节’。"),
        birth=DAYUN_CASE["profile"],
    )
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any(DIRECTION in p for p in info["problems"][0])
    assert f"出问题的句子：“{sentence}”" in composer.seen[1][0][-1]["content"]
    assert "顺排从出生数到下一个‘节’" in outcome.text


async def test_the_right_direction_is_submitted_without_repair(make):  # noqa: F811
    text = "按出生到节令的时间来定，顺排从出生数到下一个‘节’。"
    runtime, _, _ = make(lambda m: written(m, extra=text), written, birth=DAYUN_CASE["profile"])
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
