"""Screenshot review regressions: clarification must change the computation, not its truth."""

from types import SimpleNamespace as NS

import pytest

from common.input_evidence import clock_in, question_range, solar_time_choice
from common.location import Gazetteer, LocationInput
from common.schemas import Reading
from harness.guard import Guard
from harness.models import ModelResponse, ToolCall
from plugins.astro.validation import aspect_assertions, validate_output
from plugins.context import period_timezone


async def invoke(runtime, name, **arguments):
    args, result, _ = Guard(runtime.registry).check(
        ToolCall(id="probe", name=name, arguments=arguments), runtime.session
    )
    return result if result is not None else await runtime.registry.run(name, args, runtime.session)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("下午3点一刻", "15:15"),
        ("晚上12点", "00:00"),
        ("8点多", None),
        ("大约8点", None),
        ("八点左右", None),
        ("下午三点三刻", "15:45"),
        ("晚上11点20分", "23:20"),
        ("中午12点", "12:00"),
        ("15:01", "15:01"),
    ],
)
def test_clock_precision(text, expected):
    assert clock_in(text) == expected


@pytest.mark.parametrize(
    "anchor,expected",
    [("2026-10-13", ("2026-12-01", "2026-12-31")), ("2026-12-13", ("2027-02-01", "2027-02-28"))],
)
def test_month_after_next(anchor, expected):
    assert question_range("那下下个月呢？", anchor) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("不按真太阳时", False),
        ("不要用真太阳时", False),
        ("按真太阳时，日主是什么？", True),
        ("不用真太阳时还是使用真太阳时？", None),
        ("不是不用真太阳时", None),
    ],
)
def test_clock_convention_negation(text, expected):
    assert solar_time_choice(text) is expected


@pytest.mark.parametrize("admin", ["湖南", "湖南省"])
@pytest.mark.parametrize("country", ["CN", None])
def test_changsha_province(admin, country):
    result = Gazetteer().resolve(LocationInput(query="长沙", country=country, admin1=admin))
    assert result["status"] == "resolved"
    assert result["location"]["admin1"] == "11"


def reading(text):
    return Reading.model_validate(
        dict(
            question_type="trait",
            systems_used=["astro"],
            summary=text,
            evidence=[dict(ref_id="fixture", reading="仅检查表达是否声称计算事实")],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )


@pytest.mark.parametrize("text", ["事业处于上升期", "收入有上升空间", "金星与火星冲突"])
def test_ordinary_words_are_not_axis_or_aspect_claims(text):
    assert validate_output(reading(text), dict(natal_result=dict(time_known=False))) is None


@pytest.mark.parametrize(
    "text", ["上升在白羊座", "上升点代表外在表达", "太阳在第九宫", "金星与火星对冲"]
)
def test_actual_unavailable_facts_still_rejected(text):
    assert validate_output(reading(text), dict(natal_result=dict(time_known=False)))


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "木星合太阳与水星刑水星",
            [("Jupiter", "Sun", "conjunction"), ("Mercury", "Mercury", "square")],
        ),
        ("太阳与水星刑土星", [("Sun", "Saturn", "square"), ("Mercury", "Saturn", "square")]),
        ("太阳与水星形成对冲", [("Sun", "Mercury", "opposition")]),
    ],
)
def test_independent_aspects_do_not_overlap(text, expected):
    assert [item[1:] for item in aspect_assertions(text)] == expected


async def la_birth(runtime):
    runtime.session.append_user("公历1990-06-15 17:00在美国洛杉矶出生，时间准确，男性")
    await invoke(runtime, "start_reading", question="八字日主")
    loc = await invoke(runtime, "resolve_location", query="洛杉矶")
    return dict(birth_local="1990-06-15 17:00", location_id=loc.data["location"]["location_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,wrong", [("不用真太阳时，按固定UTC+8", True), ("使用真太阳时", False)]
)
async def test_overseas_choice_matches_effective_parameter(runtime, reply, wrong):
    birth = await la_birth(runtime)
    runtime.session.append_user(reply)
    bad = await invoke(runtime, "compute_bazi", **birth, true_solar_time=wrong)
    assert not bad.data.get("bazi_id")
    good = await invoke(runtime, "compute_bazi", **birth, true_solar_time=not wrong)
    assert good.ok and good.data.get("bazi_id")
    assert good.data["input"]["true_solar_time"] is not wrong


@pytest.mark.asyncio
async def test_solar_choice_profile_and_current_override(runtime):
    birth = await la_birth(runtime)
    runtime.session.append_user("按真太阳时")
    saved = await invoke(
        runtime, "update_profile", field="true_solar_time", value=True, evidence="按真太阳时"
    )
    assert saved.ok
    runtime.session.append_user("这次不用真太阳时，按固定UTC+8")
    result = await invoke(runtime, "compute_bazi", **birth)
    assert result.ok and result.data["input"]["true_solar_time"] is False
    assert not (
        await invoke(
            runtime, "update_profile", field="true_solar_time", value=True, evidence="真太阳时"
        )
    ).ok


@pytest.mark.asyncio
async def test_needs_input_not_replayed_after_answer(runtime, scripted_model):
    birth = await la_birth(runtime)

    def response(name, **args):
        return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=args)])

    runtime.model = scripted_model(
        [
            response("compute_bazi", **birth),
            response("ask_user", question="按真太阳时还是固定UTC+8？"),
            response("compute_bazi", **birth),
            response("ask_user", question="还需要了解什么？"),
        ]
    )
    await runtime.turn("请排盘")
    assert not any(r.data.get("status") == "needs_input" for r in runtime.session.cache.values())
    await runtime.turn("不用真太阳时，按固定UTC+8")
    assert runtime.session.state.get("bazi_id")
    # Completed computations must still be reusable.
    result = await invoke(runtime, "compute_bazi", **birth)
    assert result.cached
    bad = await invoke(runtime, "compute_bazi", **birth, true_solar_time=True)
    assert not bad.ok and not bad.data.get("bazi_id")
    runtime.session.append_user("更正，这次使用真太阳时")
    changed = await invoke(runtime, "compute_bazi", **birth)
    assert changed.data["input"]["true_solar_time"] is True
    assert changed.data["pillars"]["day"] != result.data["pillars"]["day"]


@pytest.mark.asyncio
async def test_period_clarification_same_arguments(runtime, scripted_model):
    birth = await la_birth(runtime)
    runtime.session.append_user("不用真太阳时")
    chart = await invoke(runtime, "compute_bazi", **birth)
    args = dict(bazi_id=chart.data["bazi_id"], start="2026-11-01", end="2026-11-02")

    def response(name, **data):
        return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=data)])

    runtime.model = scripted_model(
        [
            response("compute_bazi_period", **args),
            response("ask_user", question="咨询按哪个城市时间？"),
            response("compute_bazi_period", **args),
            response("ask_user", question="还需要了解什么？"),
        ]
    )
    await runtime.turn("计算11月1日至2日")
    assert not any(r.data.get("status") == "needs_input" for r in runtime.session.cache.values())
    await runtime.turn("按洛杉矶时间")
    assert runtime.session.state["bazi_period_result"]["tz"] == "America/Los_Angeles"


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", ["我现在住在洛杉矶", "按洛杉矶时间"])
async def test_natural_consultation_timezone_and_profile(runtime, phrase):
    await la_birth(runtime)
    runtime.session.append_user(phrase)
    args = NS(tz="America/Los_Angeles")
    chart = dict(input=dict(tz="America/New_York"))
    assert period_timezone(args, runtime.session, chart) == args.tz
    saved = await invoke(
        runtime, "update_profile", field="consultation_tz", value=args.tz, evidence=phrase
    )
    assert saved.ok
    assert runtime.session.profile["consultation_tz"] == args.tz
    bad = await invoke(
        runtime,
        "update_profile",
        field="consultation_tz",
        value="America/New_York",
        evidence=phrase,
    )
    assert not bad.ok


@pytest.mark.asyncio
async def test_birthplace_alone_does_not_confirm_consultation_timezone(runtime):
    from common.time_utils import NeedsInput

    await la_birth(runtime)
    with pytest.raises(NeedsInput):
        period_timezone(
            NS(tz="America/Los_Angeles"),
            runtime.session,
            dict(input=dict(tz="America/Los_Angeles")),
        )
    assert not (
        await invoke(
            runtime,
            "update_profile",
            field="consultation_tz",
            value="America/Los_Angeles",
            evidence="洛杉矶出生",
        )
    ).ok


@pytest.mark.asyncio
async def test_negated_timezone_evidence_cannot_be_trimmed(runtime):
    from common.time_utils import NeedsInput

    await la_birth(runtime)
    runtime.session.append_user("不要按洛杉矶时间")
    with pytest.raises(NeedsInput):
        period_timezone(
            NS(tz="America/Los_Angeles"),
            runtime.session,
            dict(input=dict(tz="America/Los_Angeles")),
        )
    saved = await invoke(
        runtime,
        "update_profile",
        field="consultation_tz",
        value="America/Los_Angeles",
        evidence="按洛杉矶时间",
    )
    assert not saved.ok


@pytest.mark.asyncio
async def test_province_reply_can_select_candidate(runtime):
    runtime.session.append_user("出生在长沙")
    await invoke(runtime, "start_reading", question="工作")
    first = await invoke(runtime, "resolve_location", query="长沙")
    assert first.data["status"] == "needs_input"
    runtime.session.append_user("湖南省")
    final = await invoke(runtime, "resolve_location", query="长沙", admin1="湖南")
    assert final.data["location"]["location_id"] == "1815577"
    forged = await invoke(runtime, "resolve_location", query="长沙", admin1="广东")
    assert not forged.ok


@pytest.mark.asyncio
async def test_timezone_inferred_and_reused_in_new_session(runtime, project):
    from app import create_runtime

    await la_birth(runtime)
    runtime.session.append_user("按洛杉矶时间")
    chart = dict(input=dict(tz="America/New_York"))
    assert period_timezone(NS(tz=None), runtime.session, chart) == "America/Los_Angeles"
    saved = await invoke(
        runtime,
        "update_profile",
        field="consultation_tz",
        value="America/Los_Angeles",
        evidence="按洛杉矶时间",
    )
    assert saved.ok
    later = create_runtime(project, user_id=runtime.session.user_id, provider="demo")
    try:
        later.session.append_user("看本月")
        assert period_timezone(NS(tz=None), later.session, chart) == "America/Los_Angeles"
    finally:
        later.close()
