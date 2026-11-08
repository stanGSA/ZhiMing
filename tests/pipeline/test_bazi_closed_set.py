"""The bazi closed set (P3.4): what a correct reading may say, and what must still be refused.

Each relaxation (a denied wrong value, a denied inference, a hidden stem's ten god named as one)
has guards next to it: another value in the same sentence, a denial then a statement, an outer
negation (不能说/不可能/不是不), a degree word (完全/根本), a double negation, and a statement
again after a turn (但其实). The chart is computed, never typed in.
"""

from types import SimpleNamespace

import pytest

from pipeline.bazi import Bazi
from plugins.bazi.calculator import relations, ten_god
from tests.pipeline.test_runner_bazi import NEXT_MONTH, SHANGHAI, TRAIT, make, written  # noqa: F401

STEMS = "甲乙丙丁戊己庚辛壬癸"
TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")


@pytest.fixture
async def chart(make):  # noqa: F811
    return await computed(make, NEXT_MONTH, SHANGHAI)


async def computed(make, question, birth):  # noqa: F811
    runtime, _, _ = make(written, birth=birth)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    state = runtime.session.state
    return SimpleNamespace(
        session=SimpleNamespace(state=state, policy_judge=None),
        natal=state["bazi_result"],
        period=state.get("bazi_period_result") or {"periods": []},
    )


def refused(chart, text: str) -> list[str]:
    return Bazi(None).problems([text], chart.session)


def other_stem(stem: str) -> str:
    return next(s for s in STEMS if s != stem and STEMS.index(s) // 2 != STEMS.index(stem) // 2)


def element(stem: str) -> str:
    return "木木火火土土金金水水"[STEMS.index(stem)]


def month_god(chart) -> tuple[str, str, str]:
    gz = chart.natal["pillars"]["month"]
    god = chart.natal["ten_gods_stems"]["month"]
    other = next(g for g in TEN_GODS if g != god)
    return gz, god, other


def a_relation(chart, present: bool):
    """(flow label, flow ganzhi, natal key, natal ganzhi, word) with or without the relation."""
    natal = chart.natal["pillars"]
    for item in chart.period["periods"]:
        gz = item["pillars"]["month"]
        for key, label in (("year", "年柱"), ("month", "月柱"), ("day", "日柱"), ("time", "时柱")):
            if not natal.get(key):
                continue
            kinds = {r["type"] for r in relations(gz, {key: natal[key]})}
            has = bool(kinds & {"地支冲", "天干冲"})
            if has == present:
                return "流月", gz, label, natal[key], "相冲"
    pytest.skip("no such relation in this chart")


# ---- the day master ------------------------------------------------------------------------


async def test_day_master_statements(chart):
    master = chart.natal["day_master"]
    stem, wrong = master[0], other_stem(master[0])
    right = f"{stem}{element(stem)}"
    other = f"{wrong}{element(wrong)}"
    for text in (
        f"你的日主是{right}，做事讲分寸。",
        f"你是{right}日主。",
        f"日主不是{other}，而是{right}。",  # a denied wrong value
        f"并不是{other}日主就一定急躁。",  # a denied inference
        f"日主{right}，并不是{right}日主都外向。",
    ):
        assert refused(chart, text) == [], text
    for text in (
        f"你的日主是{other}。",
        f"日主不是{right}。",  # denying the computed value
        f"日主根本不是{right}。",  # a degree word
        f"日主完全不是{right}。",
        f"日主不完全是{other}。",
        f"日主不是{right}，而是{other}。",  # another value in the same sentence
        f"日主不是{other}，但其实是{other}。",  # stated again after a turn
        f"不能说日主不是{other}。",  # an outer negation
        f"不可能日主不是{other}。",
        f"日主并非不是{other}。",  # a double negation
        f"日主不是不是{other}。",
        f"日主是{stem}{element(other_stem(stem))}。",  # a stem with another element
    ):
        assert refused(chart, text), text


# ---- ten gods ------------------------------------------------------------------------------


async def test_ten_gods_named_for_a_pillar(chart):
    gz, god, other = month_god(chart)
    for text in (
        f"月柱{gz}为{god}。",
        f"月柱天干是{god}。",
        f"{gz}透出{god}，压力和要求会更明显。",
        f"月柱{gz}不是{other}，而是{god}。",
    ):
        assert refused(chart, text) == [], text
    for text in (
        f"月柱{gz}为{other}。",
        f"月柱{gz}不是{god}。",
        f"月柱{gz}根本不是{god}。",
        f"月柱{gz}不是{other}，但其实是{other}。",
        f"不能说月柱{gz}不是{other}。",
        f"月柱{gz}并非不是{other}。",
        f"月柱{gz}为{god}，年柱{gz}为{god}。",  # another pillar's ganzhi is not this one's
    ):
        assert refused(chart, text), text


async def test_ten_gods_of_the_flow_months(chart):
    first = chart.period["periods"][0]
    gz, god = first["pillars"]["month"], first["ten_gods"]["month"]
    other = next(
        g for g in TEN_GODS if g not in {p["ten_gods"]["month"] for p in chart.period["periods"]}
    )
    assert refused(chart, f"流月{gz}十神为{god}。") == []
    assert refused(chart, f"流月{gz}为{other}。")
    assert refused(chart, f"流月{gz}不是{god}。")


async def test_a_ten_god_absent_from_the_chart(make):  # noqa: F811
    # Without a gender no luck cycles are computed, so fewer ten gods are on the chart.
    unsexed = {k: v for k, v in SHANGHAI.items() if k != "gender"}
    chart = await computed(make, TRAIT, unsexed)
    natal, periods = chart.natal, chart.period["periods"]
    master = natal["day_master"][0]
    present = set(natal["ten_gods_stems"].values())
    present |= {ten_god(master, s["ganzhi"][0]) for s in (natal["dayun"] or {}).get("sequence", [])}
    present |= {g for p in periods for g in p["ten_gods"].values()}
    hidden = {g for gods in natal["hidden_ten_gods"].values() for g in gods}
    absent = next((g for g in TEN_GODS if g not in present | hidden), None)
    if absent is None:
        pytest.skip("every ten god is on this chart")
    assert refused(chart, f"命局里没有{absent}。") == []  # a denial of an absent one
    some = next(iter(natal["ten_gods_stems"].values()))
    assert refused(chart, f"命局里没有{some}。")  # denying one the chart has
    assert refused(chart, f"命局里根本没有{some}。")
    assert refused(chart, f"你的{absent}很旺，适合竞争。")
    assert refused(chart, f"不能说没有{absent}。") or absent in hidden
    in_hidden = next(iter(hidden - present), None)
    if in_hidden:
        assert refused(chart, f"地支藏干里有{in_hidden}。") == []
    not_hidden = next((g for g in TEN_GODS if g not in hidden), None)
    if not_hidden:
        assert refused(chart, f"地支藏干里有{not_hidden}。")


# ---- luck cycles ---------------------------------------------------------------------------


async def test_luck_cycles(chart):
    dayun = chart.natal["dayun"]
    sequence = [s["ganzhi"] for s in dayun["sequence"]]
    current = dayun["current_candidates"][0]["ganzhi"]
    later = sequence[2]
    year = dayun["sequence"][1]["start_year"]
    y, m, d = map(int, dayun["start_solar"].split("-"))
    for text in (
        f"首步大运{sequence[0]}。",
        f"第三步大运是{sequence[2]}。",
        f"当前大运{current}。",
        f"{year}年交运。",
        f"{y}年{m}月{d}日起运。",
        f"首步大运不是{later}，而是{sequence[0]}。",
    ):
        assert refused(chart, text) == [], text
    for text in (
        f"首步大运{later}。",
        f"首步大运不是{sequence[0]}。",
        f"首步大运不是{later}，但其实是{later}。",
        f"不能说首步大运不是{later}。",
        f"第二步大运是{sequence[0]}。",
        f"{year + 1}年交运。",
        f"{y}年{m}月{d + 1 if d < 28 else d - 1}日起运。",
        "当前大运甲子。" if "甲子" not in sequence else "当前大运乙丑。",
    ):
        assert refused(chart, text), text


# ---- relations -----------------------------------------------------------------------------


async def test_relations_to_the_natal_chart(chart):
    label, gz, natal, natal_gz, word = a_relation(chart, present=True)
    assert refused(chart, f"{label}{gz}与{natal}{natal_gz}{word}，节奏容易被打乱。") == []
    assert refused(chart, f"{label}{gz}冲{natal}{natal_gz}，需要留出缓冲。") == []
    for text in (
        f"{label}{gz}与{natal}{natal_gz}不冲。",
        f"{label}{gz}与{natal}{natal_gz}根本不冲。",
        f"{label}{gz}与{natal}{natal_gz}完全没有相冲。",
    ):
        assert refused(chart, text), text


async def test_relations_the_chart_does_not_have(chart):
    label, gz, natal, natal_gz, word = a_relation(chart, present=False)
    assert refused(chart, f"{label}{gz}与{natal}{natal_gz}并不相冲。") == []
    for text in (
        f"{label}{gz}与{natal}{natal_gz}{word}。",
        f"{label}{gz}冲{natal}{natal_gz}。",
        f"{label}{gz}与{natal}{natal_gz}不冲，但其实相冲。",  # stated again after a turn
        f"不能说{label}{gz}与{natal}{natal_gz}不冲。",  # an outer negation
        f"{label}{gz}与{natal}{natal_gz}不是不冲。",  # a double negation
        f"{label}{gz}与{natal}{natal_gz}并不相冲，与日柱也相合。"
        if not any(
            r["type"] in {"天干合", "地支六合"}
            for r in relations(gz, {"day": chart.natal["pillars"]["day"]})
        )
        else f"{label}{gz}与{natal}{natal_gz}{word}。",  # another relation in the same sentence
    ):
        assert refused(chart, text), text


# ---- stem-branch pairs and labels -----------------------------------------------------------


async def test_ganzhi_outside_the_calculation(chart):
    known = Bazi.known_ganzhi(chart.session.state)
    jiazi = [STEMS[i % 10] + "子丑寅卯辰巳午未申酉戌亥"[i % 12] for i in range(60)]
    unknown = next(gz for gz in jiazi if gz not in known)
    assert refused(chart, f"这段时间{unknown}当令。")
    assert refused(chart, f"这里不是{unknown}。") == []
    assert refused(chart, "你要多照顾自己，自己午后容易累。") == []  # 己 in 自己 is no stem


async def test_a_label_written_before_its_placeholder(chart):
    gz = chart.period["periods"][0]["pillars"]["month"]
    assert any("写了两遍" in p for p in refused(chart, f"流月流月{gz}提示你放慢节奏。"))
