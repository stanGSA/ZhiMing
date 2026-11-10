"""Bazi pilot r8 findings (docs/verification/p3/bazi-pilot-r8/review.md), fixed in r9.

- Overseas #3: “好在下旬之后转向流月庚子（…2026年12月6日18:52…）”; typed birth #1: “7月中旬之后，流月
  乙未（…2026年7月7日09:56…）”. Only section titles were held to the flow months, so a body
  clause naming the part of a month a flow month begins in passed every check (r6 overseas #2
  “进入12月中旬以后，流月庚子” is the same). It is held to the owner's title rule of 2026-11-10:
  a start more than two days outside that part is refused.
- Investment #2: “春节之后，流年丁未（…2027年2月4日09:46…）”. A flow year begins at 立春, not 春节.
- Replaying every archived answer on c6b1b26: the direct answer “明年把积蓄全押股市这件事，从盘面
  提示看暂不适合” (r1 #1, r2 #2) is refused by the trade check. A trade that is the subject of a
  verdict denying it is suitable holds back (owner, 2026-11-10: refuse only explicit
  recommendations).

The relaxations carry their guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from pipeline.bazi import Bazi
from pipeline.compose import BAZI_SYSTEM
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT
from tests.pipeline.test_bazi_pilot_r5 import CASES, INVESTMENT_CASE
from tests.pipeline.test_runner_bazi import facts_in, make, written  # noqa: F401

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r8_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 10, 4, 0, tzinfo=UTC)  # the r8 run's day: 下个月 is December
FESTIVAL = "流年按立春换年，不是春节"
TRADE = "八字不能推出仓位、买卖时点或投入节奏"


@pytest.fixture
def make_at(project):
    """A runtime for a case on the r8 run's day, through its clarification if it asks one."""
    runtimes = []

    async def build(case_id, *replies):
        case = CASES[case_id]
        composer = Composer(*(replies or (written, written, written)))
        runtime = create_runtime(
            root=project,
            user_id=f"r9-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        if case.get("profile"):
            runtime.store.update_profile_fields(f"r9-{case_id}", case["profile"], "合成测试资料")
            runtime.session.profile = runtime.store.get_profile(f"r9-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        if outcome.status == "ask_user":
            outcome = await runtime.turn(case["clarification"])
        return runtime, composer, outcome

    yield build
    for runtime in runtimes:
        runtime.close()


def body_findings(session, body: str) -> list[str]:
    args = {"summary": "整体平稳。", "sections": [{"title": "这段时间", "body": body}]}
    return [problem for problem, _ in Bazi(None).section_findings(args, [], session)]


def sentences(kind: str) -> list[dict]:
    return FIXTURE[kind]


# ---- a flow month's start said in the body ---------------------------------------------------


@pytest.mark.parametrize(
    "item", sentences("start_in_part"), ids=lambda i: f"{i['round']}-{i['id']}#{i['repeat']}"
)
async def test_the_r8_body_starts_are_refused(make_at, item):
    runtime, _, outcome = await make_at(item["id"])
    assert outcome.status == "submit_reading", outcome.text
    found = body_findings(runtime.session, item["sentence"])
    assert len(found) == 1, found
    assert "实际从" in found[0] and "按流月的实际起始日写" in found[0]


@pytest.mark.parametrize(
    "item",
    sentences("start_in_part_passing"),
    ids=lambda i: f"{i['round']}-{i['id']}#{i['repeat']}",
)
async def test_starts_inside_the_part_named_pass(make_at, item):
    runtime, _, _ = await make_at(item["id"])
    assert body_findings(runtime.session, item["sentence"]) == []


async def test_body_starts_and_their_guards(make_at):
    # Overseas: 流月己亥 12月1日–6日, 流月庚子 from 12月6日 (America/Los_Angeles).
    runtime, _, _ = await make_at("bazi_pilot_overseas_solar")
    session = runtime.session
    for body in (
        "好在下旬转向流月庚子，事情会顺不少。",  # a turn without 之后
        "12月下旬起，流月庚子带来秩序。",
        "月底之后进入流月庚子。",
        "12月6日起是流月庚子，下旬之后转向流月庚子。",  # another item in the sentence
        "不是上旬，而是下旬之后转向流月庚子。",  # a denial, then the statement
        "不能说不是下旬之后转向流月庚子。",  # an outer negation of a denial
        "并非不是下旬之后转向流月庚子。",  # a double negation
        "不完全是下旬之后转向流月庚子。",  # a degree word: still the claim, hedged
        "不是下旬之后，但其实下旬之后转向流月庚子。",  # the statement again after a turn
    ):
        assert body_findings(session, body), body
    for body in (
        "12月6日起转向流月庚子，主题回到秩序与交付。",
        "上旬之后转向流月庚子。",  # 12月6日 lies in 上旬, read leniently as a title
        "上旬末转向流月庚子。",  # no part of a month the rule reads
        "不是下旬之后才转向流月庚子。",  # the wrong start denied
        "根本不是下旬之后转向流月庚子。",  # a degree word before the denial
        "下旬把精力放在交付上，流月庚子的主题是秩序。",  # 下旬 does not open 庚子
        "12月上旬，流月己亥带来表达的冲动。",  # no word for a start or a turn
        "流月庚子与本命年柱丁丑地支六合（12月6日至12月31日）提示下旬之后多协调。",
    ):
        assert body_findings(session, body) == [], body


async def test_a_body_start_is_repaired_with_the_sentence_quoted(make_at):
    """Next month for 杭州 on the r8 run's day: 流月庚子 from 12月7日 (北京时间)."""

    def started(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流月" and "庚子" in text
        ]
        return written(messages, extra=f"好在下旬之后转向{{{{{alias}}}}}，事情会顺不少。")

    runtime, composer, outcome = await make_at("bazi_pilot_next_month_career", started, written)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert len(info["problems"][0]) == 1, info["problems"]
    assert "流月庚子实际从12月7日开始" in info["problems"][0][0]
    request = composer.seen[1][0][-1]["content"]
    assert "出问题的句子：“好在下旬之后转向流月庚子（" in request


async def test_a_start_in_the_part_named_is_not_repaired(make_at):
    def started(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流月" and "庚子" in text
        ]
        return written(messages, extra=f"12月7日起转向{{{{{alias}}}}}，事情会顺不少。")

    _, _, outcome = await make_at("bazi_pilot_next_month_career", started, written)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


# ---- 春节 named as the change of a flow year -------------------------------------------------


@pytest.fixture
async def money(make_at):
    runtime, _, outcome = await make_at("bazi_pilot_investment_risk")
    assert outcome.status == "submit_reading", outcome.text
    return runtime.session


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


def has(found: list[str], words: str) -> bool:
    return any(words in p for p in found)


async def test_the_r8_festival_sentence_is_refused(money):
    (item,) = sentences("festival")
    assert has(problems(money, item["sentence"]), FESTIVAL)


async def test_festival_boundaries_and_their_guards(money):
    for text in (
        "春节后，流年丁未让独立与协作的主题浮现。",
        "过了春节就进入流年丁未。",
        "春节前仍是流年丙午。",
        "流年丁未从春节开始。",
        "流年丁未要到春节之后才开始。",
        "立春之后进入流年丁未，春节之后流年丁未的竞争主题更明显。",  # another item
        "不是立春，而是春节之后进入流年丁未。",  # a denial, then the statement
        "不能说不是春节之后进入流年丁未。",  # an outer negation of a denial
        "流年丁未并非不是从春节开始。",  # a double negation
        "流年丁未不完全是从春节开始。",  # a degree word
        "不是春节之后，但其实春节之后才进入流年丁未。",  # the statement again after a turn
    ):
        assert has(problems(money, text), FESTIVAL), text
    for text in (
        "立春之后，流年丁未让独立与协作的主题浮现。",
        "2月4日起进入流年丁未，春节（2月6日）前后家里事多。",  # 春节 bounds no flow year
        "春节前后多陪家人，把预算说清楚。",
        "流年丁未不是从春节开始，而是从立春开始。",
        "不是春节之后，而是立春之后进入流年丁未。",
        "根本不是春节之后才进入流年丁未。",
        "不过年后流年丁未的主题更明显。",  # 不过 is not 过年
    ):
        assert not has(problems(money, text), FESTIVAL), text


async def test_a_festival_change_is_repaired(make_at):
    def festival(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流年" and "丁未" in text
        ]
        return written(messages, extra=f"春节之后，{{{{{alias}}}}}让独立与协作的主题浮现。")

    _, composer, outcome = await make_at("bazi_pilot_investment_risk", festival, written)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, None)
    assert any(FESTIVAL in p for p in info["problems"][0])
    assert "出问题的句子：“春节之后，流年丁未（" in composer.seen[1][0][-1]["content"]


def test_the_prompt_asks_for_starts_and_the_flow_year_change():
    assert "正文说某个流月从何时开始时同样按实际起始日写" in BAZI_SYSTEM
    assert "流年按立春换年，不要写成春节前后" in BAZI_SYSTEM


# ---- a trade denied as unsuitable ------------------------------------------------------------

HELD_BACK = (
    "明年把积蓄全部投入股市暂不适合。",
    "明年全投股市不适合。",
    "明年全投股市并不明智。",
    "明年全投股市完全不适合。",  # a degree word before the denial strengthens it
    "明年全投股市根本不适合。",
    "明年把全部积蓄押进股市不太合适。",
    "明年全投股市不适合你。",
    "8月加仓不划算。",
)
STILL_REFUSED = (
    "明年全投股市不适合，流月辛丑适合小额度试探。",  # another item in the sentence
    "明年全投股市不适合，但8月适合加仓。",  # a denial, then a statement after a turn
    "明年全投股市暂不适合，不过8月全投很划算。",
    "不能说明年全投股市不适合。",  # an outer negation
    "很难说明年把积蓄全部投入股市不适合。",
    "不能说明年把积蓄全押股市不适合。",
    "明年全投股市并不完全适合。",  # a degree word: only partly unsuitable
    "明年全投股市不完全不适合。",
    "明年全投股市并非不适合。",  # a double negation
    "明年全投股市不是不适合。",
    "明年全投股市谈不上不适合。",
    "明年全投股市不适合犹豫。",  # the verdict governs a hesitation, not the trade
    "8月适合加仓，不适合全投。",  # the verdict governs what follows it
    "明年8月全投股市，其他月份都不适合。",  # another period takes the verdict over
    "8月是加仓的好时机，错过就不划算。",  # the verdict has its own subject
    "8月加仓，晚了就不划算。",
)


@pytest.mark.parametrize(
    "item", sentences("verdict_held_back"), ids=lambda i: f"{i['round']}-#{i['repeat']}"
)
def test_the_r1_r2_direct_answers_pass(item):
    assert Bazi.trade_problems(item["sentence"]) == [], item["sentence"]


@pytest.mark.parametrize("text", HELD_BACK)
def test_a_trade_denied_as_unsuitable_passes(text):
    assert Bazi.trade_problems(text) == [], text


@pytest.mark.parametrize("text", STILL_REFUSED)
def test_what_only_looks_denied_is_still_refused(text):
    assert Bazi.trade_problems(text), text


async def test_a_denied_trade_is_submitted_without_repair(make):  # noqa: F811
    text = "明年把积蓄全部投入股市暂不适合。"
    runtime, _, _ = make(
        lambda m: written(m, extra=text), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert text in outcome.text
    assert not has(info["problems"][0] if info["problems"] else [], TRADE)
