"""Bazi pilot r9 findings (docs/verification/p3/bazi-pilot-r9/review.md), fixed in r10.

- Investment #1, #2, typed birth #2: second drafts titled “5月6日到7月7日”“7月7日起到10月初”
  “8月7日起到10月8日” were refused and degraded. A day after a month was not read, so a dated
  range became its two end months (5月 and 7月) and the months between were left out.
- Luck cycles #1: “……都带正财、偏财的标签” was read as “都带正财” and repaired.
- Investment #2: “对任何“稳赚”说法都要求看到成本和最坏情况” was read by the shared hard_claim
  as a promise, so the degraded reading was the safety reply. Owner, 2026-11-11: a quoted 稳赚
  named as a claim the sentence doubts is a mention.
- That safety reply listed calculation keys (“period:2026-12-31T16:00:00+00:00:年柱:丙午:劫财”)
  to the reader. Owner, 2026-11-11: list the fact sheet's text.

The relaxations carry their guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import create_runtime
from common.output_policy import hard_claim
from pipeline.bazi import Bazi
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r3 import INVESTMENT, broken
from tests.pipeline.test_bazi_pilot_r5 import CASES, DAYUN_CASE, INVESTMENT_CASE
from tests.pipeline.test_runner_bazi import facts_in, make, written  # noqa: F401

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r9_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)  # the r9 run's day
# Typed birth (1995-04-28 07:15, 深圳, female) as a stored profile, so the question is asked once.
TYPED_PROFILE = {
    "birth_local_dt": "1995-04-28 07:15",
    "tz": "Asia/Shanghai",
    "lat": 22.54,
    "lon": 114.06,
    "birth_place": "深圳",
    "time_known": True,
    "gender": "female",
}


@pytest.fixture
def session_at(project):
    runtimes = []

    async def build(case_id):
        case = CASES[case_id]
        runtime = create_runtime(
            root=project,
            user_id=f"r10-{case_id}",
            seed=7,
            model=Composer(written, written, written),
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        profile = case.get("profile") or (
            TYPED_PROFILE if case_id == "bazi_pilot_typed_birth" else None
        )
        if profile:
            runtime.store.update_profile_fields(f"r10-{case_id}", profile, "合成测试资料")
            runtime.session.profile = runtime.store.get_profile(f"r10-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        if outcome.status == "ask_user":
            outcome = await runtime.turn(case["clarification"])
        assert outcome.status == "submit_reading", outcome.text
        return runtime.session

    yield build
    for runtime in runtimes:
        runtime.close()


def findings(session, sections) -> list[str]:
    args = {"summary": "整体平稳。", "sections": [{**s, "ref_ids": []} for s in sections]}
    return [problem for problem, _ in Bazi(None).section_findings(args, [], session)]


def drafts(number: int) -> list[dict]:
    return [d for d in FIXTURE["drafts"] if d["draft"] == number]


# ---- dated ranges in section titles ----------------------------------------------------------


@pytest.mark.parametrize("draft", drafts(2), ids=lambda d: f"{d['id'][11:]}#{d['repeat']}-draft2")
async def test_the_r9_second_drafts_are_read_as_dated_ranges(session_at, draft):
    """Every dated title of the three second drafts was refused in r9. Read as ranges, only
    investment #1's “2月4日起到4月初” is still refused, and for a flow month it really cites
    outside its time: “流月甲辰与本命月柱庚子天干冲（4月5日至5月6日）”."""
    session = await session_at(draft["id"])
    found = findings(session, draft["sections"])
    if (draft["id"], draft["repeat"]) == ("bazi_pilot_investment_risk", 1):
        assert len(found) == 1, found
        assert "说的是2月4日至4月10日" in found[0] and "流月甲辰在4月5日至5月6日" in found[0]
    else:
        assert found == []


@pytest.mark.parametrize("draft", drafts(1), ids=lambda d: f"{d['id'][11:]}#{d['repeat']}-draft1")
async def test_the_r9_first_drafts_are_still_refused(session_at, draft):
    """Their titles were wrong: 下半年 over 丙午 from 6月6日, 7月中 over 乙未 from 7月7日."""
    session = await session_at(draft["id"])
    found = findings(session, draft["sections"])
    titles = [p for p in draft["problems"] if "这一层的标题" in p]
    assert titles and all(any(p[:20] in f for f in found) for p in titles), found


async def test_dated_titles_against_flow_months(session_at):
    session = await session_at("bazi_pilot_investment_risk")
    refused = (
        ("5月6日到7月7日：起伏", "流月丁未"),  # 7月7日–8月8日 lies after the title
        ("2月4日起到4月初：压力", "流月甲辰"),  # ends 5月6日, a month past 4月初
        ("6月6日到9月8日：收入", "流月己酉"),  # starts the day the title ends
        ("10月8日到年底：收束", "流月己酉"),  # 9月8日–10月8日 lies before it
        ("12月1日至6日：变动", "流月壬子"),  # starts 12月7日
        ("12月7日：收尾", "流月辛亥"),  # a day alone keeps its month: 辛亥 lies in November
    )
    for title, flow in refused:
        assert findings(session, [{"title": title, "body": f"{flow}提示节奏变化。"}]), title
    passed = (
        ("5月6日到7月7日：起伏", "流月乙巳、流月丙午"),
        ("2月4日起到4月初：压力", "流月壬寅、流月癸卯"),
        ("7月7日起到10月初：产出", "流月丁未、流月戊申、流月己酉"),
        ("6月6日到9月8日：收入", "流月丙午、流月丁未、流月戊申"),
        ("10月8日到年底：收束", "流月庚戌、流月辛亥、流月壬子"),
        ("12月7日起：规矩", "流月壬子"),
        ("12月7日：收尾", "流月壬子"),
    )
    for title, flows in passed:
        assert findings(session, [{"title": title, "body": f"{flows}提示节奏变化。"}]) == [], title


async def test_a_dated_title_is_submitted_without_repair(make):  # noqa: F811
    def titled(messages):
        (alias,) = [
            a for a, label, text in facts_in(messages) if label == "流月" and "丙午" in text
        ]
        return (
            "【表态】暂不适合\n【摘要】明年不适合把积蓄都投进股市。先核实自己的财务状况。\n"
            f"【分层】5月6日到7月7日：起伏最明显\n{{{{{alias}}}}}提示竞争与冲动花费，先守住预算。\n"
            f"【引用】{alias}\n"
            "【建议】\n- 先算底线：把应急资金单独留出。\n【收尾】稳住节奏。"
        )

    runtime, _, _ = make(titled, written, birth=INVESTMENT_CASE["profile"])
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert "5月6日到7月7日" in outcome.text


# ---- a list of ten gods after 都带 -------------------------------------------------------------

LISTED = "年柱戊辰（天干戊为正财）和时柱己卯（天干己为偏财）"


def test_the_r9_listed_gods_pass():
    assert Bazi.aggregate_problems(FIXTURE["aggregate"]) == []
    for text in ("都带正财和偏财的味道。", "都带有正财与偏财。"):
        assert Bazi.aggregate_problems(LISTED + text) == [], text


def test_listed_gods_that_disagree_are_still_refused():
    for text in (
        "都带正财、七杀的标签。",  # another item in the list
        "都带正财、偏财、七杀的标签。",
        "都带偏财、偏财的标签。",
        "都带正财的标签。",
        "都带正财、偏财，但其实都是偏财。",  # a statement again after a turn
        "都带正财、偏财，第4步大运己未天干己为偏财，三处都是偏财。",  # another item
    ):
        assert Bazi.aggregate_problems(LISTED + text), text


async def test_listed_gods_are_submitted_without_repair(make):  # noqa: F811
    text = FIXTURE["aggregate"]
    runtime, _, _ = make(lambda m: written(m, extra=text), written, birth=DAYUN_CASE["profile"])
    outcome = await runtime.turn(DAYUN_CASE["question"])
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


# ---- a quoted 稳赚 that is doubted (shared hard_claim) -------------------------------------------

MENTIONS = (
    "对“稳赚”的说法先核实成本。",
    "警惕任何“稳赚”说法。",
    "别信“稳赚”之类的话。",
    "远离所谓“稳赚”的推荐。",
)
STILL_HARD = (
    "对“稳赚”说法要核实，8月加仓稳赚。",  # another item in the sentence
    "警惕“稳赚”说法，但这笔投资稳赚。",  # a statement after a turn
    "不能说要警惕“稳赚”说法。",  # an outer negation
    "不是说对“稳赚”说法要核实。",
    "不用警惕“稳赚”说法。",  # the doubt undone
    "别对“稳赚”说法存疑。",
    "不要对“稳赚”说法追问。",
    "对“稳赚”说法不必核实。",  # a denial after the noun
    "对“稳赚”说法不太需要核实。",  # a degree word
    "对“稳赚”说法要相信。",
    "“稳赚”说法是真的。",
    "对任何稳赚说法都要核实。",  # not quoted
    "这笔投资“稳赚”。",
)


def test_the_r9_doubted_mention_passes():
    assert hard_claim([FIXTURE["gain_mention"]]) is None


@pytest.mark.parametrize("text", MENTIONS)
def test_doubted_mentions_pass(text):
    assert hard_claim([text]) is None, text


@pytest.mark.parametrize("text", STILL_HARD)
def test_what_only_looks_doubted_is_still_refused(text):
    assert hard_claim([text]) == "稳赚", text


async def test_a_doubted_mention_is_submitted_without_repair(make):  # noqa: F811
    text = FIXTURE["gain_mention"].lstrip("- ")
    runtime, _, _ = make(
        lambda m: written(m, extra=text), written, birth=INVESTMENT_CASE["profile"]
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)


# ---- the safety reply lists readable facts ---------------------------------------------------


async def test_the_safety_reply_lists_the_fact_texts(make):  # noqa: F811
    hard = "8月加仓稳赚。"
    runtime, _, _ = make(
        lambda m: written(m, extra=hard),
        lambda m: written(m, extra=hard),
        birth=INVESTMENT_CASE["profile"],
    )
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    assert outcome.data["pipeline"]["degraded"] == "safety"
    assert "这次不作解读" in outcome.text
    assert "period:" not in outcome.text and "T16:00:00" not in outcome.text
    assert "流年丙午（十神劫财" in outcome.text


# ---- the ten gods' pillar keys in keywords ---------------------------------------------------


async def test_keywords_carry_no_pillar_keys(make):  # noqa: F811
    """Typed birth #2's keyword reading: “时柱戊辰（天干戊为劫财），常和劫财:time联系在一起”."""
    runtime, composer, _ = make(broken, broken, birth=TYPED_PROFILE)
    outcome = await runtime.turn(CASES["bazi_pilot_typed_birth"]["question"])
    assert outcome.status == "submit_reading", outcome.text
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    sheet = composer.seen[0][0][1]["content"]
    for text in (outcome.text, sheet):
        assert not re.search(r":(?:year|month|day|time)\b", text)
    assert "常和劫财联系在一起" in outcome.text or "常和七杀联系在一起" in outcome.text
