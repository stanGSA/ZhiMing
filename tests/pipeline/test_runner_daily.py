"""Daily fortune through the pipeline with scripted models (P2.3 of the plan)."""

import re
from datetime import UTC, datetime

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
