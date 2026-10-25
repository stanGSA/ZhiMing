"""Stage 0 regressions: request calendar, expiring identities and crisis hold."""

from datetime import UTC, datetime

import httpx
import pytest

from app import create_runtime
from common.location import consultation_timezone_evidence
from common.safety import SAFETY_CONFIRMATION, SAFETY_PROMPT
from harness.models import ModelResponse
from harness.session import Session
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


# ---- review fixes: invalid timezones, daily/calendar agreement, cleanup retries ----------


async def test_invalid_timezone_rejected_and_legacy_value_cannot_block_crisis(project):
    runtime = create_runtime(root=project, user_id="synthetic-tz", seed=42)
    try:
        runtime.session.append_user("我的时区是PST，住在America")
        for value in ("PST", "America"):
            result = await invoke(
                runtime,
                "update_profile",
                {"field": "tz", "value": value, "evidence": "我的时区是PST，住在America"},
            )
            assert not result.ok and result.code == "invalid_arguments"
        assert "tz" not in runtime.store.get_profile("synthetic-tz")
        assert consultation_timezone_evidence("按America/Argentina时间", runtime.session) is None
        runtime.store.update_profile("synthetic-tz", "tz", "PST", "旧版本写入")
    finally:
        runtime.close()
    legacy = create_runtime(root=project, user_id="synthetic-tz", seed=42)
    try:
        assert legacy.session.calendar_timezone == "Asia/Shanghai"
        result = await legacy.turn("我不想活了")
        assert result.status == "crisis_support" and "紧急服务" in result.text
    finally:
        legacy.close()


LOS_ANGELES = {
    "tz": "America/Los_Angeles",
    "lat": 34.05,
    "lon": -118.24,
    "name": "洛杉矶",
    "display_name": "洛杉矶",
}


async def test_daily_saves_unsaved_birth_timezone_before_dating_today(runtime, scripted_model):
    for field, value in {
        "birth_local_dt": "1996-05-10 08:30",
        "time_known": True,
        "true_solar_time": False,
    }.items():
        runtime.session.profile = runtime.store.update_profile(
            runtime.session.user_id, field, value, "合成测试资料"
        )
    runtime.clock = lambda: datetime(2026, 10, 20, 16, 1, tzinfo=UTC)
    runtime.model = scripted_model([ModelResponse(text="收到")])
    question = "我出生在洛杉矶，今天运势怎么样？"
    await runtime.turn(question)
    assert runtime.session.calendar_anchor == "2026-10-21"  # nothing saved: default calendar
    await ask(runtime, question)
    runtime.session.state["locations"] = {"la": LOS_ANGELES}
    first = await invoke(runtime, "daily_fortune", {"date": "2026-10-21", "location_id": "la"})
    assert first.code == "calendar_timezone_mismatch"
    assert "tz=America/Los_Angeles" in first.error
    saved = await invoke(runtime, "resolve_location", {"query": "洛杉矶"})
    assert saved.ok and saved.data["status"] == "resolved"
    assert runtime.store.get_profile(runtime.session.user_id)["tz"] == "America/Los_Angeles"
    assert runtime.session.calendar_anchor == "2026-10-20"
    stale = await invoke(runtime, "daily_fortune", {"date": "2026-10-21", "location_id": "la"})
    assert not stale.ok and "2026-10-20" in stale.error
    result = await invoke(runtime, "daily_fortune", {"date": "2026-10-20", "location_id": "la"})
    assert result.ok, result.error
    assert result.data["tz"] == "America/Los_Angeles" and result.data["date"] == "2026-10-20"


async def test_daily_stated_consultation_timezone_is_saved_before_use(runtime, scripted_model):
    with_birth(runtime, tz="America/Los_Angeles", lat=34.05, lon=-118.24, true_solar_time=False)
    runtime.clock = lambda: datetime(2026, 10, 20, 16, 1, tzinfo=UTC)
    runtime.model = scripted_model([ModelResponse(text="收到")])
    question = "我现在住在北京，按北京时间看今天运势"
    await runtime.turn(question)
    assert runtime.session.calendar_anchor == "2026-10-20"  # birth timezone until saved
    await ask(runtime, question)
    first = await invoke(runtime, "daily_fortune", {"date": "2026-10-20"})
    assert first.code == "calendar_timezone_mismatch"
    assert "consultation_tz=Asia/Shanghai" in first.error
    saved = await invoke(
        runtime,
        "update_profile",
        {"field": "consultation_tz", "value": "Asia/Shanghai", "evidence": "按北京时间"},
    )
    assert saved.ok, saved.error
    assert runtime.session.calendar_anchor == "2026-10-21"
    result = await invoke(runtime, "daily_fortune", {"date": "2026-10-21"})
    assert result.ok, result.error
    assert result.data["tz"] == "Asia/Shanghai"


async def test_web_cleanup_failure_keeps_deadline_and_is_retried(project, monkeypatch):
    import shutil

    now = [1_800_000_000.0]
    monkeypatch.setattr("web.time.time", lambda: now[0])
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtimes.append(runtime)
        return runtime

    real_rmtree, failures = shutil.rmtree, []

    def flaky_rmtree(path, *args, **kwargs):
        if not failures:
            failures.append(path)
            raise PermissionError("trace file in use")
        return real_rmtree(path, *args, **kwargs)

    app = create_web_app(root=project, runtime_factory=factory)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client,
    ):
        await client.get("/api/session?provider=demo")
        await client.post("/api/chat", json={"message": "抽张牌"})
        user_id = runtimes[0].session.user_id
        directory = runtimes[0].tracer.user_dir(user_id)
        monkeypatch.setattr("web.shutil.rmtree", flaky_rmtree)
        now[0] += MAX_IDLE + 1
        response = await client.post("/api/chat", json={"message": "继续"})
        assert response.status_code == 401 and failures and directory.exists()
        store = Store(project / "data/app.db")
        try:
            assert user_id in store.expired_web_identities(now[0])  # kept for the retry
        finally:
            store.close()
        assert (await client.get("/api/locations")).status_code == 200
        assert not directory.exists()
        store = Store(project / "data/app.db")
        try:
            assert user_id not in store.expired_web_identities(now[0])
            assert store.recent_readings(user_id) == []
        finally:
            store.close()


async def test_web_message_is_safety_classified_once(project):
    calls = []

    class Model:
        async def chat(self, messages, tools):
            if messages[0]["content"] == SAFETY_PROMPT:
                calls.append(messages[-1]["content"])
                return ModelResponse(text='{"crisis": false}')
            return ModelResponse(text="收到")

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtime.model = Model()
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client,
    ):
        await client.get("/api/session")
        response = await client.post("/api/chat", json={"message": "压力大，想消失几天去旅行"})
        assert response.json()["messages"][-1]["status"] == "text"
    assert len(calls) == 1


async def test_safety_confirmation_ignores_quotes_width_and_spacing(runtime):
    for confirmation in (
        "“" + SAFETY_CONFIRMATION + "”",
        SAFETY_CONFIRMATION.replace("，", ",") + " ！",
    ):
        await runtime.turn("我不想活了")
        assert (await runtime.turn(confirmation)).status == "crisis_support"
        assert not runtime.session.safety_pending


async def test_compare_layers_pins_the_clock(runtime, scripted_model):
    from scripts.compare_layers import ANCHOR, pin_calendar

    pin_calendar(runtime)
    runtime.model = scripted_model([ModelResponse(text="收到")])
    await runtime.turn("今天怎么样？")
    assert runtime.session.calendar_anchor == ANCHOR


@pytest.mark.parametrize(
    "text,expected",
    [
        ("我的出生时区是America/Los_Angeles", None),
        ("出生钟表时区为Asia/Shanghai", None),
        ("Asia/Shanghai是我的出生时区", None),
        ("出生钟表采用北京时间", None),
        ("出生钟表按当地时间记录", None),
        ("出生钟表按洛杉矶时间记录", None),
        ("出生在北京现居洛杉矶", "America/Los_Angeles"),
        ("本次咨询按America/Los_Angeles时间", "America/Los_Angeles"),
        ("America/Los_Angeles", "America/Los_Angeles"),
        ("出生时区是Asia/Shanghai；本次按America/Los_Angeles时间", "America/Los_Angeles"),
        ("出生时区是Asia/Shanghai，本次按北京时间", "Asia/Shanghai"),
        ("出生在美国本次咨询按北京时间", "Asia/Shanghai"),
        ("出生在美国按北京时间看今天运势", "Asia/Shanghai"),
        ("本次按出生地时间看运势", "Asia/Shanghai"),
        ("用出生地时间看今天运势", "Asia/Shanghai"),
        ("以出生地时间为准", "Asia/Shanghai"),
        ("时间就用出生地当地的", "Asia/Shanghai"),
        ("这次用出生地时间看", "Asia/Shanghai"),
        ("出生在美国按北京时间算流年", "Asia/Shanghai"),
        ("出生在美国按北京时间看明天", "Asia/Shanghai"),
        ("不要按出生地时间看运势", None),
        ("不用出生地时间", None),
        ("不要用出生地时间看运势", None),
        ("我用当地的手机号", None),
        ("出生钟表用出生地时间记录", None),
        ("出生钟表按北京时间记录", None),
        ("北京时间早上8点出生", None),
        ("出生时用北京时间算时辰", None),
        ("按北京时间出生，今天运势如何", None),
    ],
)
def test_consultation_timezone_distinguishes_birth_clock(text, expected):
    session = Session(user_id="synthetic-timezone")
    session.state["locations"] = {"la": LOS_ANGELES}
    assert consultation_timezone_evidence(text, session, "Asia/Shanghai") == expected


@pytest.mark.parametrize(
    "text",
    [
        "用出生地时间看今天运势",
        "以出生地时间为准",
        "时间就用出生地当地的",
        "这次用出生地时间看",
        "出生在美国按北京时间算流年",
        "出生在美国按北京时间看明天",
    ],
)
async def test_explicit_consultation_timezone_overrides_saved_timezone(runtime, text):
    with_birth(runtime, consultation_tz="America/Los_Angeles")
    runtime.session.refresh_calendar(datetime(2026, 10, 20, 16, 1, tzinfo=UTC))
    assert runtime.session.calendar_anchor == "2026-10-20"
    runtime.session.append_user(text)
    result = await invoke(
        runtime,
        "update_profile",
        {"field": "consultation_tz", "value": "Asia/Shanghai", "evidence": text},
    )
    assert result.ok, result.error
    assert runtime.store.get_profile(runtime.session.user_id)["consultation_tz"] == "Asia/Shanghai"
    assert runtime.session.calendar_timezone == "Asia/Shanghai"
    assert runtime.session.calendar_anchor == "2026-10-21"


async def test_birth_timezone_evidence_cannot_overwrite_consultation_profile(runtime):
    with_birth(runtime, consultation_tz="America/Los_Angeles")
    runtime.session.append_user("出生钟表时区为Asia/Shanghai")
    # The model cannot trim the birth label out of the evidence to change its meaning.
    result = await invoke(
        runtime,
        "update_profile",
        {"field": "consultation_tz", "value": "Asia/Shanghai", "evidence": "Asia/Shanghai"},
    )
    assert not result.ok
    assert runtime.store.get_profile(runtime.session.user_id)["consultation_tz"] == (
        "America/Los_Angeles"
    )
