"""Bazi pilot r22 findings (docs/verification/p3/bazi-pilot-r22/review-claude.md), fixed in r23.

Known escapes, all passed by every check:

- Luck cycles #2: “第4步大运己未……走到2033年换月柱乙卯所属的更长时间框架之前”, a natal pillar written
  as what the cycle hands over to (2033 hands over to the 5th cycle, 庚申).
- Investment #2: “立春之后，流年丁未（……2月4日起）和流年丙午（……1月1日至2月4日）都带竞争与同伴主题”,
  a flow year placed after 立春 that ends at it.
- Investment #3, advice: “用今年上半年系统学习风险规则”, asked on 2026-11-17 about 明年.

The owner decided on 2026-11-17 to read a handover's target against the sequence, to hold the flows a
point in time opens (立春之后, 2月4日起, 5月起) to that point, and to refuse a past time outside the
range unless the clause looks back.

Two drafts were refused wrongly and passed after one repair: “创意和专长可以开源但不等于适合重仓”
(investment #1) and “遇到“稳赚”说法多问几个为什么” (investment #2).

Guards next to each change: what still passes (the right value, a denial, a look back, the r22
answers that passed) and what is still refused (another item, a denial turned back, an outer
negation, a degree word, a double negation, a turn that states it again).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from common.output_policy import hard_claim
from pipeline.bazi import Bazi
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES
from tests.pipeline.test_bazi_pilot_r10 import TYPED_PROFILE
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r22_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 17, 12, 5, 12, tzinfo=UTC)  # the r22 pipeline run
HANDOFF = "写成了换运后的大运"
AFTER = "整段都在这之前"
PAST = "已经过去（今天是11月17日）"
TRADE = "八字不能推出仓位"


@pytest.fixture
def run_at(project):
    runtimes = []

    async def build(case_id):
        case = CASES[case_id]
        runtime = create_runtime(
            root=project,
            user_id=f"r23-{case_id}",
            seed=7,
            model=Composer(written),
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or TYPED_PROFILE
        runtime.store.update_profile_fields(f"r23-{case_id}", profile, "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r23-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        if outcome.status == "ask_user":
            outcome = await runtime.turn(case["clarification"])
        assert outcome.status == "submit_reading", outcome.text
        return runtime.session

    yield build
    for runtime in runtimes:
        runtime.close()


@pytest.fixture
async def money(run_at):
    return await run_at("bazi_pilot_investment_risk")


@pytest.fixture
async def luck(run_at):
    return await run_at("bazi_pilot_dayun")


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


def reading(session, answer: dict) -> list[str]:
    return [p for p, _ in Bazi(None).section_findings(answer, [], session)]


def layer(session, title: str, body: str, **fields) -> list[str]:
    answer = {"summary": "整体平稳。", "sections": [{"title": title, "body": body}], **fields}
    return reading(session, answer)


def has(found: list[str], words: str) -> bool:
    return any(words in p for p in found)


# ---- the two drafts refused wrongly ------------------------------------------------------------


async def test_a_denied_suitability_is_not_a_trade(money):
    assert not has(problems(money, FIXTURE["trade_kept"]), TRADE)


@pytest.mark.parametrize(
    "sentence",
    ["8月起，这不代表适合加仓。", "8月起，机会多并不意味着该加仓。"],
)
async def test_other_denied_suitabilities_pass(money, sentence):
    assert not has(problems(money, sentence), TRADE)


@pytest.mark.parametrize(
    "sentence",
    [
        "8月起，不等于不适合重仓。",  # the restraint turned back
        "8月起，不能说不等于适合重仓。",  # outer negation
        "8月起，并非不等于适合重仓。",  # double negation
        "8月起，不一定不等于适合加仓。",  # weakened
        "8月起，不等于适合重仓，但可以加仓。",  # another item after the turn
        "8月起，不等于适合重仓而是更适合加仓。",  # stated again
        "8月起，不等于适合很多人的重仓。",  # the suitability is not right before the trade
    ],
)
async def test_suitability_denials_that_recommend_still_fail(money, sentence):
    assert has(problems(money, sentence), TRADE)


def test_a_quoted_gain_met_and_doubted_is_a_mention():
    assert hard_claim([FIXTURE["gain_doubted"]]) is None
    assert hard_claim(["听到“稳赚”的话术先核实。"]) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "遇到“稳赚”说法就跟进。",
        "遇到“稳赚”说法不用多问。",
        "不用遇到“稳赚”说法都多问。",
        "遇到“稳赚”说法多问几个为什么是多此一举。",
        "遇到稳赚的机会多问几个为什么。",  # not quoted
        "遇到“稳赚”说法多问几个为什么，这次确实稳赚。",
    ],
)
def test_a_met_gain_that_is_not_doubted_still_fails(sentence):
    assert hard_claim([sentence]) == "稳赚"


# ---- what a luck cycle hands over to -----------------------------------------------------------


async def test_the_r22_natal_pillar_as_the_next_cycle_is_refused(luck):
    found = problems(luck, FIXTURE["luck"][1]["sections"][2]["body"])
    assert has(found, "把出生四柱的月柱乙卯写成了换运后的大运")
    assert has(found, "那一步是第5步大运庚申")


@pytest.mark.parametrize(
    ("sentence", "words"),
    [
        ("这步大运到2033年换成年柱戊辰。", "年柱戊辰写成了换运后的大运"),
        ("下一步换运进入月柱乙卯。", "月柱乙卯写成了换运后的大运"),
        ("2033年交运到辛酉。", "换运后的是第5步大运庚申，不是辛酉"),
        ("之后换到第5步大运辛酉。", "换运后的是第5步大运庚申，不是辛酉"),
        ("2033年并非不换成月柱乙卯。", HANDOFF),  # double negation
        ("换到第99步月柱乙卯。", "第99步大运没有排到"),
        ("换到第0步月柱乙卯。", "第0步大运没有排到"),
        ("换到第99步大运庚申。", "第99步大运没有排到"),
    ],
)
async def test_a_handover_to_something_else_is_refused(luck, sentence, words):
    assert has(problems(luck, sentence), words)


@pytest.mark.parametrize(
    "sentence",
    [
        "2033年换第5步大运庚申。",
        "2033年交运到庚申。",
        "2033年换的是第5步大运庚申，不是换月柱乙卯。",
        "月柱乙卯（天干乙为比肩）提示独立与同伴并重。",
        "2027年进入丁未年，流年丁未与本命月柱乙卯有关。",
    ],
)
async def test_a_handover_to_the_next_cycle_passes(luck, sentence):
    assert not has(problems(luck, sentence), HANDOFF)
    assert not has(problems(luck, sentence), "换运后的是")


@pytest.mark.parametrize("repeat", [0, 2])
async def test_the_other_r22_luck_answers_pass(luck, repeat):
    for section in FIXTURE["luck"][repeat]["sections"]:
        found = problems(luck, section["body"])
        assert not has(found, HANDOFF) and not has(found, "换运后的是")


# ---- flows after a point in time ---------------------------------------------------------------


async def test_the_r22_flow_year_after_lichun_is_refused(money):
    section = FIXTURE["investment"][1]["sections"][1]
    found = layer(money, section["title"], section["body"])
    assert has(found, "“立春之后”说的是2月4日以后，流年丙午在1月1日至2月4日，" + AFTER)


@pytest.mark.parametrize(
    "body",
    [
        "立春之后，流年丙午与本命月柱庚子地支冲（1月1日至2月4日）还在拉扯。",
        "2月4日起，流月辛丑（十神偏财）偏向机会与调配。",
        "7月起，流月乙巳（十神偏印）提醒补齐预算。",  # 乙巳 ends 6月6日
        "立春之后，流年丁未和流年丙午都很明显。",  # another item first
        "立春之后，流年丙午并非不在。",  # double negation
        "立春之后，流年丙午并未结束，仍带竞争与同伴主题。",
        "立春之后，流年丙午没有结束。",
        "立春之后，流年丙午尚未完全结束。",
        "立春之后，流年丙午未必已经结束。",
        "立春之后，流年丙午并非不再存在。",
        "立春之后，流年丙午不能说已经结束。",
        "立春之后，流年丙午已经结束，但流年丙午仍主导全年。",
        "立春之后，流年丁未开始，流年丙午仍未退场。",
        "2027年2月4日起，流年丙午仍带竞争与同伴主题。",
        "从2027年2月4日起，流年丙午仍带竞争与同伴主题。",
        "2027年立春之后，流年丙午仍带竞争与同伴主题。",
    ],
)
async def test_flows_before_the_point_are_refused(money, body):
    assert has(layer(money, "2月到5月：先学习", body), AFTER)


@pytest.mark.parametrize(
    "body",
    [
        "立春之后进入流年丁未，主题转向独立与同伴。",
        "立春之后，流年丁未接替流年丙午，主题转向同伴。",
        "立春之后不再是流年丙午，转为流年丁未。",
        "立春之后，流年丙午已经结束，转为流年丁未。",
        "立春之后，流年丙午并非没有结束。",
        "2027年2月4日起，流年丁未提示独立与同伴。",
        "2027年立春之后，流年丁未接替流年丙午。",
        "1月5日起，流月辛丑偏向机会与调配。",
        "6月起流月丙午提示冲动花费。",  # 丙午 from 6月6日
        "立春之后流年丁未开始；1月流年丙午还在。",  # a later time word ends the scope
        "立春之后，流年丁未（2月4日起），此前流年丙午（1月1日至2月4日）偏竞争。",
    ],
)
async def test_flows_inside_the_point_or_said_to_be_over_pass(money, body):
    assert not has(layer(money, "2月到5月：先学习", body), AFTER)


# ---- a past time outside the range -------------------------------------------------------------


async def test_the_r22_past_half_year_in_the_advice_is_refused(money):
    found = reading(money, FIXTURE["investment"][2])
    assert has(found, "“今年上半年”" + PAST)


@pytest.mark.parametrize(
    "field",
    [
        {"summary": "今年上半年适合先学习风险规则。"},
        {"advice": ["盘点：今年3月先把账目列清楚。"]},
        {"closing": "今年春天先把应急金留足。"},
        {"advice": ["用今年上半年系统学习已知风险和资产配置常识。"]},
        {"advice": ["用今年上半年系统学习如何避免发生投资损失。"]},
        {"advice": ["今年3月先积累投资经历。"]},
    ],
)
async def test_a_past_time_anywhere_is_refused(money, field):
    answer = {"summary": "整体平稳。", "sections": [{"title": "全年", "body": "先核实。"}]}
    assert has(reading(money, answer | field), PAST)


@pytest.mark.parametrize(
    "advice",
    [
        "复盘：回看今年上半年的收支，再定明年的预算。",
        "盘点：今年3月以来的支出已经偏高，先记下来。",
        "学习：明年上半年系统学习风险规则。",
        "预算：今年12月把明年的预算写下来。",  # still ahead
        "今年上半年曾经出现额外支出。",
        "今年3月发生过额外支出。",
        "今年3月已完成预算调整。",
        "今年3月曾出现额外支出。",
    ],
)
async def test_a_look_back_or_a_time_ahead_passes(money, advice):
    answer = {"summary": "整体平稳。", "sections": [{"title": "全年", "body": "先核实。"}]}
    assert not has(reading(money, answer | {"advice": [advice]}), PAST)


async def test_an_invalid_handover_step_enters_the_repair_loop(project):
    case = CASES["bazi_pilot_dayun"]
    composer = Composer(lambda messages: written(messages, extra="换到第99步月柱乙卯。"), written)
    runtime = create_runtime(
        root=project,
        user_id="r23-invalid-handoff",
        seed=7,
        model=composer,
        mode="pipeline",
        clock=lambda: CLOCK,
    )
    try:
        runtime.store.update_profile_fields("r23-invalid-handoff", case["profile"], "合成测试资料")
        runtime.session.profile = runtime.store.get_profile("r23-invalid-handoff")
        outcome = await runtime.turn(case["question"])
        assert outcome.status == "submit_reading", outcome.text
        assert outcome.data["pipeline"]["repairs"] == 1
        assert len(composer.seen) == 2
        assert "第99步大运没有排到" in str(composer.seen[1])
    finally:
        runtime.close()


# ---- the r22 answers ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_id", "key"),
    [
        ("bazi_pilot_investment_risk", "investment"),
        ("bazi_pilot_typed_birth", "typed"),
        ("bazi_pilot_next_month_career", "career"),
        ("bazi_pilot_overseas_solar", "overseas"),
    ],
)
async def test_the_r22_timing_answers_raise_only_the_known_escapes(run_at, case_id, key):
    session = await run_at(case_id)
    raised = {
        (key, repeat): [p for p in reading(session, answer) if AFTER in p or PAST in p]
        for repeat, answer in enumerate(FIXTURE[key])
    }
    expected = {
        ("investment", 1): ["“立春之后”"],
        ("investment", 2): ["“今年上半年”"],
    }
    for index, found in raised.items():
        assert [p.split("说的是")[0].split("已经")[0] for p in found] == expected.get(index, [])
