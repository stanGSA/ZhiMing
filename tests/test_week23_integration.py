import copy
import sqlite3

import pytest

from app import create_runtime
from common.schemas import Reading
from common.validation import validate_reading
from harness.guard import Guard
from harness.models import ModelResponse, ToolCall
from memory.store import Store


async def invoke(runtime, name, args):
    parsed, result, key = Guard(runtime.registry).check(
        ToolCall(id="test", name=name, arguments=args), runtime.session
    )
    if result is not None:
        return result
    result = await runtime.registry.run(name, parsed, runtime.session)
    if result.ok:
        tool = runtime.registry.tools[name]
        if tool.idempotent:
            runtime.session.cache[key] = result
        if tool.exclusive_key:
            runtime.session.state[tool.exclusive_key] = True
    return result


async def prepare(runtime, time_known=True):
    runtime.session.append_user(
        "我是男，出生于1993-08-17 23:20，北京；用于合成测试。"
        if time_known
        else "出生于1993-08-17，北京，出生时间不知道，用于合成测试。"
    )
    assert (await invoke(runtime, "start_reading", dict(question="我的性格与工作方向"))).ok
    result = await invoke(runtime, "resolve_location", dict(query="北京"))
    assert result.data["status"] == "resolved"
    return dict(
        birth_local="1993-08-17 23:20" if time_known else "1993-08-17",
        location_id=result.data["location"]["location_id"],
        time_known=time_known,
    )


def draft(runtime, summary="适合先尝试需要沟通与持续学习的方向，再结合实际技能验证。"):
    state = runtime.session.state
    systems = sorted({s["system"] for s in state["signals"]})
    evidence = []
    for system in systems:
        signal = next(s for s in state["signals"] if s["system"] == system)
        evidence.append(
            dict(
                ref_id=signal["ref_id"],
                reading="该象征主题可用来反思准备、沟通与职责，需要现实条件核实。",
            )
        )
    return dict(
        question_type="trait",
        systems_used=systems,
        summary=summary,
        evidence=evidence,
        advice=["用一次实际任务检验技能。"],
        confidence=dict(level="low", reason="释义草稿未人工审核"),
        safety=dict(flag=False, note=""),
    )


@pytest.mark.asyncio
async def test_three_systems_restore_cache_ownership_forget(project):
    runtime = create_runtime(project, user_id="week23-owner", provider="demo", seed=42)
    other = create_runtime(project, user_id="week23-other", provider="demo")
    later = None
    try:
        birth = await prepare(runtime)
        natal = await invoke(runtime, "compute_natal_chart", birth)
        assert natal.ok
        bazi = await invoke(runtime, "compute_bazi", {**birth, "gender": "male"})
        assert bazi.ok
        assert (
            await invoke(
                runtime, "draw_tarot", dict(spread="three_card", question="我的性格与工作方向")
            )
        ).ok
        assert {s["system"] for s in runtime.session.state["signals"]} == {"astro", "bazi", "tarot"}
        repeated = await invoke(runtime, "compute_natal_chart", birth)
        assert repeated.cached and repeated.data["chart_id"] == natal.data["chart_id"]
        output = draft(runtime)
        submitted = await invoke(runtime, "submit_reading", output)
        assert submitted.ok
        rid = submitted.data["reading_id"]
        saved = runtime.store.get_reading(runtime.session.user_id, rid)
        assert (
            saved["chart_id"] == natal.data["chart_id"] and saved["bazi_id"] == bazi.data["bazi_id"]
        )
        assert {k for k in saved["calculations_json"]} == {"natal_result", "bazi_result"}
        assert not other.store.get_reading(other.session.user_id, rid)
        other.session.state["chart_id"] = natal.data["chart_id"]
        assert not (
            await invoke(
                other,
                "compute_transits",
                dict(chart_id=natal.data["chart_id"], start="2026-11-01", end="2026-11-02"),
            )
        ).ok
        later = create_runtime(project, user_id=runtime.session.user_id, provider="demo")
        later.session.append_user("上次的八字日主是什么意思？请读取原记录。")
        restored = await invoke(later, "read_reading", dict(reading_id=rid))
        assert restored.ok
        assert later.session.state["chart_id"] == natal.data["chart_id"]
        assert later.session.state["bazi_result"]["pillars"] == bazi.data["pillars"]
        followup = await invoke(later, "submit_reading", output)
        assert followup.ok
        assert later.store.get_response(later.session.user_id, followup.data["response_id"])
        assert later.store.get_reading(later.session.user_id, rid)["output_json"] == output | {
            "sections": [],
            "resonances": [],
            "tensions": [],
            "timeline": [],
            "closing": "",
            "followups": [],
        }
        # Persistent cache reuse in a new reading and a new session.
        birth2 = await prepare(later)
        repeat = await invoke(later, "compute_natal_chart", birth2)
        assert repeat.data["cache_reused"] and repeat.data["chart_id"] == natal.data["chart_id"]
        later.forget()
        for table in ("readings", "reading_responses", "charts", "bazi_charts", "profile_history"):
            assert (
                later.store.db.execute(
                    f"SELECT count(*) FROM {table} WHERE user_id=?", (later.session.user_id,)
                ).fetchone()[0]
                == 0
            )
    finally:
        runtime.close()
        other.close()
        if later:
            later.close()


@pytest.mark.asyncio
async def test_astro_only_bazi_only_followup_no_tarot(project):
    for tool in ("compute_natal_chart", "compute_bazi"):
        runtime = create_runtime(project, user_id=tool, provider="demo")
        try:
            birth = await prepare(runtime)
            assert (await invoke(runtime, tool, birth)).ok
            output = draft(runtime)
            result = await invoke(runtime, "submit_reading", output)
            assert result.ok
            runtime.session.append_user("请解释原记录。")
            restored = await invoke(
                runtime, "read_reading", dict(reading_id=result.data["reading_id"])
            )
            assert restored.ok and runtime.session.state["tarot_result"] is None
            assert (await invoke(runtime, "submit_reading", output)).ok
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_unknown_time_and_hallucinations(runtime):
    birth = await prepare(runtime, False)
    assert (await invoke(runtime, "compute_natal_chart", birth)).ok
    assert (await invoke(runtime, "compute_bazi", birth)).ok
    base = draft(runtime)
    for text in (
        "上升是白羊座，说明你容易行动。",
        "太阳在天蝎座。",
        "太阳在第1宫。",
        "太阳天蝎第1宫。",
        "时柱是甲子。",
        "你的年柱是甲子。",
    ):
        bad = Reading.model_validate({**base, "summary": text})
        assert validate_reading(bad, runtime.session), text
    # 喜用神 is a traditional inference the reading may argue for; it is not a computed fact.
    inferred = Reading.model_validate({**base, "summary": "喜用神倾向于木，可多接触绿色。"})
    assert validate_reading(inferred, runtime.session) is None
    wrong = copy.deepcopy(base)
    wrong["evidence"][0]["ref_id"] = "kb:forged"
    assert not (await invoke(runtime, "submit_reading", wrong)).ok
    assert (await invoke(runtime, "submit_reading", base)).ok


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "clock,tz,utc",
    [
        ("北京时间", "Asia/Shanghai", "2000-01-01T02:00:00+00:00"),
        ("新疆时间", "Asia/Urumqi", "2000-01-01T04:00:00+00:00"),
    ],
)
async def test_xinjiang_clock_confirmation_and_explicit_override(runtime, clock, tz, utc):
    runtime.session.append_user("合成资料：2000-01-01 10:00，乌鲁木齐出生，分析工作方向。")
    assert (await invoke(runtime, "start_reading", dict(question="工作方向"))).ok
    place = await invoke(runtime, "resolve_location", dict(query="乌鲁木齐"))
    birth = dict(birth_local="2000-01-01 10:00", location_id=place.data["location"]["location_id"])
    result = await invoke(runtime, "compute_natal_chart", birth)
    assert result.data["code"] == "confirm_clock_timezone"
    runtime.session.append_user(f"我确认使用{clock}。")
    result = await invoke(runtime, "compute_natal_chart", {**birth, "tz": tz})
    assert result.ok and result.data["utc"] == utc


@pytest.mark.asyncio
async def test_compound_refs_and_required_bazi_answers(runtime):
    birth = await prepare(runtime)
    natal = await invoke(runtime, "compute_natal_chart", birth)
    item = next(i for i in natal.data["interpretations"] if i["kind"] == "planet_sign")
    assert len(item["meaning"]["component_refs"]) == 5
    assert set(item["meaning"]["component_refs"]) <= runtime.session.state["kb_refs"]
    assert (await invoke(runtime, "compute_bazi", {**birth, "gender": "male"})).ok
    runtime.session.state["question"] = "请说明日主、起运日期和首步大运"
    # Omitting an asked-for fact is recorded as a warning; a wrong 干支 is still rejected.
    assert validate_reading(Reading.model_validate(draft(runtime)), runtime.session) is None
    warnings = " ".join(runtime.session.state["output_warnings"])
    assert all(word in warnings for word in ("日主", "起运日期", "首步大运"))
    wrong = Reading.model_validate(draft(runtime, "首步大运甲子。"))
    assert validate_reading(wrong, runtime.session)
    answer = "日主辛金，1996-12-27起运，首步大运己未。"
    accepted = await invoke(runtime, "submit_reading", draft(runtime, answer))
    assert accepted.ok and accepted.data["warnings"] == []


@pytest.mark.asyncio
async def test_lunar_leap_cannot_be_invented(runtime):
    runtime.session.append_user("农历2023年二月十五 10:00，北京出生，是否闰月不知道。")
    await invoke(runtime, "start_reading", dict(question="我的性格"))
    place = await invoke(runtime, "resolve_location", dict(query="北京"))
    result = await invoke(
        runtime,
        "compute_bazi",
        dict(
            location_id=place.data["location"]["location_id"],
            calendar="lunar",
            lunar_date="2023年二月十五 10:00",
            calendar_confirmed=True,
            leap_month=False,
        ),
    )
    assert not result.ok


def test_three_plugins_implement_protocol(runtime):
    from plugins.astro import AstroPlugin
    from plugins.base import DivinationPlugin
    from plugins.bazi import BaziPlugin
    from plugins.tarot import TarotPlugin

    for plugin in (AstroPlugin, BaziPlugin):
        assert isinstance(plugin(runtime.kb, runtime.store), DivinationPlugin)
    assert isinstance(TarotPlugin(runtime.kb), DivinationPlugin)


@pytest.mark.asyncio
async def test_profile_conventions_and_aspect_strength(runtime):
    from plugins.astro import AstroPlugin

    birth = await prepare(runtime)
    runtime.session.profile.update(zishi_rule="same_day", true_solar_time=False)
    bazi = await invoke(runtime, "compute_bazi", birth)
    assert bazi.data["pillars"]["day"] == "庚午"
    natal = await invoke(runtime, "compute_natal_chart", birth)
    plugin = AstroPlugin(runtime.kb, runtime.store)
    item = next(i for i in natal.data["interpretations"] if i["kind"] == "aspect")
    result = copy.deepcopy(natal.data)
    index = int(item["fact"].split(":")[0].removeprefix("natal_aspect"))
    result["aspects"][index]["orb"] = 0
    tight = plugin.signal_strength(result, item, runtime.kb.rules("astro"))
    result["aspects"][index]["orb"] = 3
    wide = plugin.signal_strength(result, item, runtime.kb.rules("astro"))
    assert 0 <= wide < tight <= 1
    for p in result["planets"]:
        p["speed_deg_per_day"] = 10
    assert plugin.signal_strength(result, item, runtime.kb.rules("astro")) < wide


@pytest.mark.asyncio
async def test_quality_review_receives_uncited_timeline_events(runtime):
    from types import SimpleNamespace

    from scripts.live_week23 import grounded_payload

    birth = await prepare(runtime)
    natal = await invoke(runtime, "compute_natal_chart", birth)
    result = await invoke(
        runtime,
        "compute_transits",
        dict(
            chart_id=natal.data["chart_id"],
            start="2026-11-01",
            end="2026-11-30",
            bodies=["Mercury"],
        ),
    )
    assert len(result.data["events"]) > 1
    first_ref = result.data["interpretations"][0]["ref_id"]
    outcome = SimpleNamespace(data={"reading": {"evidence": [{"ref_id": first_ref}]}})
    facts = grounded_payload(runtime, outcome)["transit_result"]
    assert facts["events"] == result.data["events"]
    assert facts["event_count"] == len(result.data["events"])
    assert len(facts["cited_interpretations"]) == 1


@pytest.mark.asyncio
async def test_quality_review_projects_daily_events_with_daily_schema(runtime):
    from types import SimpleNamespace

    from plugins.daily.tools import DailyPlugin
    from scripts.live_week23 import grounded_payload
    from tests.test_week6 import ask, with_birth

    with_birth(runtime)
    await ask(runtime, "看看2026-10-20的每日运势。")
    result = await invoke(runtime, "daily_fortune", {"date": "2026-10-20"})
    assert result.ok, result.error
    assert result.data["events"]
    assert any("timeframe" not in i for i in result.data["interpretations"])
    first_ref = result.data["interpretations"][0]["ref_id"]
    outcome = SimpleNamespace(data={"reading": {"evidence": [{"ref_id": first_ref}]}})
    facts = grounded_payload(runtime, outcome)["daily_result"]
    assert facts["events"] == result.data["events"]
    assert facts["event_count"] == len(result.data["events"])
    assert len(facts["cited_interpretations"]) == 1
    assert (
        facts["model_available_interpretations"]
        == DailyPlugin.project(result.data)["interpretations"]
    )


@pytest.mark.asyncio
async def test_country_alone_cannot_select_same_country_city(runtime):
    runtime.session.append_user("出生地美国Springfield，具体州还不知道。")
    await invoke(runtime, "start_reading", dict(question="工作方向"))
    result = await invoke(runtime, "resolve_location", dict(query="Springfield"))
    candidates = result.data["candidates"]
    assert len(candidates) > 1
    chosen = candidates[0]["location_id"]
    rejected = await invoke(
        runtime, "resolve_location", dict(query="Springfield", candidate_id=chosen)
    )
    assert not rejected.ok
    runtime.session.append_user(f"确认候选location_id是{chosen}。")
    accepted = await invoke(
        runtime, "resolve_location", dict(query="Springfield", candidate_id=chosen)
    )
    assert accepted.ok and accepted.data["status"] == "resolved"


@pytest.mark.asyncio
async def test_birth_provenance_permissions_and_dependencies(runtime):
    birth = await prepare(runtime)
    for args in (
        {**birth, "birth_local": "1990-01-01 10:00"},
        {**birth, "fold": 0},
        {**birth, "location_id": "forged"},
    ):
        result = await invoke(runtime, "compute_natal_chart", args)
        assert not result.ok or result.data.get("status") == "needs_input"
    assert not (
        await invoke(runtime, "resolve_location", dict(query="Springfield", country="US"))
    ).ok
    assert not (await invoke(runtime, "compute_bazi", {**birth, "gender": "female"})).ok
    assert not (
        await invoke(
            runtime,
            "compute_transits",
            dict(chart_id="missing", start="2026-11-01", end="2026-11-30"),
        )
    ).ok
    runtime.session.role = "tarot"
    assert not (await invoke(runtime, "compute_bazi", birth)).ok
    runtime.session.role = "astro"
    runtime.session.partition = "astro"
    assert not (
        await invoke(runtime, "lookup_meaning", dict(system="bazi", kind="ten_god", key="七杀"))
    ).ok


@pytest.mark.asyncio
async def test_range_consistency_and_timing_requires_calculation(runtime):
    birth = await prepare(runtime)
    runtime.session.state["question"] = "2026-11-01至2026-11-30适合跳槽吗？"
    runtime.session.append_user(runtime.session.state["question"])
    natal = await invoke(runtime, "compute_natal_chart", birth)
    bazi = await invoke(runtime, "compute_bazi", birth)
    assert not (await invoke(runtime, "submit_reading", draft(runtime))).ok
    assert not (
        await invoke(
            runtime,
            "compute_transits",
            dict(chart_id=natal.data["chart_id"], start="2026-12-01", end="2026-12-31"),
        )
    ).ok
    trans = await invoke(
        runtime,
        "compute_transits",
        dict(
            chart_id=natal.data["chart_id"], start="2026-11-01", end="2026-11-30", bodies=["Saturn"]
        ),
    )
    assert trans.ok
    period = await invoke(
        runtime,
        "compute_bazi_period",
        dict(bazi_id=bazi.data["bazi_id"], start="2026-11-01", end="2026-11-30"),
    )
    assert period.ok
    assert (
        await invoke(
            runtime,
            "submit_reading",
            draft(runtime, summary="2026年11月有条件适合跳槽，前提是先核实岗位并拿到书面录用。"),
        )
    ).ok


@pytest.mark.asyncio
async def test_new_calculations_cannot_bypass_submit(project, scripted_model):
    model = scripted_model(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(id="1", name="start_reading", arguments=dict(question="我的性格"))
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="2",
                        name="compute_bazi",
                        arguments=dict(
                            birth_local="1998-04-12 09:30", tz="Asia/Shanghai", lon=116.4
                        ),
                    )
                ]
            ),
            ModelResponse(text="我已计算，直接回复。"),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="3", name="ask_user", arguments=dict(question="请确认还想了解哪个方面？")
                    )
                ]
            ),
        ]
    )
    runtime = create_runtime(project, provider="demo", model=model)
    try:
        result = await runtime.turn(
            "出生1998-04-12 09:30，时区Asia/Shanghai，经度116.4，分析我的性格。"
        )
        assert result.status == "ask_user"
        assert any(
            m["role"] == "user" and "使用 submit_reading" in m.get("content", "")
            for m in model.seen_messages[-1]
        )
    finally:
        runtime.close()


def test_v2_migration_preserves_rows(tmp_path):
    path = tmp_path / "v2.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE readings(reading_id TEXT PRIMARY KEY,user_id TEXT NOT NULL, session_id TEXT NOT NULL,parent_reading_id TEXT,question TEXT NOT NULL,question_type TEXT NOT NULL,systems_used TEXT NOT NULL,tarot_json TEXT,signals_json TEXT NOT NULL,output_json TEXT NOT NULL,kb_version TEXT NOT NULL,profile_version INTEGER NOT NULL,mode TEXT NOT NULL,created_at TEXT NOT NULL)"
    )
    original = (
        "legacy",
        "owner",
        "session",
        None,
        "旧问题",
        "tarot",
        '["tarot"]',
        None,
        "[]",
        '{"summary":"旧结论"}',
        "v1-6d787fced6dae05b",
        1,
        "single",
        "2026-10-13",
    )
    db.execute("INSERT INTO readings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", original)
    db.execute("PRAGMA user_version=2")
    db.commit()
    db.close()
    store = Store(path)
    try:
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 4
        row = store.db.execute("SELECT * FROM readings WHERE reading_id='legacy'").fetchone()
        assert tuple(row)[:14] == original
        assert store.get_reading("owner", "legacy")["calculations_json"] == {}
        assert store.get_reading("owner", "legacy")["merge_json"] == {}
    finally:
        store.close()
