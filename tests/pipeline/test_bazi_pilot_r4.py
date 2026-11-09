"""Bazi pilot r3 findings (docs/verification/p3/bazi-pilot-r3/review.md), fixed in r4.

Typed birth #2 (女, 1995-04-28 07:15 深圳, the second half of 2026): the only luck-cycle fact on
a timing sheet is the start of the first cycle, and the writer cited it as the range's own stage:
“首步大运辛巳（1997年交运）这个大运阶段需要你留意自身节奏”. The current cycle is 癸未
(2017–2027); every check passed the sentence, and “目前走的是辛巳大运” passed as well.

The new refusal has its guards: what still passes (the range's own cycle, a cycle set in another
time, a plain denial, a reading that is not about a range) and what is still refused around it
(another time word elsewhere in the clause, an outer negation, a degree word, a double negation,
a statement again after a turn, a comma between the cycle and “this stage”).
"""

import re
from types import SimpleNamespace

import pytest

from pipeline.bazi import Bazi
from tests.pipeline.test_runner_bazi import DAYUN, SHANGHAI, facts_in, make, written  # noqa: F401

TYPED = "我是女生，1995年4月28日早上7点15分出生在深圳，用八字看看我今年下半年的感情运。"
ADVICE = "这个大运阶段需要你留意自身节奏，别把所有精力都投在关系里。"
# The saved sentence of r3 typed birth #2, as the fact text rendered it then.
R3_SENTENCE = (
    "但1997年12月28日起运，首步大运辛巳（1997年交运）这个大运阶段需要你留意自身节奏，"
    "别把所有精力都投在关系里。"
)


def first_stage(messages) -> str:
    """The writer of r3: the sheet's luck-cycle fact, then “this stage”."""
    (alias,) = [a for a, label, _ in facts_in(messages) if label == "大运"]
    return written(messages, extra=f"但{{{{{alias}}}}}{ADVICE}")


@pytest.fixture
async def chart(make):  # noqa: F811
    runtime, _, _ = make(written, birth=None)
    outcome = await runtime.turn(TYPED)
    assert outcome.status == "submit_reading", outcome.text
    state = runtime.session.state
    sequence = [s["ganzhi"] for s in state["bazi_result"]["dayun"]["sequence"]]
    assert sequence[:4] == ["辛巳", "壬午", "癸未", "甲申"]
    assert state["bazi_result"]["dayun"]["start_solar"] == "1997-12-28"
    period = state["bazi_period_result"]
    assert (period["start"], period["end"]) == ("2026-07-01", "2026-12-31")
    return SimpleNamespace(state=state, policy_judge=None)


def refused(chart, text: str) -> list[str]:
    return Bazi(None).problems([text], chart)


def misplaced(problems) -> bool:
    return any("不能当成这段时间的大运阶段" in p for p in problems) or any(
        "按今年算所在的大运是癸未" in p for p in problems
    )


async def test_the_r3_sentence_is_refused(chart):
    assert misplaced(refused(chart, R3_SENTENCE))
    # The same sentence as the fact now renders it.
    rendered = R3_SENTENCE.replace("（1997年交运）", "（1997年交运，2007年换下一步）")
    (problem,) = refused(chart, rendered)
    assert problem == (
        "这次看的是2026-07-01至2026-12-31，所在大运是癸未；辛巳是1997至2007年的大运，"
        "不能当成这段时间的大运阶段"
    )


async def test_a_cycle_written_as_the_present_one(chart):
    for text in (
        "目前走的是辛巳大运。",  # the r3 probe's control
        "当前处于辛巳大运。",
        "如今正行辛巳运。",
        "现在所处的大运是辛巳。",
        "目前走的大运是辛巳。",
        "目前走的不是癸未大运。",
    ):
        assert misplaced(refused(chart, text)), text
    for text in (
        "目前走的是癸未大运。",
        "目前走的不是辛巳大运，而是癸未大运。",
        "当前处于癸未大运。",
        "现在的运势起伏不大。",  # 运势 is no cycle
    ):
        assert refused(chart, text) == [], text


async def test_a_cycle_taken_as_this_stage_is_still_refused(chart):
    for text in (
        f"首步大运辛巳{ADVICE}",
        "首步大运辛巳这个阶段需要你别重复过去的模式。",  # 过去 elsewhere in the clause
        "回看过去，首步大运辛巳这个大运阶段需要你留意。",  # 回看 in another clause
        "首步大运辛巳，这个大运阶段要多照顾自己。",  # a comma before “this stage”
        "辛巳大运这步运提醒你放慢。",
        "第二步大运壬午这一步要你多沟通。",
        "流年丙午主学习，首步大运辛巳这个大运阶段也要留意节奏。",  # another item first
        "不能说现在不是首步大运辛巳这个阶段。",  # an outer negation
        "现在不完全是首步大运辛巳这个阶段。",  # a degree word
        "现在不是不在辛巳这个大运阶段。",  # a double negation
        "现在不是辛巳这个大运阶段，但其实还是辛巳这个大运阶段。",  # again after a turn
    ):
        assert misplaced(refused(chart, text)), text


async def test_what_still_passes(chart):
    for text in (
        "1997年12月28日起运，首步大运辛巳（1997年交运，2007年换下一步）。",
        f"癸未{ADVICE}",  # the range's own cycle
        "大运癸未这个阶段重在积累。",
        "首步大运辛巳这个阶段早已过去。",
        "首步大运辛巳这一步之后，又走了壬午和癸未。",
        "早在首步大运辛巳这个阶段，起运就已经开始。",
        "下一步甲申这个大运阶段从2027年开始。",
        "现在不是首步大运辛巳这个阶段。",  # a plain denial
        "流年丙午这个阶段重在学习。",  # a flow year, not a cycle
    ):
        assert refused(chart, text) == [], text


async def test_a_reading_that_is_not_about_a_range_keeps_its_cycles(make):  # noqa: F811
    runtime, _, _ = make(written, birth=SHANGHAI)
    outcome = await runtime.turn(DAYUN)
    assert outcome.status == "submit_reading", outcome.text
    state = runtime.session.state
    first = state["bazi_result"]["dayun"]["sequence"][0]["ganzhi"]
    session = SimpleNamespace(state=state, policy_judge=None)
    assert Bazi(None).problems([f"首步大运{first}{ADVICE}"], session) == []


async def test_the_sheet_says_which_cycle_holds_the_range(make):  # noqa: F811
    runtime, composer, _ = make(written, birth=None)
    outcome = await runtime.turn(TYPED)
    assert outcome.status == "submit_reading", outcome.text
    sheet = composer.seen[0][0][1]["content"]
    assert "首步大运辛巳（1997年交运，2007年换下一步）" in sheet
    assert "这段时间所在的大运是癸未（2017年交运）；事实表里的首步大运辛巳只说明何时起运" in sheet


async def test_the_r3_writer_is_repaired_with_its_sentence_quoted(make):  # noqa: F811
    runtime, composer, events = make(first_stage, written, birth=None)
    outcome = await runtime.turn(TYPED)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    (problems,) = info["problems"]
    assert any("不能当成这段时间的大运阶段" in p for p in problems)
    # The request quotes the sentence (a check on single sentences: runner.repair_quotes).
    request = composer.seen[1][0][-1]["content"]
    quoted = request.split("出问题的句子：", 1)[1].split("\n", 1)[0]
    assert "首步大运辛巳（1997年交运，2007年换下一步）这个大运阶段需要你留意自身节奏" in quoted
    reading = outcome.data["reading"]
    assert all(ADVICE not in section["body"] for section in reading["sections"])


# ---- typed birth #3: numbers left as text -----------------------------------------------------

# The end of a saved r3 section body (typed birth #3), the line the writer put under its text.
R3_LITERAL = "整体看，这段时间更适合经营而不是冲刺。引用：R7 R8 R4 R5"
LITERAL = re.compile(r"(?<![A-Za-z0-9{])R\d+")


def literal(problems) -> bool:
    return any("R加数字的编号" in p for p in problems)


async def test_a_number_left_as_text_is_refused(chart):
    assert literal(refused(chart, R3_LITERAL))
    assert literal(refused(chart, "依据见R12。"))
    assert literal(refused(chart, "（R3、R4）提示你放慢节奏。"))
    for text in (
        "整体看，这段时间更适合经营而不是冲刺。",
        "听R&B的时候放松一下。",  # no number
        "可以用QR2这类工具记账。",  # part of a word
    ):
        assert not literal(refused(chart, text)), text


def cited_as_text(messages) -> str:
    """The r3 writer: a citation line written under the body instead of 【引用】."""
    draft = written(messages)
    first = draft.split("【引用】", 1)[1].split("\n", 1)[0].strip()
    return draft.replace(f"\n【引用】{first}", f"\n引用：{first}\n【引用】{first}", 1)


async def test_a_citation_written_into_the_body_is_repaired(make):  # noqa: F811
    runtime, composer, _ = make(cited_as_text, written, birth=None)
    outcome = await runtime.turn(TYPED)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert literal(info["problems"][0])
    request = composer.seen[1][0][-1]["content"]
    assert "出问题的句子：" in request and "引用：R" in request
    for section in outcome.data["reading"]["sections"]:
        assert not LITERAL.search(section["body"])
