"""Stage 0 regressions: request calendar, expiring identities and crisis hold."""

from datetime import UTC, datetime

import httpx
import pytest

from app import create_runtime
from common.safety import SAFETY_CONFIRMATION
from harness.models import ModelResponse
from memory.store import Store
from tests.test_week6 import ask, with_birth
from tests.test_week23_integration import invoke
from web import COOKIE, MAX_IDLE, create_web_app

HEADERS = {"X-Zhiming-Client": "web", "Origin": "http://testserver"}


async def test_calendar_crosses_midnight_and_daily_uses_new_day(runtime, scripted_model):
    instants = iter(
        [
            datetime(2026, 10, 20, 15, 59, tzinfo=UTC),
            datetime(2026, 10, 20, 16, 1, tzinfo=UTC),
        ]
    )
    runtime.clock = lambda: next(instants)
    runtime.model = scripted_model([ModelResponse(text="收到"), ModelResponse(text="收到")])
    with_birth(runtime)
    for day in ("2026-10-20", "2026-10-21"):
        await runtime.turn("今天运势怎么样？")
        assert runtime.session.calendar_anchor == day
        anchors = [
            m["content"]
            for m in runtime.model.seen_messages[-1]
            if m["role"] == "system" and m["content"].startswith("本轮日历基准")
        ]
        assert len(anchors) == 1 and day in anchors[0]
        await ask(runtime, "今天运势怎么样？")
        result = await invoke(runtime, "daily_fortune", {"date": day})
        assert result.ok, result.error
        assert runtime.store.get_daily(runtime.session.user_id, day)


@pytest.mark.parametrize(
    "consultation,birth,expected_zone,expected_day",
    [
        ("America/Los_Angeles", "Asia/Shanghai", "America/Los_Angeles", "2026-10-20"),
        (None, "America/Los_Angeles", "America/Los_Angeles", "2026-10-20"),
        (None, None, "Asia/Shanghai", "2026-10-21"),
    ],
)
async def test_calendar_timezone_priority(
    runtime, scripted_model, consultation, birth, expected_zone, expected_day
):
    runtime.clock = lambda: datetime(2026, 10, 20, 16, 1, tzinfo=UTC)
    runtime.session.profile.update(consultation_tz=consultation, tz=birth)
    runtime.model = scripted_model([ModelResponse(text="收到")])
    await runtime.turn("今天是几号？")
    assert runtime.session.calendar_anchor == expected_day
    assert runtime.session.calendar_timezone == expected_zone


async def test_profile_timezone_change_updates_same_turn_calendar(runtime):
    runtime.session.refresh_calendar(datetime(2026, 10, 20, 16, 1, tzinfo=UTC))
    runtime.session.append_user("咨询按洛杉矶时间。")
    # Register the resolved city as normal location resolution would.
    runtime.session.state["locations"] = {
        "la": {"tz": "America/Los_Angeles", "name": "洛杉矶", "display_name": "洛杉矶"}
    }
    result = await invoke(
        runtime,
        "update_profile",
        {
            "field": "consultation_tz",
            "value": "America/Los_Angeles",
            "evidence": "咨询按洛杉矶时间",
        },
    )
    assert result.ok, result.error
    assert runtime.session.calendar_anchor == "2026-10-20"
    assert any("America/Los_Angeles" in m.get("content", "") for m in runtime.session.messages)


async def test_overseas_daily_uses_local_date_and_birth_timezone(runtime, scripted_model):
    with_birth(runtime, tz="America/Los_Angeles", lat=34.05, lon=-118.24, true_solar_time=False)
    runtime.clock = lambda: datetime(2026, 10, 20, 16, 1, tzinfo=UTC)
    runtime.model = scripted_model([ModelResponse(text="收到")])
    await runtime.turn("今天运势怎么样？")
    await ask(runtime, "今天运势怎么样？")
    wrong = await invoke(runtime, "daily_fortune", {"date": "2026-10-21"})
    assert not wrong.ok and "2026-10-20" in wrong.error
    result = await invoke(runtime, "daily_fortune", {"date": "2026-10-20"})
    assert result.ok, result.error
    assert result.data.get("status") != "needs_input", result.data
    assert result.data["tz"] == "America/Los_Angeles"


async def test_crisis_hold_survives_reading_reset_and_requires_standalone_confirmation(runtime):
    await runtime.turn("我不想活了")
    runtime.session.state.clear()  # CLI /new must not reset safety.
    for message in (
        "抽张牌",
        "我安全了",
        SAFETY_CONFIRMATION + "，但我还是想死",
        SAFETY_CONFIRMATION + "，现在帮我占卜",
    ):
        assert (await runtime.turn(message)).status == "crisis_support"
        assert runtime.session.safety_pending
        assert not runtime.store.recent_readings(runtime.session.user_id)
        assert runtime.session.model_calls == 0
    assert (await runtime.turn(SAFETY_CONFIRMATION)).status == "crisis_support"
    assert not runtime.session.safety_pending
    assert runtime.session.model_calls == 0
    assert (await runtime.turn("抽张牌")).status == "submit_reading"


async def test_web_renewal_expiry_and_orphan_cleanup(project, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr("web.time.time", lambda: now[0])
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtimes.append(runtime)
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client,
    ):
        await client.get("/api/session")
        original_cookie = client.cookies.get(COOKIE)
        first = runtimes[0]
        user_id = first.session.user_id
        await client.post("/api/chat", json={"message": "抽张牌"})
        directory = first.tracer.user_dir(user_id)
        assert directory.exists()
        for _ in range(3):
            now[0] += MAX_IDLE - 10
            response = await client.get("/")
            assert "Max-Age=43200" in response.headers["set-cookie"]
            assert client.cookies.get(COOKIE) == original_cookie
        assert len((await client.get("/api/session")).json()["history"]) == 1
        now[0] += MAX_IDLE + 1
        response = await client.post("/api/chat", json={"message": "继续"})
        assert response.status_code == 401
        assert not directory.exists()
        with_store = Store(project / "data/app.db")
        try:
            assert with_store.get_profile(user_id) == {"version": 0}
            assert with_store.recent_readings(user_id) == []
        finally:
            with_store.close()
        await client.get("/api/session")
        assert client.cookies.get(COOKIE) != original_cookie
        orphan = runtimes[-1]
        orphan_id = orphan.session.user_id
        orphan.store.update_profile(orphan_id, "name", "测试", "测试")
        orphan.tracer.log(orphan.session, "test")
        orphan_dir = orphan.tracer.user_dir(orphan_id)
    now[0] += MAX_IDLE + 1
    restarted = create_web_app(root=project, runtime_factory=factory)
    async with restarted.router.lifespan_context(restarted):
        store = Store(project / "data/app.db")
        try:
            assert store.get_profile(orphan_id) == {"version": 0}
            assert not orphan_dir.exists()
        finally:
            store.close()


async def test_web_demo_chart_and_new_chat_cannot_bypass_safety(project):
    app = create_web_app(root=project)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client,
    ):
        await client.get("/api/session?provider=demo")
        result = await client.post("/api/chat", json={"message": "我不想活了", "system": "bazi"})
        assert result.json()["messages"][-1]["status"] == "crisis_support"
        await client.post("/api/new", json={"provider": "demo"})
        result = await client.post("/api/chart", json={"system": "bazi", "birth": {}})
        assert result.json()["code"] == "safety_confirmation_required"
        result = await client.post("/api/chat", json={"message": "看看八字", "system": "bazi"})
        assert result.json()["messages"][-1]["status"] == "crisis_support"


@pytest.mark.parametrize(
    "profile,present,absent",
    [
        ({"tz": "Asia/Shanghai"}, "12356", "988"),
        ({"tz": "Asia/Urumqi"}, "12356", "988"),
        ({"tz": "America/New_York"}, "988", "12356"),
        ({"consultation_tz": "America/Los_Angeles", "tz": "Asia/Shanghai"}, "988", "12356"),
        ({"consultation_tz": "Europe/London", "tz": "Asia/Shanghai"}, "紧急服务", "12356"),
        ({}, "紧急服务", "12356"),
    ],
)
async def test_hotlines_follow_user_information(runtime, profile, present, absent):
    runtime.session.profile.update(profile)
    result = await runtime.turn("我不想活了")
    assert present in result.text and absent not in result.text


async def test_web_birth_form_selects_hotline_before_profile_is_saved(project):
    app = create_web_app(root=project)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client,
    ):
        await client.get("/api/session?provider=demo")
        response = await client.post(
            "/api/chat", json={"message": "我不想活了", "birth": {"location_id": "1803361"}}
        )
        assert "12356" in response.json()["messages"][-1]["text"]
