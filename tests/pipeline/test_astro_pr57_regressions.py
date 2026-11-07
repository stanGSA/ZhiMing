"""PR #57 review counterexamples, through rendering and the final submission Guard."""

import re
from types import SimpleNamespace

import pytest

from pipeline.astro import Astro
from pipeline.factsheet import Fact
from pipeline.runner import PipelineRunner
from tests.pipeline.test_runner_astro import (
    NEXT_MONTH,
    SHANGHAI,
    TRAIT,
    facts_in,
    written,
)
from tests.pipeline.test_runner_astro import make as make


@pytest.mark.parametrize(
    "sentence,accepted",
    [
        ("并非{{R1}}就意味着做事一定固执。", True),
        ("并不是本命太阳在金牛座就代表做事一定固执。", True),
        ("并非太阳在第11宫就说明一定成功。", True),
        ("并不是太阳在白羊座。", True),
        ("不是白羊座的太阳和月亮。", True),
        ("并非太阳在第1宫。", True),
        ("不是太阳在白羊座，而是太阳在金牛座。", True),
        ("并非不是太阳在金牛座。", True),
        ("并非太阳不在金牛座。", True),
        ("并非太阳在金牛座。", False),
        ("不是金牛座的太阳和月亮。", False),
        ("并非太阳在第11宫。", False),
        ("并非不是太阳在白羊座。", False),
        ("不是不在第1宫的太阳。", False),
        ("不是太阳在白羊座，而是月亮在白羊座。", False),
        ("太阳不是金牛座，并非金牛座就意味着固执。", False),
    ],
)
async def test_position_negation_reaches_the_expected_submission(make, sentence, accepted):
    def draft(messages):
        return written(messages, extra=sentence)

    runtime, _, _ = make(draft, draft)
    outcome = await runtime.turn(TRAIT)
    assert outcome.status == "submit_reading", outcome.text
    # The actual chart, rather than an assumed sign/house, grounds the counterexamples.
    sun = next(p for p in runtime.session.state["natal_result"]["planets"] if p["body"] == "Sun")
    assert (sun["sign_zh"], sun["house"]) == ("金牛", 11)
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == ((0, None) if accepted else (1, "keywords")), info


@pytest.mark.parametrize(
    "wording", ["placeholder", "no_date", "synonym", "title", "uncited", "refs_only"]
)
async def test_section_dates_bind_written_events_without_requiring_verbatim_text(make, wording):
    def draft(messages):
        alias, _, text = next(fact for fact in facts_in(messages) if fact[1] == "行运相位")
        day = int(re.search(r"11月(\d+)日精确", text)[1])
        title = "下旬：调整节奏" if day <= 10 else "上旬：调整节奏"
        claim = {
            "placeholder": "{{" + alias + "}}",
            "no_date": text.split("（")[0],
            "synonym": text.split("（")[0].replace("与本命", "和本命").replace("三分相", "拱相"),
            "title": text.split("（")[0],
            "uncited": text.split("（")[0],
            "refs_only": "",
        }[wording]
        if wording == "title":
            title += "：" + claim
            claim = ""
        refs = "" if wording == "uncited" else f"【引用】{alias}\n"
        return (
            "【表态】平稳\n【摘要】下个月整体平稳，适合按计划推进。\n"
            f"【分层】{title}\n{claim}提示你调整节奏。\n{refs}"
            "【建议】\n- 先排序：列出最重要的两件事。\n【收尾】按自己的节奏来。"
        )

    runtime, _, _ = make(draft, draft)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    expected = (0, None) if wording == "refs_only" else (1, "keywords")
    assert (info["repairs"], info["degraded"]) == expected, info
    if wording != "refs_only":
        assert all(any("不在这一段里" in p for p in problems) for problems in info["problems"])


@pytest.mark.parametrize(
    "body,refs,accepted",
    [
        ("行运木星拱本命太阳。", ["R2"], True),
        ("行运木星拱本命太阳。", ["R1"], False),
        ("行运木星拱本命太阳在11月25日精确。", [], True),
        ("行运木星拱本命太阳在11月5日精确。", [], False),
        ("行运土星刑本命月亮。", ["R3"], True),
        ("行运木星拱本命太阳在11月5日精确。", ["R3"], False),
        ("本命木星拱太阳。", ["R1"], True),
        ("这一层只谈节奏。", ["R1", "R2", "R3"], True),
    ],
)
def test_section_event_identity_uses_relation_date_and_citations(body, refs, accepted):
    events = [
        {
            "exact_utc": "2026-11-05T00:00:00Z",
            "exact_date": "2026-11-05",
            "transit_body": "Jupiter",
            "natal_body": "Sun",
            "aspect": "trine",
        },
        {
            "exact_utc": "2026-11-25T00:00:00Z",
            "exact_date": "2026-11-25",
            "transit_body": "Jupiter",
            "natal_body": "Sun",
            "aspect": "trine",
        },
        {
            # Same instant, different relation: a timestamp alone is not an event key.
            "exact_utc": "2026-11-25T00:00:00Z",
            "exact_date": "2026-11-25",
            "transit_body": "Saturn",
            "natal_body": "Moon",
            "aspect": "square",
        },
    ]
    facts = [
        Fact(
            f"R{index}",
            f"astro:transit:{e['exact_utc']}:{e['transit_body']}:{e['natal_body']}:{e['aspect']}",
            "行运相位",
            "",
            "",
        )
        for index, e in enumerate(events, 1)
    ]
    session = SimpleNamespace(
        calendar_anchor="2026-10-30",
        state={
            "astro_question_type": "timing",
            "transit_result": {"start": "2026-11-01", "end": "2026-11-30", "events": events},
        },
    )
    args = {"sections": [{"title": "下旬：节奏", "body": body, "ref_ids": refs}]}
    assert bool(Astro(None).reading_problems(args, facts, session)) is not accepted


@pytest.mark.parametrize(
    "message",
    [
        "看星盘，我1990年3月5日生，看看我的性格。",
        "看星盘，我是1990年的，看看我的性格。",
        "看星盘，我1990-03-05生，看看我的性格。",
    ],
)
async def test_short_birth_mentions_leave_the_pipeline(make, message):
    runtime, composer, _ = make(written)
    assert await PipelineRunner(runtime).turn(message) is None
    assert composer.seen == []
    assert not runtime.session.state.get("transit_result")


@pytest.mark.parametrize(
    "answer,continues",
    [
        ("早上8点30分", True),
        ("我1996年5月10日出生，早上8点30分", True),
        ("我是1990年3月5日出生，早上8点30分", False),
        ("1990-03-05 08:30", False),
        ("出生于1990年，早上8点30分", False),
    ],
)
async def test_clock_answer_cannot_override_a_different_birth_date(make, answer, continues):
    birth = {**SHANGHAI, "birth_local_dt": "1996-05-10"}
    runtime, composer, _ = make(written, birth=birth)
    first = await runtime.turn(TRAIT)
    assert first.status == "ask_user"
    outcome = await PipelineRunner(runtime).turn(answer)
    if continues:
        assert outcome.status == "submit_reading", outcome.text
        assert runtime.session.state["natal_result"]["input"]["birth_local"] == "1996-05-10 08:30"
    else:
        assert outcome is None
        assert not runtime.session.state.get("natal_result")
        assert composer.seen == []
        assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None
