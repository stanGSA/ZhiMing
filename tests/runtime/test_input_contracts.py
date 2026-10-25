"""Regression contracts from PR #1; malicious inputs must remain rejected."""

from types import SimpleNamespace as NS

import pytest

from app import create_runtime
from common.schemas import Reading
from common.validation import validate_reading
from harness.guard import Guard
from harness.models import ToolCall
from plugins.context import BirthInput, birth_provenance, range_provenance


def test_new_reading_range_scope():
    from harness.session import Session

    s = Session("synthetic", calendar_anchor="2026-10-13")
    s.append_user("2025-11-01至2025-11-30")
    s.start_reading("旧问题")
    s.append_user("下个月求职")
    s.start_reading("下个月求职")
    assert range_provenance(NS(start="2026-11-01", end="2026-11-30"), s) is None
    assert range_provenance(NS(start="2025-11-01", end="2025-11-30"), s)


def test_inclusive_dates_equal_half_open_clock_range():
    from common.time_utils import NeedsInput, date_range

    s = session("咨询2026-11-01至2026-11-30，America/New_York")
    args = NS(
        start="2026-11-01T00:00:00-04:00", end="2026-12-01T00:00:00-05:00", tz="America/New_York"
    )
    assert range_provenance(args, s) is None
    assert date_range(args.start, args.end, args.tz) == date_range(
        "2026-11-01", "2026-11-30", args.tz
    )
    with pytest.raises(NeedsInput):
        date_range("2026-11-01T00:00:00-05:00", args.end, args.tz)


def test_country_city_compound_query():
    from common.location import Gazetteer, LocationInput

    gazetteer = Gazetteer()
    result = gazetteer.resolve(LocationInput(query="美国纽约市"))
    assert result["location"]["location_id"] == "5128581"
    assert gazetteer.resolve(LocationInput(query="美国北京"))["status"] == "needs_input"


def test_gender_evidence_does_not_confuse_female_with_male():
    from common.input_evidence import gender_evidence

    assert gender_evidence("female") == {"female"}
    assert not gender_evidence("我不是男性")


def test_birth_month_is_not_a_timing_request():
    from common.facts import validate_calculation_facts

    reading = NS(question_type="trait", systems_used=["astro"])
    state = dict(question="1993年8月17日出生，用占星看工作方式", signals=[])
    assert validate_calculation_facts(reading, state) is None


def test_profile_datetime_equivalence_without_new_evidence():
    s = session("使用已有出生资料")
    s.profile["birth_local_dt"] = "1993-08-17 23:20"
    assert birth_provenance(BirthInput(birth_local="1993-08-17T23:20:00"), s) is None
    assert birth_provenance(BirthInput(birth_local="1993-08-17T22:20:00"), s)


@pytest.mark.asyncio
async def test_chinese_clock_profile_evidence(runtime):
    runtime.session.append_user("晚上11点20分出生")
    assert (
        await invoke(
            runtime, "update_profile", field="time_known", value=True, evidence="晚上11点20分"
        )
    ).ok


@pytest.mark.asyncio
async def test_profile_calendar_conventions_and_synthetic_tag(runtime):
    runtime.session.append_user("合成资料，公历生日，按23点换日")
    for field, value, evidence in [
        ("zishi_rule", "next_day", "按23点换日"),
        ("calendar_input", "solar", "公历"),
    ]:
        assert (
            await invoke(runtime, "update_profile", field=field, value=value, evidence=evidence)
        ).code == "invalid_arguments"
    assert (
        await invoke(
            runtime,
            "update_profile",
            field="prefs_json",
            value={"birth_data_is_synthetic": True},
            evidence="合成资料",
        )
    ).ok


def test_bazi_dayun_date_is_not_a_transit_date():
    from plugins.astro.validation import validate_output

    reading = Reading.model_validate(
        dict(
            question_type="timing",
            systems_used=["bazi", "astro"],
            summary="有条件适合尝试",
            evidence=[dict(ref_id="dayun", reading="1996-12-27起运，时机应结合流月和行运。")],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )
    assert validate_output(reading, {}) is None


def test_prefixed_natal_positions_and_multiple_timeline_events():
    from plugins.astro.validation import validate_output

    events = [
        dict(
            transit_body=a,
            natal_body=b,
            aspect=aspect,
            exact_utc=f"2026-11-{day}T10:00:00+00:00",
            exact_date=f"2026-11-{day}",
            orb_deg=0.0,
            allowed_orb_deg=1.0,
        )
        for a, b, aspect, day in [
            ("Jupiter", "Sun", "conjunction", "04"),
            ("Sun", "Mercury", "square", "05"),
        ]
    ]
    state = dict(
        natal_result=dict(
            time_known=True,
            planets=[
                dict(body_zh="太阳", sign_zh="狮子", house=4),
                dict(body_zh="水星", sign_zh="狮子", house=4),
            ],
        ),
        transit_result=dict(
            events=events,
            interpretations=[
                dict(
                    ref_id="jupiter",
                    fact="transit:2026-11-04T10:00:00+00:00:Jupiter:Sun:conjunction",
                )
            ],
        ),
    )
    reading = Reading.model_validate(
        dict(
            question_type="timing",
            systems_used=["astro"],
            summary="有条件适合尝试",
            evidence=[dict(ref_id="jupiter", reading="11月4日行运木星合本命狮子座第4宫太阳。")],
            timeline=[
                dict(
                    period="2026-11-01至2026-11-10",
                    note="11月4日木星合太阳，11月5日太阳刑水星，可检查准备。",
                )
            ],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )
    assert validate_output(reading, state) is None
    reading.evidence[0].reading = reading.evidence[0].reading.replace("第4宫", "第9宫")
    assert validate_output(reading, state)
    reading.evidence[0].reading = reading.evidence[0].reading.replace("第9宫", "第4宫")
    reading.timeline[0].note = reading.timeline[0].note.replace("11月5日", "11月6日")
    assert validate_output(reading, state)


@pytest.mark.asyncio
async def test_adapter_marks_invalid_json_and_missing_usage(monkeypatch):
    from harness.llm import OpenAIModel

    async def respond(**kwargs):
        return NS(
            model="synthetic",
            usage=None,
            choices=[
                NS(
                    finish_reason="tool_calls",
                    message=NS(
                        content=None,
                        tool_calls=[NS(id="bad", function=NS(name="get_profile", arguments="{"))],
                    ),
                )
            ],
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-placeholder")
    adapter = OpenAIModel("synthetic")
    monkeypatch.setattr(adapter.client.chat.completions, "create", respond)
    try:
        result = await adapter.chat([], [])
    finally:
        await adapter.close()
    assert result.tool_calls[0].argument_error
    assert result.usage_available is False


@pytest.mark.parametrize(
    "text",
    [
        "2026-11-11行运土星拱本命太阳",
        "2026年11月11日行运土星拱本命太阳",
        "2026-11-10行运土星刑本命太阳",
        "2026-11-10行运土星拱本命月亮",
        "2026-11-10行运土星拱本命太阳，容许度7度",
    ],
)
def test_transit_entity_mismatch(text):
    from plugins.astro.validation import validate_output

    event = dict(
        transit_body="Saturn",
        natal_body="Sun",
        aspect="trine",
        exact_utc="2026-11-10T10:00:00+00:00",
        exact_date="2026-11-10",
        orb_deg=0.0,
        allowed_orb_deg=1.0,
    )
    fact = "transit:2026-11-10T10:00:00+00:00:Saturn:Sun:trine"
    state = dict(
        transit_result=dict(events=[event], interpretations=[dict(ref_id="event", fact=fact)])
    )
    reading = Reading.model_validate(
        dict(
            question_type="timing",
            systems_used=["astro"],
            summary="有条件适合尝试",
            evidence=[dict(ref_id="event", reading=text)],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )
    assert validate_output(reading, state)
    reading.evidence[0].reading = "2026年11月10日行运土星拱本命太阳，容许度1度"
    assert validate_output(reading, state) is None


def test_signal_legacy_compatibility_and_enum():
    from pydantic import ValidationError

    from plugins.base import Signal

    base = dict(
        ref_id="x",
        system="astro",
        theme="career",
        valence=0,
        strength=0.5,
        kb_ref="k",
        rule_version=1,
        reviewed=False,
    )
    assert Signal(**base, horizon="long_term").horizon == "trait"
    assert Signal(**base, horizon="short_term").horizon == "timing"
    with pytest.raises(ValidationError):
        Signal(**base, horizon="invented")


def test_ephemeris_never_changes_cwd(monkeypatch):
    import os

    from plugins.astro.calculator import natal_chart

    def forbidden(*args):
        raise AssertionError("process cwd must never change")

    monkeypatch.setattr(os, "chdir", forbidden)
    monkeypatch.setattr(os.path, "relpath", forbidden)
    assert natal_chart("1993-08-17 23:20", "Asia/Shanghai", 39.9075, 116.39723)["planets"]


@pytest.mark.asyncio
async def test_overseas_clock_and_period_timezone_need_confirmation(runtime):
    runtime.session.append_user("男性，1995-12-31 23:45，美国纽约市出生")
    await invoke(runtime, "start_reading", question="日主及求职安排")
    loc = await invoke(runtime, "resolve_location", query="纽约市")
    birth = dict(birth_local="1995-12-31 23:45", location_id=loc.data["location"]["location_id"])
    result = await invoke(runtime, "compute_bazi", **birth)
    assert result.data["code"] == "confirm_bazi_clock"
    runtime.session.append_user("使用真太阳时")
    result = await invoke(runtime, "compute_bazi", **birth, true_solar_time=True)
    assert result.ok and result.data.get("bazi_id")
    chart = await invoke(runtime, "compute_natal_chart", **birth)
    args = dict(
        chart_id=chart.data["chart_id"], start="2026-11-01", end="2026-11-02", bodies=["Saturn"]
    )
    missing = await invoke(runtime, "compute_transits", **args)
    assert missing.data["code"] == "confirm_period_timezone"
    forged = await invoke(runtime, "compute_transits", **args, tz="Asia/Shanghai")
    assert forged.data["code"] == "confirm_period_timezone"
    runtime.session.append_user("咨询时区America/New_York")
    result = await invoke(runtime, "compute_transits", **args, tz="America/New_York")
    assert result.ok and result.data["tz"] == "America/New_York"


@pytest.mark.asyncio
async def test_usage_missing_stops_before_tools(project, scripted_model):
    from harness.models import ModelResponse

    model = scripted_model(
        [
            ModelResponse(
                usage_available=False,
                tool_calls=[ToolCall(id="x", name="start_reading", arguments={"question": "test"})],
            )
        ]
    )
    runtime = create_runtime(project, provider="demo", model=model)
    try:
        result = await runtime.turn("test")
        assert result.status == "usage_unavailable"
        assert not runtime.session.state.get("active_reading_id")
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_malformed_tool_json_can_recover(project, scripted_model):
    from harness.models import ModelResponse

    model = scripted_model(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(id="bad", name="get_profile", raw_arguments="{", argument_error=True)
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(id="ok", name="ask_user", arguments=dict(question="请提供出生资料"))
                ]
            ),
        ]
    )
    runtime = create_runtime(project, provider="demo", model=model)
    try:
        result = await runtime.turn("排盘")
        assert result.status == "ask_user"
        feedback = [m for m in model.seen_messages[-1] if m["role"] == "tool"]
        assert "invalid_arguments" in feedback[0]["content"]
    finally:
        runtime.close()


async def invoke(runtime, name, **arguments):
    args, result, _ = Guard(runtime.registry).check(
        ToolCall(id="regression", name=name, arguments=arguments), runtime.session
    )
    return result if result is not None else await runtime.registry.run(name, args, runtime.session)


def session(text):
    return NS(user_messages=[text], profile={}, state={})


@pytest.mark.parametrize("text", ["1993年8月17日23:20出生", "1993年8月17日晚上11点20分出生"])
def test_chinese_birth(text):
    assert birth_provenance(BirthInput(birth_local="1993-08-17 23:20"), session(text)) is None
    assert birth_provenance(BirthInput(birth_local="1993-08-17 22:20"), session(text))


def test_range_ignores_birth_and_checks_chinese_month():
    args = NS(start="2026-11-01", end="2026-11-30")
    assert range_provenance(args, session("看2026-11-01至2026-11-30，我1993-08-17出生")) is None
    assert range_provenance(args, session("看2026年12月求职"))


@pytest.mark.asyncio
async def test_profile_normalization_cross_session(project):
    runtime = create_runtime(project, user_id="synthetic-normalization", provider="demo")
    try:
        runtime.session.append_user("我是男性，1993年8月17日晚上11点20分出生，出生地北京。")
        for field, value, evidence in [
            ("gender", "male", "我是男性"),
            ("birth_local_dt", "1993-08-17 23:20", "1993年8月17日晚上11点20分"),
            ("birth_place", "北京", "出生地北京"),
        ]:
            assert (
                await invoke(runtime, "update_profile", field=field, value=value, evidence=evidence)
            ).ok
    finally:
        runtime.close()
    later = create_runtime(project, user_id="synthetic-normalization", provider="demo")
    try:
        later.session.append_user("根据我保存的资料排八字")
        await invoke(later, "start_reading", question="排八字")
        loc = await invoke(later, "resolve_location", query="北京")
        result = await invoke(
            later, "compute_bazi", location_id=loc.data["location"]["location_id"]
        )
        assert result.ok and result.data.get("dayun")
    finally:
        later.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase", ["{body}{sign}、第{wrong}宫", "{body}（{sign}，第{wrong}宫）", "{body}在第九宫"]
)
async def test_wrong_house_rejected(runtime, phrase):
    runtime.session.append_user("1993-08-17 23:20，北京出生")
    await invoke(runtime, "start_reading", question="工作方式")
    loc = await invoke(runtime, "resolve_location", query="北京")
    chart = await invoke(
        runtime,
        "compute_natal_chart",
        birth_local="1993-08-17 23:20",
        location_id=loc.data["location"]["location_id"],
    )
    p = next(p for p in chart.data["planets"] if p["house"] != 9)
    signal = runtime.session.state["signals"][0]
    reading = Reading.model_validate(
        dict(
            question_type="trait",
            systems_used=["astro"],
            summary=phrase.format(body=p["body_zh"], sign=p["sign_zh"], wrong=p["house"] % 12 + 1),
            evidence=[dict(ref_id=signal["ref_id"], reading="可反思工作方式")],
            advice=[],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )
    assert validate_reading(reading, runtime.session)
