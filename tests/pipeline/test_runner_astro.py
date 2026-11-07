"""Astrology through the pipeline with scripted models (P3 of the plan)."""

import re
from datetime import UTC, datetime

import pytest

from app import create_runtime
from pipeline import requirements
from pipeline.astro import ASPECT_ZH
from pipeline.runner import PipelineRunner
from plugins.astro.calculator import BODY_ZH
from plugins.astro.tools import AstroPlugin
from tests.pipeline.drafts import Composer

CLOCK = datetime(2026, 10, 30, 4, 0, tzinfo=UTC)  # noon in Shanghai, 2026-10-30
SHANGHAI = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 31.23,
    "lon": 121.47,
    "time_known": True,
}
LOS_ANGELES = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "America/Los_Angeles",
    "lat": 34.05,
    "lon": -118.24,
    "birth_place": "洛杉矶",
    "time_known": True,
}
NEXT_MONTH = "看星盘，下个月事业运怎么样？"
TRAIT = "看星盘，我的性格有什么特点？"
LINE = re.compile(r"^(R\d+)｜(\S+?)｜(\S+?)｜", re.M)


def facts_in(messages) -> list[tuple[str, str, str]]:
    return LINE.findall(messages[1]["content"])


def aliases(messages, label: str) -> list[str]:
    return [alias for alias, lab, _ in facts_in(messages) if lab == label]


def written(messages, extra="") -> str:
    facts = facts_in(messages)
    transit = [a for a, label, _ in facts if label in ("行运相位", "行运")]
    natal = [a for a, label, _ in facts if label.startswith("本命")]
    first = transit[0] if transit else natal[0]
    second = natal[0]
    return (
        "【表态】平稳\n【摘要】这段时间整体平稳，适合按计划推进。留意沟通节奏。\n"
        f"【分层】这段时间的节奏\n{{{{{first}}}}}提示你把精力放在长期目标上。{extra}\n【引用】{first}\n"
        f"【分层】你的底色\n{{{{{second}}}}}说明你做事偏稳，往往先观察再行动。\n【引用】{second}\n"
        "【建议】\n- 先排序：把这个月最重要的两件事写下来。\n【收尾】按自己的节奏来。"
    )


def broken(messages) -> str:
    return "这不是标记文本"


@pytest.fixture
def make(project):
    runtimes = []

    def build(*replies, user_id="astro-user", birth=SHANGHAI, selected=None):
        composer = Composer(*replies)
        runtime = create_runtime(
            root=project,
            user_id=user_id,
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        if birth:
            runtime.store.update_profile_fields(user_id, birth, "合成测试资料")
            runtime.session.profile = runtime.store.get_profile(user_id)
        runtime.session.refresh_calendar(CLOCK)
        if selected:
            runtime.session.state["selected_systems"] = selected
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def planned(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


async def test_a_month_takes_one_writing_call(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    calls = planned(events)
    assert calls[:3] == ["start_reading", "compute_natal_chart", "compute_transits"]
    assert calls[-1] == "submit_reading" and set(calls[2:-1]) == {"compute_transits"}
    assert len(calls[2:-1]) <= 3  # the transit tiers
    ((messages, tools),) = composer.seen
    assert tools == [] and "astro:" not in str(messages)
    sheet = messages[1]["content"]
    assert "日期范围：2026-11-01至2026-11-30（Asia/Shanghai" in sheet
    transit = runtime.session.state["transit_result"]
    assert (transit["start"], transit["end"], transit["tz"]) == (
        "2026-11-01",
        "2026-11-30",
        "Asia/Shanghai",
    )
    labels = {label for _, label, _ in facts_in(messages)}
    assert "行运相位" in labels and "本命落座" in labels
    assert len(aliases(messages, "行运相位")) <= 12
    reading = outcome.data["reading"]
    assert reading["question_type"] == "timing"
    assert "行运" in reading["sections"][0]["body"] and "北京时间" in reading["sections"][0]["body"]
    # Beijing time is not a default: nothing is noted.
    assert "出生地" not in reading["closing"]


async def test_missing_birth_time_answer_is_used(make):
    birth = {**SHANGHAI, "birth_local_dt": "1996-05-10"}
    runtime, _, _ = make(written, birth=birth)
    first = await runtime.turn(TRAIT)
    assert first.status == "ask_user" and "出生钟表时间" in first.text
    second = await runtime.turn("早上8点30分")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["natal_result"]["input"]["birth_local"] == "1996-05-10 08:30"
    assert second.data["pipeline"]["asks"] == 1


async def test_ambiguous_birth_time_answer_supplies_fold(make):
    birth = {
        **SHANGHAI,
        "birth_local_dt": "1996-10-27 01:30",
        "tz": "America/New_York",
        "lat": 40.71,
        "lon": -74.01,
    }
    runtime, _, _ = make(written, birth=birth)
    first = await runtime.turn(TRAIT)
    assert first.status == "ask_user" and "fold=1" in first.text
    second = await runtime.turn("回拨后，fold=1")
    assert second.status == "submit_reading", second.text
    assert second.data["pipeline"]["asks"] == 1


async def test_a_trait_question_reads_the_natal_chart_only(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(TRAIT)
    assert outcome.status == "submit_reading", outcome.text
    assert "compute_transits" not in planned(events)
    assert outcome.data["reading"]["question_type"] == "trait"
    labels = {label for _, label, _ in facts_in(composer.seen[0][0])}
    assert labels <= {"本命落座", "本命宫位", "本命相位"} and "本命宫位" in labels


async def test_overseas_birth_without_residence_uses_the_birth_timezone(make):
    """Owner, 2026-11-07: the birth place's timezone, and the reading says so."""
    runtime, composer, events = make(written, birth=LOS_ANGELES)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    assert "ask_user" not in planned(events)
    transit = runtime.session.state["transit_result"]
    assert transit["tz"] == "America/Los_Angeles"
    closing = outcome.data["reading"]["closing"]
    assert "日期按出生地洛杉矶的时区（America/Los_Angeles）计算" in closing
    assert "America/Los_Angeles当地日期" in outcome.data["reading"]["sections"][0]["body"]


async def test_overseas_birth_with_a_stated_residence_is_asked(make):
    runtime, composer, events = make(written, birth=LOS_ANGELES)
    outcome = await runtime.turn("看星盘，我现在住在多伦多，下个月事业运怎么样？")
    assert outcome.status == "ask_user", outcome.text
    assert "哪个城市的时间" in outcome.text
    assert "compute_transits" not in planned(events)
    assert composer.seen == []


async def test_a_stated_timezone_is_used(make):
    runtime, composer, events = make(written, birth=LOS_ANGELES)
    outcome = await runtime.turn("看星盘，按北京时间，下个月事业运怎么样？")
    assert outcome.status == "submit_reading", outcome.text
    assert runtime.session.state["transit_result"]["tz"] == "Asia/Shanghai"
    assert "出生地" not in outcome.data["reading"]["closing"]


async def test_an_unclear_range_is_asked_and_the_answer_resumes_the_run(make):
    runtime, composer, events = make(written)
    first = await runtime.turn("看星盘，最近的事业运怎么样？")
    assert first.status == "ask_user" and first.text == requirements.UNCLEAR_RANGE
    assert composer.seen == []
    stored = runtime.store.unfinished_pipeline_run(runtime.session.user_id)
    assert stored["stage"] == "awaiting_input" and stored["state"]["needs"] == "range"
    second = await runtime.turn("下个月")
    assert second.status == "submit_reading", second.text
    transit = runtime.session.state["transit_result"]
    assert (transit["start"], transit["end"]) == ("2026-11-01", "2026-11-30")
    # One reading: the answer did not start another.
    assert planned(events).count("start_reading") == 1
    assert second.data["pipeline"]["asks"] == 1
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None


async def test_missing_birth_data_asks_for_the_form(make):
    runtime, composer, events = make(written, birth=None, selected=["astro"])
    outcome = await runtime.turn("我下个月事业运怎么样？")
    assert outcome.status == "ask_user" and outcome.text == requirements.BIRTH_FORM
    # Still missing on the next message: the agent loop takes over.
    assert PipelineRunner(runtime).detect("继续") is None
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None


async def test_two_broken_drafts_degrade_to_the_facts(make):
    runtime, *_ = make(broken, broken)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    sections = outcome.data["reading"]["sections"]
    assert sections[0]["title"] == "行运相位" and "精确" in sections[0]["body"]


# ---- closed vocabulary (P3.4) -------------------------------------------------------------


@pytest.fixture
async def charted(make):
    """A month's reading on a known chart, and the astro system to check sentences with."""
    runtime, composer, events = make(written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading"
    astro = PipelineRunner(runtime).systems["astro"]
    return runtime, astro


def planet(runtime, body):
    return next(p for p in runtime.session.state["natal_result"]["planets"] if p["body"] == body)


def other_sign(sign_zh):
    from plugins.astro.calculator import SIGN_ZH

    return next(s for s in SIGN_ZH if s != sign_zh)


async def test_every_rendered_fact_passes_its_own_check(charted):
    runtime, astro = charted
    texts = [text for _, text in astro.texts(runtime.session.state).values()]
    assert astro.problems(texts, runtime.session) == []


async def test_correct_hand_written_positions_pass(charted):
    runtime, astro = charted
    sun = planet(runtime, "Sun")
    transit = runtime.session.state["transit_result"]
    event = AstroPlugin.project(dict(transit))["events"][0]  # one the fact sheet lists
    sentences = [
        f"你的太阳在{sun['sign_zh']}座，做事偏稳。",
        f"太阳落{sun['sign_zh']}，本命太阳在第{sun['house']}宫。",
        f"{event['exact_date'][5:7].lstrip('0')}月{event['exact_date'][8:].lstrip('0')}日前后留意节奏。",
        "1996年5月10日出生的你，往往先观察再行动。",
        "这个月整体平稳，土星的提醒是循序渐进。",
        "并不是白羊座的太阳，而是金牛座的太阳。",
    ]
    assert astro.problems(sentences, runtime.session) == []


async def test_wrong_positions_are_caught(charted):
    runtime, astro = charted
    sun, moon = planet(runtime, "Sun"), planet(runtime, "Moon")
    wrong_house = sun["house"] % 12 + 1
    asc = runtime.session.state["natal_result"]["asc"]["sign_zh"]
    cases = {
        f"太阳在{other_sign(sun['sign_zh'])}座": "本命太阳在",
        f"本命月亮落{other_sign(moon['sign_zh'])}": "本命月亮在",
        f"太阳的星座是{other_sign(sun['sign_zh'])}": "本命太阳在",
        f"太阳星座{other_sign(sun['sign_zh'])}": "本命太阳在",
        f"月亮落在了{other_sign(moon['sign_zh'])}": "本命月亮在",
        f"太阳的宫位是第{wrong_house}宫": "正文写成了第",
        f"太阳落在了第{wrong_house}宫": "正文写成了第",
        f"太阳在第{wrong_house}宫": "正文写成了第",
        f"上升{other_sign(asc)}座": "上升是",
        "行运土星在双鱼座": "行运土星的星座不在事实表里",
        "2026年11月31日要特别小心": "不在事实表里",
        "2026年12月25日要特别小心": "日期2026年12月25日不在事实表里",
    }
    # A date beside an aspect must be that aspect's own, even when another event falls on it.
    events = runtime.session.state["transit_result"]["events"]
    first = events[0]
    other = next(e for e in events if e["exact_date"] != first["exact_date"])
    day = other["exact_date"]
    claim = (
        f"{int(day[5:7])}月{int(day[8:])}日前后，行运{BODY_ZH[first['transit_body']]}与本命"
        f"{BODY_ZH[first['natal_body']]}形成{ASPECT_ZH[first['aspect']]}。"
    )
    same = {
        e["exact_date"]
        for e in events
        if (e["transit_body"], e["natal_body"], e["aspect"])
        == (first["transit_body"], first["natal_body"], first["aspect"])
    }
    if day not in same:
        cases[claim] = "不是同一句里那个相位的精确日期"
    for sentence, expected in cases.items():
        found = astro.problems([sentence], runtime.session)
        assert any(expected in p for p in found), (sentence, found)


async def test_an_aspect_that_is_not_the_charts_is_caught(charted):
    runtime, astro = charted
    natal = runtime.session.state["natal_result"]
    have = {(a["a"], a["b"], a["type"]) for a in natal["aspects"]}
    have |= {(b, a, t) for a, b, t in have}
    have |= {
        (e["transit_body"], e["natal_body"], e["aspect"])
        for e in runtime.session.state["transit_result"]["events"]
    }
    pair = next(
        (a, b)
        for a in ("Sun", "Moon", "Mercury", "Venus", "Mars")
        for b in ("Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
        if (a, b, "opposition") not in have
    )
    sentence = f"{BODY_ZH[pair[0]]}与{BODY_ZH[pair[1]]}对分相带来拉扯"
    found = astro.problems([sentence], runtime.session)
    assert any("相位只写事实表里的编号" in p for p in found), found


async def test_houses_are_refused_when_the_birth_time_is_unknown(make):
    unknown = {**SHANGHAI, "birth_local_dt": "1996-05-10", "time_known": False}
    runtime, composer, _ = make(written, birth=unknown)
    outcome = await runtime.turn(TRAIT)
    assert outcome.status == "submit_reading", outcome.text
    labels = {label for _, label, _ in facts_in(composer.seen[0][0])}
    assert "本命宫位" not in labels
    assert "出生时间未知" in composer.seen[0][0][1]["content"]
    astro = PipelineRunner(runtime).systems["astro"]
    assert astro.problems(["太阳在第十宫"], runtime.session) == [
        "出生时间未知，没有宫位，正文不能写宫位"
    ]
    assert any("上升" in p for p in astro.problems(["上升天秤"], runtime.session))


async def test_a_wrong_sign_is_repaired_once(make):
    def wrong(messages):
        line = next(text for _, label, text in facts_in(messages) if text.startswith("本命太阳在"))
        sign = line.removeprefix("本命太阳在").removesuffix("座")
        return written(messages, extra=f"你的太阳在{other_sign(sign)}座，所以容易急躁。")

    runtime, composer, events = make(wrong, written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert any("本命太阳在" in p for p in info["problems"][0])
    assert planned(events).count("submit_reading") == 1


# ---- intent ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "用八字和星盘一起看看下个月",  # several systems: P3.5
        "帮我抽一张塔罗，再看看星盘",
        "我和男朋友的合盘怎么样？",  # synastry is not calculated
        "看看我的星盘推运",
        "刚才那个星盘解读里说的木星是什么意思？",  # a follow-up stays with the agent loop
        "我的出生时间记错了，星盘要改成9点",
        "最近工作压力上升，怎么办？",  # 上升 alone is not the rising sign
        "今天运势怎么样？",  # daily
    ],
)
async def test_messages_the_astro_pipeline_leaves_alone(make, message):
    runtime, *_ = make(written)
    found = PipelineRunner(runtime).detect(message)
    assert found is None or found.system != "astro", message


async def test_birth_data_typed_into_the_message_goes_to_the_agent_loop(make):
    runtime, *_ = make(written, birth=None)
    assert PipelineRunner(runtime).detect("我1990年3月5日早上8点出生在上海，看看星盘性格") is None


async def test_a_waiting_question_from_another_conversation_is_not_answered(make, project):
    runtime, composer, _ = make(written)
    first = await runtime.turn("看星盘，最近的事业运怎么样？")
    assert first.status == "ask_user"
    other = create_runtime(
        root=project,
        user_id="astro-user",
        seed=7,
        model=Composer(written),
        mode="pipeline",
        clock=lambda: CLOCK,
    )
    try:
        other.session.refresh_calendar(CLOCK)
        assert PipelineRunner(other).detect("下个月") is None
        assert other.store.unfinished_pipeline_run("astro-user") is None
    finally:
        other.close()


async def test_a_second_unanswered_question_hands_over_to_the_agent_loop(make):
    runtime, composer, events = make(written)
    assert (await runtime.turn("看星盘，最近的事业运怎么样？")).status == "ask_user"
    second = await runtime.turn("我也说不好")
    assert second.status == "ask_user" and second.data.get("reading") is None
    assert PipelineRunner(runtime).detect("还是不确定") is None
    assert composer.seen == []


# ---- the evaluation sets run end to end offline -------------------------------------------


def dataset(name):
    import yaml

    from app import ROOT

    return yaml.safe_load((ROOT / f"evals/cases/{name}.yaml").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize(
    "case",
    dataset("astro_pilot") + dataset("astro_final"),
    ids=lambda case: case["id"],
)
async def test_each_evaluation_case_reaches_submission(make, case):
    runtime, composer, events = make(written, user_id=f"eval-{case['id']}", birth=case["profile"])
    outcome = await runtime.turn(case["question"])
    if outcome.status == "ask_user":
        assert case.get("clarification"), outcome.text
        outcome = await runtime.turn(case["clarification"])
    assert outcome.status == "submit_reading", outcome.text
    assert set(case["tools"]) <= set(planned(events))
    reading = outcome.data["reading"]
    assert reading["systems_used"] == case["systems"]
    assert outcome.data["pipeline"]["model_calls"] <= 3
    if case.get("unknown"):
        assert runtime.session.state["natal_result"]["axes"] is None
    if case.get("risk"):
        assert reading["safety"]["flag"] is True
    transit = runtime.session.state.get("transit_result")
    if case["profile"]["tz"] != "Asia/Shanghai" and transit:
        defaulted = not case.get("clarification")
        assert ("日期按出生地" in reading["closing"]) is defaulted
        assert transit["tz"] == (case["profile"]["tz"] if defaulted else "Asia/Shanghai")


async def test_daylight_saving_birth_and_a_transit_across_midnight(make):
    """Accept-path additions for P3: a DST birth clock, and a transit whose UTC date is not the
    local date. The local date is the fact sheet's; the UTC one is not a date of this range."""
    runtime, composer, _ = make(written, birth=LOS_ANGELES)  # 1996-05-10 08:30 PDT
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    natal = runtime.session.state["natal_result"]
    assert natal["utc"].startswith("1996-05-10T15:30")  # UTC−7 in May, not UTC−8
    astro = PipelineRunner(runtime).systems["astro"]
    transit = runtime.session.state["transit_result"]
    events = AstroPlugin.project(dict(transit))["events"]  # the ones the fact sheet lists
    crossing = next(e for e in transit["events"] if e["exact_utc"][:10] != e["exact_date"])
    # Written alone, a listed date passes; beside its own aspect, any date of that aspect does.
    claim = (
        f"{crossing['exact_date']}，行运{BODY_ZH[crossing['transit_body']]}与本命"
        f"{BODY_ZH[crossing['natal_body']]}形成{ASPECT_ZH[crossing['aspect']]}。"
    )
    assert astro.problems([claim], runtime.session) == []
    utc_day = crossing["exact_utc"][:10]
    assert astro.problems([claim.replace(crossing["exact_date"], utc_day)], runtime.session)
    if utc_day not in {e["exact_date"] for e in events}:
        assert astro.problems([f"{utc_day}前后留意节奏。"], runtime.session)


# ---- r2: transit tiers, repeated labels, time words ---------------------------------------


def listed_transits(messages) -> list[str]:
    return [text for _, label, text in facts_in(messages) if label == "行运相位"]


@pytest.mark.parametrize(
    "question", [NEXT_MONTH, "看星盘，明年的整体运势怎么样？", "看星盘，下周适合谈合作吗？"]
)
async def test_tiers_list_the_same_transits_as_all_ten_planets(make, question):
    """Computing slow planets first changes how long it takes, not what the fact sheet lists."""
    from plugins.astro.calculator import transits

    runtime, composer, events = make(written)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading", outcome.text
    state = runtime.session.state
    tiered = state["transit_result"]
    chart = runtime.store.get_calculation("astro", runtime.session.user_id, state["chart_id"])
    full = transits(chart, tiered["start"], tiered["end"], tiered["tz"])

    def key(e):
        return (e["exact_utc"], e["transit_body"], e["natal_body"], e["aspect"])

    assert [key(e) for e in AstroPlugin.project(dict(tiered))["events"]] == [
        key(e) for e in AstroPlugin.project(dict(full))["events"]
    ]
    assert len(listed_transits(composer.seen[0][0])) == min(12, len(full["events"]))


async def test_a_year_computes_the_slow_planets_only(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn("看星盘，明年的整体运势怎么样？")
    assert outcome.status == "submit_reading", outcome.text
    assert planned(events).count("compute_transits") == 1
    assert runtime.session.state["transit_bodies"] == [
        "Saturn",
        "Jupiter",
        "Mars",
        "Uranus",
        "Neptune",
        "Pluto",
    ]


async def test_listed_transits_carry_their_part_of_the_month(make):
    runtime, composer, events = make(written)
    await runtime.turn(NEXT_MONTH)
    sheet = composer.seen[0][0][1]["content"]
    for line in sheet.splitlines():
        if "｜行运相位｜" in line:
            day = int(re.search(r"2026年11月(\d+)日精确", line)[1])
            part = "上旬" if day <= 10 else "中旬" if day <= 20 else "下旬"
            assert f"｜时段：11月{part}｜" in line, line
    assert "用户说的时间是“下个月”，即2026-11-01至2026-11-30" in sheet


async def test_repeated_labels_are_caught(charted):
    runtime, astro = charted
    mercury = planet(runtime, "Mercury")["sign_zh"]
    for sentence in (
        f"你本命本命水星在{mercury}座。",
        "行运行运土星与本命太阳三分相。",
        "本命的本命水星",
    ):
        assert any("写了两遍" in p for p in astro.problems([sentence], runtime.session)), sentence
    for sentence in (
        f"你的本命水星在{mercury}座。",
        "这是本命盘里的行运提示。",
        "本命和行运要分开看。",
    ):
        assert not any("写了两遍" in p for p in astro.problems([sentence], runtime.session))


async def test_lists_of_planets_are_each_checked(charted):
    runtime, astro = charted
    sun, mercury = planet(runtime, "Sun")["sign_zh"], planet(runtime, "Mercury")["sign_zh"]
    moon = planet(runtime, "Moon")["sign_zh"]
    house = planet(runtime, "Sun")["house"]
    right = [
        f"太阳在{sun}座，水星也在{mercury}座。",
        f"{sun}座的太阳让你更看重稳定。",
        f"太阳同样在{sun}座。",
        f"太阳都在第{house}宫。",
    ]
    if sun == mercury:
        right += [f"太阳、水星都落在{sun}座。", f"太阳与水星同在{sun}座。", f"{sun}座的太阳和水星"]
    assert astro.problems(right, runtime.session) == []
    wrong = other_sign(sun) if other_sign(sun) != mercury else other_sign(mercury)
    for sentence in (
        f"太阳、水星都落在{wrong}座。",
        f"太阳与水星同在{wrong}座。",
        f"太阳也在{wrong}座。",
        f"太阳和月亮均位于{wrong if wrong != moon else other_sign(wrong)}座。",
        f"太阳同样在{wrong}座。",
        f"{wrong}座的太阳和水星",
        f"太阳一起落在了{wrong}座。",
        # The second planet of a list is checked too.
        f"太阳、水星都在{sun if sun != mercury else other_sign(sun)}座。",
        f"第{house % 12 + 1}宫的太阳和月亮",
    ):
        assert any("正文写成了" in p for p in astro.problems([sentence], runtime.session)), sentence
    # r1's escape: the sign first, the second planet wrong (frozen code and the shared
    # validator both let “金牛座的太阳和月亮” through when only the Sun is in Taurus).
    moon_house = planet(runtime, "Moon")["house"]
    second_wrong = []
    if moon != sun:
        second_wrong += [f"{sun}座的太阳和月亮", f"{sun}座的太阳、水星和月亮"]
    if moon_house != house:
        second_wrong.append(f"第{house}宫的太阳和月亮")
    assert second_wrong
    for sentence in second_wrong:
        assert any("正文写成了" in p for p in astro.problems([sentence], runtime.session)), sentence


def summary_args(summary: str, sections=()):
    return {"summary": summary, "sections": list(sections)}


async def test_the_summary_says_the_asked_time(charted):
    runtime, astro = charted  # asked about 下个月 = 2026-11 (today 2026-10-30)
    session = runtime.session
    bad = [
        "这个月事业上先有拉扯，后有配合。",
        "本月整体平稳。",
        "整体来看，这个月不算平顺。",
        "下下个月会更顺。",
        "明年的节奏偏快。",
        "这个月比较平稳。",
    ]
    for summary in bad:
        found = astro.reading_problems(summary_args(summary), [], session)
        assert any("摘要第一句写成了" in p for p in found), summary
    good = [
        "下个月事业上先有拉扯，后有配合。",
        "11月整体平稳，留意沟通。",
        "比起这个月，下个月更适合推进。",
        "下个月不是这个月那样的拉扯，而是先紧后松。",
        "这段时间整体平稳。",
        # Only the first sentence is the answer; later ones may plan around today.
        "下个月整体平稳。这个月先把简历准备好。",
    ]
    for summary in good:
        assert astro.reading_problems(summary_args(summary), [], session) == [], summary


async def test_section_parts_of_the_month_hold_their_transits(make):
    runtime, composer, events = make(written)
    await runtime.turn(NEXT_MONTH)
    session = runtime.session
    astro = PipelineRunner(runtime).systems["astro"]
    facts = astro.facts(session)
    transits_by_day = {}
    for fact in facts:
        if fact.label == "行运相位":
            day = int(re.search(r"11月(\d+)日精确", fact.text)[1])
            transits_by_day.setdefault(day, fact.alias)

    def check(title, day):
        args = summary_args(
            "下个月平稳。", [{"title": title, "body": "", "ref_ids": [transits_by_day[day]]}]
        )
        return astro.reading_problems(args, facts, session)

    for day in transits_by_day:
        part = "上旬" if day <= 10 else "中旬" if day <= 20 else "下旬"
        assert check(f"{part}：节奏", day) == [], (part, day)
        wrong = "下旬" if day <= 10 else "上旬"
        assert check(f"{wrong}：节奏", day), (wrong, day)
    edge = {d for d in transits_by_day if d in (9, 10, 11, 12, 19, 20, 21, 22)}
    for day in edge:
        # 前后 widens a part by two days; without it the boundary is exact.
        near = (
            "月中前后"
            if day in (9, 10, 21, 22)
            else ("月初前后" if day in (11, 12) else "月底前后")
        )
        assert check(near, day) == [], (near, day)
    late = [d for d in transits_by_day if d >= 11]
    if late:
        assert check("月中以后", late[0]) == []
        assert check("上旬到中旬", min(late)) == [] if min(late) <= 20 else True
    early = [d for d in transits_by_day if d <= 20]
    if early:
        assert check("下旬以前", early[0]) == []
