"""Birth data typed into the question, bound by code for astro and bazi (plan P3.1)."""

import pytest

from pipeline import birth
from pipeline.runner import PipelineRunner
from tests.pipeline import test_runner_bazi as bazi_runs
from tests.pipeline.test_runner_astro import make, planned, written  # noqa: F401

TYPED = "我1990年3月5日早上8点出生在杭州，看看星盘性格"


# ---- reading the message -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, day, clock",
    [
        ("我1990年3月5日早上8点出生在杭州，看看八字", "1990-03-05", "08:00"),
        ("出生于1993-08-17 23:20，北京", "1993-08-17", "23:20"),
        ("我在杭州出生，生日是1990年3月5日", "1990-03-05", None),
    ],
)
def test_a_typed_birth_is_read(text, day, clock):
    found = birth.typed(text)
    assert (found.day, found.clock) == (day, clock)


@pytest.mark.parametrize(
    "text",
    [
        "我是1990年3月出生的，看看八字",  # no full date
        "看看2027年3月5日的运势",  # not a birth
        "我1990年3月5日出生，我妹妹1992年4月1日出生",  # two births
    ],
)
def test_no_typed_birth(text):
    assert birth.typed(text) is None


@pytest.mark.parametrize(
    "text, places",
    [
        ("我1990年3月5日早上8点出生在杭州，看看八字", ["杭州"]),
        ("我在杭州出生，1990年3月5日早上8点", ["杭州"]),
        ("出生于1993-08-17 23:20，北京", ["北京"]),
        ("我1990年3月5日出生在杭州市西湖区", ["杭州市西湖区"]),
        ("出生地：伦敦", ["伦敦"]),
        # Where the user lives is not where they were born.
        ("我1990年3月5日出生，现在住在上海", []),
        ("我1990年3月5日在医院出生", []),
    ],
)
def test_birth_places_are_read(text, places):
    assert birth.places(text) == places


def test_place_wordings_tried():
    assert birth.variants("杭州市西湖区") == ["杭州市西湖区", "杭州市"]
    assert birth.variants("浙江杭州") == ["浙江杭州", "杭州"]
    assert birth.variants("中国杭州") == ["中国杭州", "杭州"]


@pytest.mark.parametrize(
    "text, kept, removed",
    [
        ("我1990年3月5日早上8点出生，看看下个月", "下个月", "1990"),
        ("1990-03-05 08:30出生的我，2027年3月怎么样", "2027年3月", "1990"),
        # A date not tied to a birth is kept.
        ("看看2027年3月5日", "2027年3月5日", None),
    ],
)
def test_birth_dates_are_removed_before_a_range_is_read(text, kept, removed):
    cleaned = birth.without_birth(text)
    assert kept in cleaned
    if removed:
        assert removed not in cleaned


def test_an_answer_narrows_the_candidates_with_the_users_words():
    candidates = [
        {"name": "London", "country": "GB", "admin1": "ENG"},
        {"name": "London", "country": "CA", "admin1": "08"},
    ]
    assert birth.narrowing("英国那个", candidates) == {"country": "英国"}
    assert birth.narrowing("加拿大", candidates) == {"country": "加拿大"}
    assert birth.narrowing("不知道", candidates) == {}


# ---- astro ---------------------------------------------------------------------------------


async def test_typed_birth_is_bound_by_code(make):  # noqa: F811
    runtime, composer, events = make(written, birth=None)
    found = PipelineRunner(runtime).detect(TYPED)
    assert found is not None and found.system == "astro"
    outcome = await runtime.turn(TYPED)
    assert outcome.status == "submit_reading", outcome.text
    calls = planned(events)
    assert calls[:4] == [
        "start_reading",
        "update_profile",
        "resolve_location",
        "compute_natal_chart",
    ]
    natal = runtime.session.state["natal_result"]
    assert natal["input"]["birth_local"] == "1990-03-05 08:00"
    profile = runtime.store.get_profile(runtime.session.user_id)
    assert profile["birth_local_dt"] == "1990-03-05 08:00" and profile["birth_place"] == "杭州"


async def test_a_typed_birth_date_is_not_read_as_the_range(make):  # noqa: F811
    runtime, _, _ = make(written, birth=None)
    outcome = await runtime.turn("我1990年3月5日早上8点出生在杭州，看星盘下个月事业运怎么样？")
    assert outcome.status == "submit_reading", outcome.text
    transit = runtime.session.state["transit_result"]
    assert (transit["start"], transit["end"]) == ("2026-11-01", "2026-11-30")


@pytest.mark.parametrize(
    "message",
    [
        "我1990年3月5日早上8点出生在杭州，看看星盘性格",  # differs from the saved birth
        "看星盘，我是1990年3月出生的，看看我的性格。",  # no full date
    ],
)
async def test_corrections_and_partial_births_stay_with_the_agent_loop(make, message):  # noqa: F811
    runtime, *_ = make(written)
    assert PipelineRunner(runtime).detect(message) is None


async def test_the_web_forms_birth_is_used_alone(make):  # noqa: F811
    runtime, *_ = make(written)
    profile = runtime.session.profile
    runtime.session.birth_binding = {
        "profile": {**profile, "location_id": "1796236"},
        "location": {"name": "上海"},
    }
    assert PipelineRunner(runtime).detect(TYPED) is None


# ---- bazi ----------------------------------------------------------------------------------


@pytest.fixture
def bazi(project):
    runtimes = []
    yield bazi_runs.builder(project, runtimes)
    for runtime in runtimes:
        runtime.close()


async def test_bazi_typed_birth_with_its_gender(bazi):
    runtime, composer, events = bazi(bazi_runs.written, birth=None)
    outcome = await runtime.turn("我是女生，1996年5月10日早上8点30分出生在上海，看看八字大运")
    assert outcome.status == "submit_reading", outcome.text
    result = runtime.session.state["bazi_result"]
    assert result["input"]["birth_local"] == "1996-05-10 08:30"
    assert result["dayun"]["gender"] == "female"
    profile = runtime.store.get_profile(runtime.session.user_id)
    assert profile["gender"] == "female" and profile["birth_place"] == "上海"


async def test_bazi_typed_birth_asks_for_a_place_shared_by_several(bazi):
    runtime, composer, events = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我1993年9月5日凌晨4点35分出生在伦敦，看看八字性格")
    assert first.status == "ask_user" and "英国" in first.text and "加拿大" in first.text
    second = await runtime.turn("英国")
    assert second.status == "ask_user" and "真太阳时" in second.text  # an overseas birth
    third = await runtime.turn("不用真太阳时")
    assert third.status == "submit_reading", third.text
    natal = runtime.session.state["bazi_result"]["input"]
    assert natal["tz"] == "Europe/London" and natal["true_solar_time"] is False
    assert third.data["pipeline"]["asks"] == 2


async def test_bazi_typed_birth_without_a_place_asks_for_it(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我1990年3月5日早上8点出生，看看八字性格")
    assert first.status == "ask_user" and first.text == birth.ASK_PLACE
    second = await runtime.turn("杭州")
    assert second.status == "submit_reading", second.text


async def test_bazi_typed_birth_without_a_clock_asks_for_it(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我1990年3月5日出生在杭州，看看八字性格")
    assert first.status == "ask_user" and "出生" in first.text
    second = await runtime.turn("早上8点")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_result"]["input"]["birth_local"] == "1990-03-05 08:00"


async def test_bazi_typed_birth_with_an_unknown_time(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    outcome = await runtime.turn("我1990年3月5日出生在杭州，不知道出生时间，看看八字性格")
    assert outcome.status == "submit_reading", outcome.text
    result = runtime.session.state["bazi_result"]
    assert result["time_known"] is False and "time" not in result["pillars"]


async def test_bazi_typed_birth_in_xinjiang_asks_for_the_clock(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我1990年3月5日早上8点出生在乌鲁木齐，看看八字性格")
    assert first.status == "ask_user" and "新疆时间" in first.text
    second = await runtime.turn("北京时间")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_result"]["input"]["tz"] == "Asia/Shanghai"


# ---- a lunar birth (bazi only) ---------------------------------------------------------------


def test_a_typed_lunar_birth_is_read():
    found = birth.typed_lunar("我农历2023年二月十五早上10点出生在北京，看看八字")
    assert (found.date, found.clock, found.value) == (
        "2023年二月十五",
        "10:00",
        "2023年二月十五 10:00",
    )
    assert birth.typed_lunar("农历2023年二月十五，看看八字") is None  # no birth word
    assert birth.typed("我农历2023年二月十五早上10点出生在北京") is None  # not a solar date


async def test_bazi_lunar_birth_asks_for_the_leap_month(bazi):
    runtime, composer, events = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我农历2023年二月十五早上10点出生在北京，看看八字性格")
    assert first.status == "ask_user" and "闰月" in first.text
    second = await runtime.turn("闰二月")
    assert second.status == "submit_reading", second.text
    result = runtime.session.state["bazi_result"]
    # 闰二月十五 of 2023 is 2023-04-05 in the solar calendar.
    assert result["input"]["birth_local"].startswith("2023-04-05")
    # The solar date is not saved as if the user had written it.
    assert not runtime.store.get_profile(runtime.session.user_id).get("birth_local_dt")


async def test_bazi_lunar_birth_as_a_regular_month(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    await runtime.turn("我农历2023年二月十五早上10点出生在北京，看看八字性格")
    second = await runtime.turn("普通月，不是闰月")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_result"]["input"]["birth_local"].startswith("2023-03-06")


async def test_bazi_lunar_birth_without_a_clock(bazi):
    runtime, *_ = bazi(bazi_runs.written, birth=None)
    first = await runtime.turn("我农历2023年二月十五出生在北京，是普通月，看看八字性格")
    assert first.status == "ask_user" and "连在一起" in first.text
    second = await runtime.turn("农历2023年二月十五早上10点出生")
    assert second.status == "submit_reading", second.text


@pytest.mark.parametrize(
    "messages, value, supported",
    [
        (["农历2023年二月十五早上10点出生在北京"], "2023年二月十五 10:00", True),
        (["农历2023年二月十五 10:00，北京出生"], "2023年二月十五 10:00", True),
        # Still refused: a clock in another sentence, an approximate one, another clock,
        # another date, a clock that belongs to a later date, no clock at all.
        (["农历2023年二月十五出生。明天早上10点开会"], "2023年二月十五 10:00", False),
        (["农历2023年二月十五大约10点出生"], "2023年二月十五 10:00", False),
        (["农历2023年二月十五早上10点出生"], "2023年二月十五 11:00", False),
        (["农历2023年二月十六早上10点出生"], "2023年二月十五 10:00", False),
        (["农历2023年二月十五出生，2026年11月3日10点面试"], "2023年二月十五 10:00", False),
        (["农历2023年二月十五出生", "早上10点"], "2023年二月十五 10:00", False),
        (["农历2023年二月十五出生"], "2023年二月十五", False),
    ],
)
def test_a_lunar_clock_must_follow_the_lunar_date(messages, value, supported):
    from plugins.bazi.tools import stated_lunar

    assert stated_lunar(value, messages) is supported


async def test_the_agent_loop_keeps_the_lunar_date_rule(runtime):
    """stated_lunar applies only to the lunar date the pipeline bound; a model's call is not."""
    from tests.plugins.test_astro_bazi_integration import invoke

    runtime.session.append_user("我农历2023年二月十五早上10点出生在北京，普通月，看看八字")
    assert (await invoke(runtime, "start_reading", dict(question="我的性格"))).ok
    place = await invoke(runtime, "resolve_location", dict(query="北京"))
    arguments = dict(
        location_id=place.data["location"]["location_id"],
        calendar="lunar",
        lunar_date="2023年二月十五 10:00",
        calendar_confirmed=True,
        leap_month=False,
    )
    refused = await invoke(runtime, "compute_bazi", arguments)
    assert not refused.ok and "农历日期" in refused.error
    runtime.session.state["typed_lunar"] = "2023年二月十五 10:00"
    assert (await invoke(runtime, "compute_bazi", arguments)).ok
