"""Daily fortune through the pipeline with scripted models (P2.3 of the plan)."""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app import create_runtime
from pipeline.daily import Daily
from tests.pipeline.drafts import Composer

TODAY = "今天运势怎么样？"
CLOCK = datetime(2026, 10, 30, 4, 0, tzinfo=UTC)  # noon in Shanghai
BIRTH = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 30.66,
    "lon": 104.07,
    "time_known": True,
}
LINE = re.compile(r"^(R\d+)｜(\S+?)｜(\S+?)｜", re.M)


def facts_in(messages) -> list[tuple[str, str, str]]:
    return LINE.findall(messages[1]["content"])


def alias_of(messages, label: str) -> str:
    return next(alias for alias, lab, _ in facts_in(messages) if lab == label)


def written(messages, extra="") -> str:
    day, card = alias_of(messages, "流日"), alias_of(messages, "每日一牌")
    return (
        "【表态】平稳\n【摘要】今天整体平稳，适合把手头的事做完。留意和同伴分工。\n"
        f"【分层】今天的节奏\n{{{{{day}}}}}提示你明确自己的职责。{extra}\n【引用】{day}\n"
        f"【分层】今天的一张牌\n{{{{{card}}}}}提醒你照顾好正在进行的事。\n【引用】{card}\n"
        "【建议】\n- 先分工：和同伴说清楚各自的部分。\n【收尾】按自己的节奏来。"
    )


def wrong_ten_god(messages) -> str:
    return written(messages, extra="今天流日十神为七杀，压力偏大。")


def broken(messages) -> str:
    return "这不是标记文本"


@pytest.fixture
def make(project):
    runtimes = []

    def build(*replies, user_id="daily-user", birth=BIRTH):
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
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def planned(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


def purposes(events) -> list[str]:
    return [e["purpose"] for e in events if e["event"] == "model_response"]


async def test_a_day_takes_one_writing_call(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert planned(events) == ["start_reading", "daily_fortune", "submit_reading"]
    ((messages, tools),) = composer.seen
    assert tools == [] and "daily:" not in str(messages)
    sheet = messages[1]["content"]
    assert "日期：2026-10-30（Asia/Shanghai）" in sheet and "本命日主：丁" in sheet
    labels = {label for _, label, _ in facts_in(messages)}
    assert {"流日", "流日与本命", "当天的相位", "每日一牌", "流日五行"} <= labels
    # The day's facts reach the reader rendered from the calculation.
    card = runtime.session.state["daily_result"]["card"]
    side = "逆位" if card["reversed"] else "正位"
    assert "流日丁丑（十神比肩）" in outcome.text and f"【{card['name']}】{side}" in outcome.text
    assert outcome.data["reading"]["question_type"] == "daily"


async def test_tomorrow_is_the_next_day(make):
    runtime, _, events = make(written)
    outcome = await runtime.turn("明天运势如何？")
    assert outcome.status == "submit_reading"
    assert runtime.session.state["daily_result"]["date"] == "2026-10-31"


async def test_a_wrong_ten_god_is_caught_before_submission(make):
    """P0.2's missed mutation (流日十神写错) is caught on the pipeline's path."""
    runtime, _, events = make(wrong_ten_god, written)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert info["problems"][0] == ["当天流日的十神是比肩、伤官，正文写成了七杀"]
    assert planned(events).count("submit_reading") == 1


async def test_two_broken_drafts_degrade_to_the_days_facts(make):
    runtime, *_ = make(broken, broken)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    sections = outcome.data["reading"]["sections"]
    assert 0 < len(sections) <= 6
    assert sections[0]["title"] == "流日" and "流日丁丑（十神比肩）" in sections[0]["body"]
    assert not any("conjunction" in s["body"] for s in sections)


async def test_a_high_risk_day_with_medication_advice_twice_ends_in_the_safety_reply(make):
    advice = lambda m: written(m, extra="不舒服可以直接停药。")  # noqa: E731
    runtime, *_ = make(advice, advice)
    outcome = await runtime.turn("今天运势怎么样？身体有点不舒服，要不要停药？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == "safety"
    assert outcome.data["reading"]["sections"] == []
    assert outcome.data["reading"]["safety"]["flag"] is True


async def test_the_web_birth_note_is_not_part_of_the_question(make):
    runtime, *_ = make(written)
    runtime.session.state["selected_systems"] = ["daily"]
    message = (
        TODAY
        + "\n\n我在出生信息表中填写的资料：我的出生日期是公历 1996-05-10 08:30（出生时间确定）。"
    )
    outcome = await runtime.turn(message)
    assert outcome.status == "submit_reading"
    assert runtime.session.state["question"] == TODAY


@pytest.mark.parametrize(
    ("birth", "message"),
    [
        # No birth data: the agent loop asks and saves it.
        (None, TODAY),
        ({**BIRTH, "lat": None, "lon": None}, TODAY),
        # An overseas birth whose true solar time is not settled.
        ({**BIRTH, "tz": "America/New_York", "lat": 40.7, "lon": -74.0}, TODAY),
        # A consultation timezone stated in the message.
        (BIRTH, "按纽约时间，今天运势怎么样？"),
        # A range longer than a day.
        (BIRTH, "这周运势怎么样？"),
        # Another system named outside the daily page.
        (BIRTH, "用塔罗看看今天运势"),
        # A date that does not exist.
        (BIRTH, "2月30日的运势怎么样？"),
        # Not a daily question at all.
        (BIRTH, "今天天气不错"),
    ],
)
async def test_questions_the_daily_pipeline_leaves_to_the_agent_loop(make, birth, message):
    runtime, *_ = make(birth=birth)
    assert Daily(runtime).detect(runtime, message) is None


async def test_the_daily_page_routes_here_and_follow_ups_stay_with_the_agent_loop(make):
    runtime, *_ = make(written)
    runtime.session.state["selected_systems"] = ["daily"]
    daily = Daily(runtime)
    assert daily.detect(runtime, "帮我看看").kind == "new"
    assert (await runtime.turn(TODAY)).status == "submit_reading"
    assert daily.detect(runtime, "刚才那段解读里的比肩是什么意思？") is None
    assert daily.detect(runtime, "比肩是什么意思？") is None
    assert daily.detect(runtime, "明天运势呢？").kind == "new"


@pytest.mark.parametrize(
    "message",
    [
        "我的出生日期更正为1990年3月15日14:20，今天运势怎么样？",
        "我之前填的出生时间不准确，实际上我不知道出生时间。今天运势怎么样？",
    ],
)
async def test_birth_corrections_stay_with_the_agent_loop(make, message):
    runtime, *_ = make()
    assert Daily(runtime).detect(runtime, message) is None


@pytest.mark.parametrize(
    "message",
    [
        "今天和明天的运势分别怎么样？",
        "10月30日到11月2日的运势怎么样？",
        "今天运势怎么样？之后每天都要留意什么？",
    ],
)
async def test_multi_day_requests_stay_with_the_agent_loop(make, message):
    runtime, *_ = make()
    assert Daily(runtime).detect(runtime, message) is None


async def test_an_iana_consultation_timezone_stays_with_the_agent_loop(make):
    runtime, *_ = make()
    assert Daily(runtime).detect(runtime, "咨询使用America/New_York，今天运势怎么样？") is None


@pytest.mark.parametrize(
    ("claim", "problem"),
    [
        ("今天流日天干五行属水，传统幸运色是黑色。", "当天流日五行是火，正文写成了水"),
        ("你的本命日主是甲木。", "本命日主是丁，正文写成了甲"),
        ("这是2026年11月2日的运势解读。", "当天日期是2026-10-30，正文写成了2026-11-02"),
    ],
)
async def test_daily_fact_claims_are_repaired_before_submission(make, claim, problem):
    runtime, _, events = make(lambda messages: written(messages, extra=claim), written)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert info["problems"][0] == [problem]
    assert claim not in outcome.text
    assert planned(events).count("submit_reading") == 1


def with_late(messages) -> str:
    late = alias_of(messages, "流日（换日后）")
    return written(messages).replace(
        "【建议】",
        f"【分层】晚上\n晚上11点后是{{{{{late}}}}}，可以早点休息。\n【引用】{late}\n【建议】",
    )


async def test_a_day_in_the_consultation_timezone_is_dated_there(make):
    """The calendar of a New York consultation is still the 29th when Shanghai is on the 30th."""
    runtime, *_ = make(written, birth={**BIRTH, "consultation_tz": "America/New_York"})
    runtime.clock = lambda: datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    result = runtime.session.state["daily_result"]
    assert (result["date"], result["tz"]) == ("2026-10-29", "America/New_York")


async def test_the_day_pillar_change_at_eleven_pm_is_its_own_fact(make):
    runtime, composer, _ = make(with_late)
    outcome = await runtime.turn(TODAY)
    assert outcome.status == "submit_reading"
    late = [label for _, label, _ in facts_in(composer.seen[0][0]) if label == "流日（换日后）"]
    assert late and "23:00后的流日戊寅（十神伤官）" in outcome.text


async def test_daily_facts_keep_relations_in_their_local_time_segment(make):
    runtime, composer, _ = make(written)
    assert (await runtime.turn(TODAY)).status == "submit_reading"
    messages = composer.seen[0][0]
    sheet = messages[1]["content"]
    assert "仅00:00–23:00，Asia/Shanghai" in sheet
    assert "仅23:00–24:00，Asia/Shanghai" in sheet
    assert "23点换日不等于入夜" in sheet
    result = runtime.session.state["daily_result"]
    texts = Daily.texts(result)
    for item in result["interpretations"]:
        if item["kind"] != "relation" or not item["fact"].startswith("day:"):
            continue
        segment_fact, pillar, kind, where = item["fact"].rsplit(":", 3)
        segment = next(
            s for s in result["day"]["segments"] if segment_fact == f"day:{s['start_utc']}"
        )
        local = datetime.fromisoformat(segment["start_utc"]).astimezone(ZoneInfo(result["tz"]))
        rendered = texts[item["fact"]][1]
        assert f"仅{local:%H:%M}–" in rendered
        natal = result["bazi"]["pillars"].get(where)
        if natal:
            index = 0 if kind.startswith("天干") else 1
            assert f"{pillar[index]}与{natal[index]}" in rendered


def test_daily_segments_use_consultation_timezone_instead_of_utc_dates():
    result = {
        "date": "2026-11-02",
        "tz": "Asia/Shanghai",
        "day": {
            "pillar": "庚辰",
            "element": "金",
            "segments": [
                {
                    "start_utc": "2026-11-01T16:00:00+00:00",
                    "end_utc": "2026-11-02T15:00:00+00:00",
                    "pillar": "庚辰",
                    "ten_god": "正财",
                },
                {
                    "start_utc": "2026-11-02T15:00:00+00:00",
                    "end_utc": "2026-11-02T16:00:00+00:00",
                    "pillar": "辛巳",
                    "ten_god": "偏财",
                },
            ],
        },
        "bazi": {"pillars": {"time": "甲辰"}},
        "interpretations": [
            {"kind": "relation", "fact": "day:2026-11-01T16:00:00+00:00:庚辰:自刑:time"}
        ],
        "card": {
            "card_id": "the_lovers",
            "meaning_key": "the_lovers:upright",
            "name": "恋人",
            "reversed": False,
        },
    }
    texts = Daily.texts(result)
    assert "地支辰与辰" in texts[result["interpretations"][0]["fact"]][1]
    assert "仅00:00–23:00，Asia/Shanghai" in texts[result["interpretations"][0]["fact"]][1]
    assert "仅23:00–24:00，Asia/Shanghai" in texts["day:2026-11-02T15:00:00+00:00:辛巳:偏财"][1]


# ---- P2 r7: the owner permits explicit denials of 稳赚 ----------------------------------

INVESTMENT = "今天运势怎么样？适合把积蓄拿去买股票吗？"


async def test_the_writer_is_told_the_approved_gain_denial_is_allowed(make):
    """r6 daily_investment_risk#2 wrote “别把配合当稳赚” and was repaired once."""
    runtime, composer, _ = make(written)
    await runtime.turn(INVESTMENT)
    system = composer.seen[0][0][0]["content"]
    assert "别把配合当稳赚" in system and "明确否定" in system and "不保证收益" in system


@pytest.mark.parametrize(
    "claim",
    ["这笔投资稳赚。", "别把配合当稳赚，但这笔投资稳赚。", "不得不把配合当稳赚。"],
)
async def test_affirmative_gain_claims_are_still_refused(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 1)
    assert "确定性" in info["problems"][0][0]
    assert claim not in outcome.text


async def test_the_r6_gain_denial_no_longer_needs_repair_or_counts_as_unsafe(make):
    claim = "有联结也有牵绊，别把配合当稳赚。"
    runtime, _, events = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert not any(e["event"] == "pipeline_stage" and e.get("stage") == "safety" for e in events)
    assert claim in outcome.text


# ---- P2 r7: the approved denial written with a modified or quoted object ------------------


@pytest.mark.parametrize(
    "claim",
    [
        "别把一时的配合顺畅当成稳赚，亏损的可能需要提前想清楚。",
        "别把顺手当稳赚。",
        "别把“配合顺”误解为“稳赚”。",
    ],
)
async def test_the_r7_gain_denials_pass_without_repair_or_safety_reply(make, claim):
    runtime, _, events = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert claim in outcome.text


@pytest.mark.parametrize("claim", ["别把顺手当成稳赚的反面。", "不得不把一时的配合顺畅当成稳赚。"])
async def test_what_the_r7_gain_widening_must_still_refuse(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 1)
    assert "确定性" in info["problems"][0][0]
    assert claim not in outcome.text


# ---- P2 r7 review: a hand-written aspect must be one of the day's -------------------------

TOMORROW = "明天运势怎么样？"


@pytest.mark.parametrize(
    "claim",
    [
        # The day's own events (2026-10-31 for BIRTH): Moon–Jupiter opposition, Mercury–
        # Jupiter sextile.
        "月亮与本命木星的对分相让你容易想得多。",
        "行运水星与本命木星六分相，沟通可以顺一点。",
    ],
)
async def test_a_hand_written_aspect_of_the_day_is_accepted(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(TOMORROW)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert claim in outcome.text


@pytest.mark.parametrize(
    "claim",
    [
        # Existing aspect vocabulary includes aliases and permits either body order.
        "行运月亮对冲本命木星，容易想得多。",
        "本命木星与行运月亮对冲，容易想得多。",
        "行运的水星与本命的木星六合，沟通可以顺一点。",
    ],
)
async def test_a_hand_written_daily_aspect_alias_matching_the_day_is_accepted(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(TOMORROW)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert claim in outcome.text


@pytest.mark.parametrize(
    "claim, problem",
    [
        # r7 tomorrow_work#3's form with aspects that are not this day's.
        ("月亮与本命火星、金星的三分相让行动顺手。", "当天没有月亮与本命火星的三分相"),
        ("月亮与本命冥王星的对分相让你紧张。", "当天没有月亮与本命冥王星的对分相"),
        # One body of a list that is not the day's is enough.
        ("月亮与本命太阳、木星的六分相。", "当天没有月亮与本命木星的六分相"),
        # The right bodies with another aspect.
        ("月亮与本命木星的四分相让你紧张。", "当天没有月亮与本命木星的四分相"),
        # The same incorrect claims bypassed the canonical-only parser in r8.
        ("月亮与本命冥王星刑克让你紧张。", "当天没有月亮与本命冥王星的四分相"),
        ("月亮刑克本命冥王星让你紧张。", "当天没有月亮与本命冥王星的四分相"),
        ("本命冥王星与行运月亮对冲让你紧张。", "当天没有月亮与本命冥王星的对分相"),
    ],
)
async def test_a_hand_written_aspect_that_is_not_the_days_is_repaired(make, claim, problem):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(TOMORROW)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert any(problem in p for p in info["problems"][0]), info["problems"]
    assert claim not in outcome.text


# ---- P2 r8: denials written with an adverbial or a closing noun ---------------------------


@pytest.mark.parametrize(
    "question, claim",
    [
        (INVESTMENT, "别在情绪顺畅时把配合或行情当成稳赚。"),
        (INVESTMENT, "别因为情绪顺畅就把配合或行情当作稳赚。"),
        (TODAY, "这些只是象征性的节奏提示，不是事情必然顺利的保证。"),
        (TODAY, "先澄清优先级，别把配合当成必然有利。"),
        (TODAY, "别把“有机会”直接当成“稳赚”。"),
    ],
)
async def test_the_r8_denials_pass_without_repair(make, question, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(question)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert claim in outcome.text


@pytest.mark.parametrize(
    "question, claim",
    [
        (INVESTMENT, "别因为不想亏就把配合当成稳赚。"),
        (TODAY, "这不是事情必然顺利的保证吗？"),
    ],
)
async def test_what_the_r8_denial_fixes_must_still_refuse(make, question, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(question)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 1)
    assert claim not in outcome.text


@pytest.mark.parametrize(
    "claim",
    ["别把市场反应当成稳赚。", "别把想象中的收益当成稳赚。"],
)
async def test_a_safe_reminder_does_not_need_repair_or_degrade(make, claim):
    draft = lambda m: written(m, extra=claim)  # noqa: E731
    runtime, composer, _ = make(draft, draft)
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert len(composer.seen) == 1
    assert claim in outcome.text


@pytest.mark.parametrize(
    "claim",
    [
        "不能说这不是事情必然顺利的保证。",
        "不能认为这不是行情必然上涨的证明。",
        "别把配合当成必然有利的反面。",
        "不要把配合当成必然成功以外的结果。",
    ],
)
async def test_a_nested_or_reversed_denial_is_repaired_before_submission(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(INVESTMENT)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert claim not in outcome.text
