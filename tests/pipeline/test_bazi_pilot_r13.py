"""Bazi pilot r12 findings (docs/verification/p3/bazi-pilot-r12/review.md), fixed in r13.

- Career #2: “流年与本命日柱之间有配合松动的迹象” (配合松动 is 地支破's own gloss) was read as a
  claim of 合; both drafts were refused and the reading was degraded to keywords.
- Luck cycles #2: “你目前正走在这十年的中段偏后位置” in 2026, the 4th year of the cycle from 2023,
  passed every check (a known escape). The sheet did not say where in the cycle today lies.
- Investment #1 and #3: “2月4日以后到夏季” was read as February and summer, “2月到入夏” as
  February alone; the months between were left out. “秋季到年底” started at 年底.
- Investment #3: “如果你正在做资金安排，建议分批、留应急金” in the layer “4月5日起到8月8日前后”
  recommends a pace of investing with its verb left out (owner, 2026-11-12: a known escape).

The relaxations carry their guards (still refused): another item in the sentence, a denial then a
statement, an outer negation, a degree word, a double negation, a statement again after a turn.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app import create_runtime
from pipeline.bazi import TRADE_PROBLEM, Bazi, title_spans
from tests.pipeline.drafts import Composer
from tests.pipeline.test_bazi_pilot_r5 import CASES, has
from tests.pipeline.test_runner_bazi import written

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/bazi_pilot_r12_review.json").read_text(encoding="utf-8")
)
CLOCK = datetime(2026, 11, 12, 14, 24, tzinfo=UTC)  # the r12 pipeline run
RELATION = "没有合的关系"
POSITION = "在当前大运己未（2023年交运，2033年换下一步）的第4年"


@pytest.fixture
def run_at(project):
    """A runtime at the r12 clock whose writer returns the given drafts."""
    runtimes = []

    async def build(case_id, *drafts):
        case = CASES[case_id]
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project,
            user_id=f"r13-{case_id}",
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        runtimes.append(runtime)
        runtime.store.update_profile_fields(f"r13-{case_id}", case["profile"], "合成测试资料")
        runtime.session.profile = runtime.store.get_profile(f"r13-{case_id}")
        runtime.session.refresh_calendar(CLOCK)
        outcome = await runtime.turn(case["question"])
        assert outcome.status == "submit_reading", outcome.text
        return runtime, outcome, composer

    yield build
    for runtime in runtimes:
        runtime.close()


def calls(outcome) -> tuple:
    info = outcome.data["pipeline"]
    return info["model_calls"], info["repairs"], info["degraded"]


def problems(session, text: str) -> list[str]:
    return Bazi(None).problems([text], session)


def findings(session, title: str, body: str) -> list[tuple[str, str]]:
    args = {"summary": "整体平稳。", "sections": [{"title": title, "body": body, "ref_ids": []}]}
    return Bazi(None).section_findings(args, [], session)


# ---- 配合 is not 合 --------------------------------------------------------------------------


@pytest.mark.parametrize("draft", [0, 1])
async def test_the_r12_career_drafts_are_submitted_first_time(run_at, draft):
    *_, outcome, _ = await run_at(
        "bazi_pilot_next_month_career", FIXTURE["career_drafts"][draft], written
    )
    assert calls(outcome) == (1, 0, None)


@pytest.fixture
async def career(run_at):
    runtime, *_ = await run_at("bazi_pilot_next_month_career", written)
    return runtime.session


@pytest.mark.parametrize(
    "text",
    [
        "流年与本命日柱之间配合松动，流年与本命日柱也相合。",  # another item in the sentence
        "流年与本命日柱配合顺利并且相合。",
        "流年与本命日柱之间不是配合松动，而是相合。",  # a denial then a statement
        "流年与本命日柱之间配合松动，不能说不相合。",  # an outer negation
        "流年与本命日柱之间配合松动，但其实完全相合。",  # a degree word
        "流年与本命日柱之间配合松动，但不是不相合。",  # a double negation
        "流年与本命日柱之间配合松动，但其实相合。",  # a statement after a turn
        "流年与本命日柱相合。",
    ],
)
async def test_a_relation_said_beside_an_ordinary_word_is_refused(career, text):
    assert has(problems(career, text), RELATION), text


@pytest.mark.parametrize(
    "text",
    [
        "同时流年与本命日柱之间有配合松动的迹象，适合定期回头检查。",
        "流年与本命日柱之间出现配合松动、衔接处有缝隙的迹象。",
        "流年与本命日柱不相合，配合也一般。",
        "流年与本命日柱之间有突破的机会。",
        "流年与本命日柱地支破，配合松动。",
    ],
)
async def test_an_ordinary_word_claims_no_relation(career, text):
    assert not has(problems(career, text), RELATION), text


# ---- where in the current luck cycle today lies -------------------------------------------


@pytest.fixture
async def luck(run_at):
    runtime, *_ = await run_at("bazi_pilot_dayun", written)
    return runtime


async def test_the_r12_position_is_refused(luck):
    assert has(problems(luck.session, FIXTURE["position"]), POSITION)


@pytest.mark.parametrize(
    "text,refused",
    [
        ("你目前正走在这十年的前半段。", False),
        ("你目前在这十年的中段。", False),
        ("目前在这步大运的第4年。", False),
        ("你并不是在这十年的中段偏后。", False),
        ("前一步戊午大运的后半段比较辛苦。", False),  # another cycle
        ("这一步的后期规划要提早做。", False),
        ("你在这十年的后半段。", True),
        ("你在己未大运的尾声。", True),
        ("目前在这步大运的第6年。", True),
        ("你不是在这十年的前半段。", True),  # the right part denied
        ("不能说你不在这十年的中段偏后。", True),  # an outer negation
        ("你完全在这十年的后半段。", True),  # a degree word
        ("你并不完全在这十年的前半段。", True),
        ("不是不在这十年的后半段。", True),  # a double negation
        ("你不在这十年的后半段，但其实在这十年的后半段。", True),  # a statement after a turn
    ],
)
async def test_positions_against_the_years_since_the_handover(luck, text, refused):
    assert has(problems(luck.session, text), POSITION) is refused, text


async def test_the_sheet_says_where_today_lies(run_at):
    *_, composer = await run_at("bazi_pilot_dayun", written)
    sheet = composer.seen[0][0][1]["content"]
    assert "今天（2026-11-12）在当前大运己未的第4年（2023年交运，2033年换下一步）" in sheet
    assert "属于这十年的前半段" in sheet


async def test_a_wrong_position_is_repaired_with_its_sentence(run_at):
    sentence = "也就是说你目前正走在这十年的中段偏后位置。"
    _, outcome, composer = await run_at(
        "bazi_pilot_dayun",
        lambda m: written(m, extra=sentence),
        lambda m: written(m, extra="也就是说你目前走在这十年的前半段。"),
    )
    assert calls(outcome) == (2, 1, None)
    assert f"出问题的句子：“{sentence}”" in composer.seen[1][0][-1]["content"]


# ---- a month joined to a season or part of the year ---------------------------------------

YEAR = (date(2027, 1, 1), date(2027, 12, 31), date(2026, 11, 12))


@pytest.mark.parametrize(
    "title,spans",
    [
        ("2月4日以后到夏季：摩擦偏多，别急着加码", [(date(2027, 2, 4), date(2027, 8, 31))]),
        ("2月到入夏：责任压上来，适合按规矩来", [(date(2027, 2, 1), date(2027, 5, 31))]),
        ("秋季到年底：节奏趋稳，但仍以稳健为先", [(date(2027, 8, 1), date(2027, 12, 31))]),
        ("5月至年中：压力", [(date(2027, 5, 1), date(2027, 8, 31))]),
    ],
)
def test_linked_titles_are_one_range(title, spans):
    assert title_spans(title, *YEAR) == spans


def test_linked_title_crosses_into_the_next_calendar_year():
    period = (date(2026, 11, 1), date(2027, 10, 31), date(2026, 11, 12))
    assert title_spans("11月到年中：跨年安排", *period) == [
        (date(2026, 11, 1), date(2027, 8, 31)),
        (date(2027, 11, 1), date(2028, 8, 31)),
    ]


async def test_the_r12_investment_drafts(run_at):
    """#3's first draft is refused for its batch recommendation only (its title 2月到入夏 holds
    癸卯); #1's two drafts keep only their real error, 丁未 (7月7日–8月8日) under 秋季到年底 and
    under 8月8日至12月7日."""
    *_, outcome, composer = await run_at(
        "bazi_pilot_investment_risk", FIXTURE["investment3_draft"], written
    )
    assert calls(outcome) == (2, 1, None)
    assert outcome.data["pipeline"]["problems"][0] == [TRADE_PROBLEM]
    assert "出问题的句子：“如果你正在做资金安排，建议分批" in composer.seen[1][0][-1]["content"]
    for draft, title in zip(
        FIXTURE["investment1_drafts"], ("秋季到年底", "8月8日至12月7日"), strict=True
    ):
        *_, outcome, _ = await run_at("bazi_pilot_investment_risk", draft, written)
        assert calls(outcome) == (2, 1, None)
        (found,) = outcome.data["pipeline"]["problems"][:1]
        assert len(found) == 1 and title in found[0] and "流月丁未" in found[0], found


@pytest.fixture
async def money(run_at):
    runtime, *_ = await run_at("bazi_pilot_investment_risk", written)
    return runtime.session


@pytest.mark.parametrize(
    "title,body",
    [
        ("2月4日以后到夏季：摩擦", "流月壬寅、流月己酉提示节奏变化。"),  # 己酉 from 9月8日
        ("2月到入夏：压力", "流月壬寅、流月丙午提示节奏变化。"),  # 丙午 6月6日–7月7日
        ("2月4日以后，到夏季再看：压力", "流月癸卯提示节奏变化。"),  # not joined by 到
        ("秋季到年底：趋稳", "流月丁未提示节奏变化。"),  # 7月7日–8月8日
    ],
)
async def test_linked_titles_against_flow_months(money, title, body):
    assert findings(money, title, body), title


@pytest.mark.parametrize(
    "title,body",
    [
        ("2月4日以后到夏季：摩擦", "流月癸卯、流月丁未提示节奏变化。"),
        ("2月到入夏：压力", "流月癸卯、流月甲辰、流月乙巳提示节奏变化。"),
    ],
)
async def test_linked_titles_hold_their_flow_months(money, title, body):
    assert findings(money, title, body) == [], title


# ---- a recommended pace of investing in a dated layer -------------------------------------


async def test_the_r12_batch_recommendation_is_refused(money):
    found = findings(money, FIXTURE["batch_title"], FIXTURE["batch"])
    assert (
        TRADE_PROBLEM,
        "如果你正在做资金安排，建议分批、留应急金，并和伴侣或家人把边界讲清楚。",
    ) in found


@pytest.mark.parametrize(
    "body",
    [
        "如果你正在做资金安排，建议留应急金、分批。",  # another item first
        "如果你正在做资金安排，建议还是尽量分批。",  # a degree word
        "不能说不建议分批。",  # an outer negation
        "不是不建议分批。",  # a double negation
        "不建议一次性全投，但其实更适合分批。",  # a statement after a turn
        "这段时间可以考虑定投。",
    ],
)
async def test_batch_recommendations_in_a_dated_layer(money, body):
    assert has([p for p, _ in findings(money, FIXTURE["batch_title"], body)], TRADE_PROBLEM)


@pytest.mark.parametrize(
    "body",
    [
        "不建议分批。",
        "建议别急着分批。",
        "全年看，把“全投”换成“分批、留底、按预算”更稳妥。",  # r8 investment #1 (owner: passes)
        "小额学习：如果真想接触，先用不影响生活的金额熟悉规则，不押上全部积蓄。",  # r11 #2
        "如果你正在做资金安排，先留应急金，并和伴侣或家人把边界讲清楚。",
    ],
)
async def test_restraint_in_a_dated_layer_passes(money, body):
    assert not has([p for p, _ in findings(money, FIXTURE["batch_title"], body)], TRADE_PROBLEM)


def test_batch_recommendations_by_sentence():
    assert Bazi.trade_problems("明年建议分批。") == [TRADE_PROBLEM]
    assert Bazi.trade_problems("这一阶段更适合分批。") == [TRADE_PROBLEM]
    for text in (
        "如果你正在做资金安排，建议分批、留应急金。",  # no time of its own
        "全年看，把“全投”换成“分批、留底、按预算”更稳妥。",
        "明年不建议分批。",
        # r11 single investment #2: 定投资纪律 sets a discipline, it is no 定投.
        "2027年4月4日前后是比较容易落地的节点，适合定投资纪律，而不是当晚加仓。",
    ):
        assert Bazi.trade_problems(text) == [], text


async def test_a_batch_recommendation_is_repaired_with_its_sentence(run_at):
    sentence = "如果你正在做资金安排，建议分批、留应急金。"

    def dated(messages, extra):
        layer = f"【分层】4月5日起到8月8日前后：起伏多\n{extra}\n【建议】"
        return written(messages).replace("【建议】", layer, 1)

    _, outcome, composer = await run_at(
        "bazi_pilot_investment_risk",
        lambda m: dated(m, sentence),
        lambda m: dated(m, "如果你正在做资金安排，先留应急金。"),
    )
    assert calls(outcome) == (2, 1, None)
    assert f"出问题的句子：“{sentence}”" in composer.seen[1][0][-1]["content"]
