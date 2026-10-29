"""Durable account credits and rolling IP/device registration checks, without paid calls."""

import asyncio
import json

import httpx
import pytest

from app import create_runtime
from harness.llm import OpenAIModel
from harness.metering import MeteredModel, QuotaExceeded
from harness.models import ModelResponse
from memory.accounts import FREE_TOKENS, REGISTRATION_WINDOW, AccountError, AccountStore
from web import DEVICE_COOKIE, create_web_app

HEADERS = {"Origin": "https://testserver", "X-Zhiming-Client": "web"}


def store_for(project):
    return AccountStore(project / "data/app.db")


def test_credit_reservations_survive_restarts_and_settle_once(project):
    store = store_for(project)
    user = store.create("额度账号", "test-hash")["user_id"]
    call, limit = store.reserve_tokens(user, 1000, 8192)
    assert limit == 8192 and store.quota(user)["reserved"] == 9192
    store.settle_tokens(call, 1200, 300)
    store.settle_tokens(call, 1200, 300)
    assert store.quota(user) == {
        "limit": FREE_TOKENS,
        "used": 1500,
        "reserved": 0,
        "remaining": FREE_TOKENS - 1500,
    }
    pending, _ = store.reserve_tokens(user, 1000, 1000)
    store.close()
    store = store_for(project)
    assert store.quota(user)["reserved"] == 2000
    store.settle_tokens(pending, None, None)
    assert store.quota(user)["used"] == 3500
    store.close()


def test_two_connections_cannot_reserve_the_same_credit(project):
    store = store_for(project)
    user = store.create("并发额度", "hash")["user_id"]
    other = store_for(project)
    try:
        call, _ = store.reserve_tokens(user, 249_000, 1000)
        with pytest.raises(QuotaExceeded):
            other.reserve_tokens(user, 1, 1000)
        store.settle_tokens(call, 249_000, 1000)
        with pytest.raises(QuotaExceeded):
            other.reserve_tokens(user, 1, 1000)
        assert other.quota(user)["remaining"] == 0
    finally:
        other.close()
        store.close()


def test_registration_window_is_atomic_and_survives_account_deletion(project):
    store = store_for(project)
    first = store.create("注册一", "hash", pair_hash="pair", registered_at=1000)
    other = store_for(project)
    try:
        store.delete(first["user_id"])
        with pytest.raises(AccountError, match="7 天"):
            other.create("注册二", "hash", pair_hash="pair", registered_at=1001)
        assert not other.credentials("注册二")
        allowed = other.create(
            "注册二", "hash", pair_hash="pair", registered_at=1000 + REGISTRATION_WINDOW
        )
        assert allowed
        other.undo_registration(allowed["user_id"])
        assert other.create("注册三", "hash", pair_hash="pair", registered_at=1001)
    finally:
        other.close()
        store.close()


def client(app, ip="203.0.113.1"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 40000)),
        base_url="https://testserver",
        headers=HEADERS,
    )


async def register(browser, name):
    return await browser.post(
        "/api/account/register",
        json={"username": name, "password": "test-pass123", "accept_privacy": True},
    )


async def test_same_ip_device_blocks_for_seven_days_but_other_devices_are_allowed(
    project, monkeypatch
):
    now = [1_800_000_000.0]
    monkeypatch.setattr("web.time.time", lambda: now[0])
    app = create_web_app(root=project, public_origin="https://testserver")
    async with app.router.lifespan_context(app), client(app) as first, client(app) as second:
        initial = await first.get("/api/account")
        assert "Secure" in initial.headers["set-cookie"]
        assert "HttpOnly" in initial.headers["set-cookie"]
        device = first.cookies.get(DEVICE_COOKIE)
        assert device
        assert (await register(first, "设备一")).status_code == 201
        blocked = await register(first, "重复设备")
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "registration_limited"
        assert int(blocked.headers["retry-after"]) == REGISTRATION_WINDOW
        # Headers supplied by the caller cannot change the ASGI client IP.
        first.headers["X-Forwarded-For"] = "198.51.100.77"
        assert (await register(first, "伪造地址")).status_code == 429
        assert (await register(second, "设备二")).status_code == 201
        async with client(app, "203.0.113.2") as moved:
            moved.cookies.update({DEVICE_COOKIE: device})
            assert (await register(moved, "不同地址")).status_code == 201
        # Deletion of the account cannot release the seven-day registration claim.
        deleted = await first.post("/api/account/delete", json={"password": "test-pass123"})
        assert deleted.status_code == 200
        assert (await register(first, "注销后重领")).status_code == 429
        now[0] += REGISTRATION_WINDOW
        assert (await register(first, "七天后")).status_code == 201


async def test_web_quota_is_shared_by_features_devices_and_restart(project):
    calls = []

    class FakeModel:
        async def chat(self, messages, tools):
            calls.append(True)
            return ModelResponse(text="测试回复", input_tokens=1000, output_tokens=100)

    def factory(**kwargs):
        return create_runtime(**{**kwargs, "provider": "demo", "model": FakeModel()})

    app = create_web_app(root=project, public_origin="https://testserver", runtime_factory=factory)
    async with app.router.lifespan_context(app), client(app) as browser:
        created = await register(browser, "额度联通")
        assert created.status_code == 201
        assert created.json()["account"]["quota"]["remaining"] == FREE_TOKENS
        await browser.get("/api/session")
        result = await browser.post("/api/chat", json={"message": "你好"})
        assert result.json()["account"]["quota"]["used"] == 1100
        store = store_for(project)
        user = store.credentials("额度联通")[0]["user_id"]
        # Account changes and history deletion must not reset credit.
        await browser.delete("/api/readings")
        assert store.quota(user)["used"] == 1100
        with store.db:
            store.db.execute(
                "UPDATE account_quota SET used_tokens=? WHERE user_id=?", (FREE_TOKENS, user)
            )
        prior = len(calls)
        for system in ("auto", "tarot", "bazi", "astro", "name", "dream", "daily"):
            await browser.get(f"/api/session?system={system}")
            reply = await browser.post("/api/chat", json={"message": "你好", "system": system})
            if reply.status_code == 200:
                assert reply.json()["messages"][-1]["status"] in ("quota_exhausted", "chart_only")
            else:
                assert reply.status_code == 403
        assert len(calls) == prior
        # Reading account state and offline tools remain usable.
        assert (await browser.get("/api/account")).json()["account"]["quota"]["remaining"] == 0
        assert (await browser.post("/api/new", json={"provider": "demo"})).status_code == 200
        assert (await browser.get("/api/session")).json()["provider"] == "demo"
        cookies = dict(browser.cookies)
        store.close()
    restarted = create_web_app(
        root=project, public_origin="https://testserver", runtime_factory=factory
    )
    async with restarted.router.lifespan_context(restarted), client(restarted) as browser:
        browser.cookies.update(cookies)
        assert (await browser.get("/api/account")).json()["account"]["quota"]["remaining"] == 0


async def test_openai_meter_counts_retries_cached_input_and_limits_output(project, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    store = store_for(project)
    user = store.create("请求计量", "hash")["user_id"]
    payloads = []

    def respond(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "prompt_cache_hit_tokens": 80,
                },
            },
        )

    underlying = OpenAIModel(
        "test",
        max_tokens=8192,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    model = MeteredModel(underlying, store, user)
    try:
        await model.chat([{"role": "user", "content": "hello"}], [])
        assert store.quota(user)["used"] == 150  # cache hits are part of the input, not subtracted
        with store.db:
            store.db.execute(
                "UPDATE account_quota SET used_tokens=? WHERE user_id=?", (FREE_TOKENS - 2000, user)
            )
        await model.chat([{"role": "user", "content": "hello"}], [])
        assert 256 <= payloads[-1]["max_tokens"] < 8192
        with store.db:
            store.db.execute(
                "UPDATE account_quota SET used_tokens=? WHERE user_id=?", (FREE_TOKENS, user)
            )
        before = len(payloads)
        with pytest.raises(QuotaExceeded):
            await model.chat([{"role": "user", "content": "hello"}], [])
        assert len(payloads) == before
    finally:
        await underlying.close()
        store.close()


async def test_cancelled_and_missing_usage_do_not_release_unknown_costs(project):
    store = store_for(project)
    user = store.create("不确定用量", "hash")["user_id"]
    started = asyncio.Event()

    class CancelledModel:
        async def chat(self, messages, tools):
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(MeteredModel(CancelledModel(), store, user).chat([], []))
    await started.wait()
    assert store.quota(user)["reserved"] > 0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.quota(user)["reserved"] == 0 and store.quota(user)["used"] > 0
    before = store.quota(user)["used"]

    class MissingUsage:
        async def chat(self, messages, tools):
            return ModelResponse(text="unknown", usage_available=False)

    await MeteredModel(MissingUsage(), store, user).chat([], [])
    assert store.quota(user)["used"] > before
    assert (
        store.db.execute("SELECT COUNT(*) FROM model_usage WHERE status='uncertain'").fetchone()[0]
        == 2
    )
    store.close()


async def test_http_retry_reserves_each_attempt_and_explicit_rejection_is_refunded(
    project, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    store = store_for(project)
    user = store.create("重试记账", "hash")["user_id"]
    attempts = []

    def respond(request):
        attempts.append(True)
        if len(attempts) == 1:
            return httpx.Response(500, json={"error": {"message": "offline test"}})
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        )

    underlying = OpenAIModel(
        "test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
    )
    try:
        await MeteredModel(underlying, store, user).chat([], [])
        statuses = [
            r[0] for r in store.db.execute("SELECT status FROM model_usage ORDER BY created_at")
        ]
        assert statuses == ["uncertain", "settled"]
        assert store.quota(user)["used"] > 150
    finally:
        await underlying.close()

    before = store.quota(user)
    rejected = OpenAIModel(
        "test",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    400, json={"error": {"message": "invalid test request"}}
                )
            )
        ),
    )
    try:
        with pytest.raises(Exception, match="400"):
            await MeteredModel(rejected, store, user).chat([], [])
        assert store.quota(user) == before
    finally:
        await rejected.close()
        store.close()


async def test_concurrent_registration_rechecks_pair_after_password_hashing(project):
    app = create_web_app(root=project, public_origin="https://testserver")
    async with app.router.lifespan_context(app), client(app) as browser:
        await browser.get("/api/account")
        results = await asyncio.gather(
            register(browser, "并发注册一"), register(browser, "并发注册二")
        )
        assert sorted(r.status_code for r in results) == [201, 429]
        store = store_for(project)
        assert store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
        assert store.db.execute("SELECT COUNT(*) FROM registration_devices").fetchone()[0] == 1
        store.close()


async def test_safety_classifier_is_metered_and_cannot_bypass_empty_quota(project):
    calls = []

    class Classifier:
        async def chat(self, messages, tools):
            calls.append(True)
            return ModelResponse(text='{"crisis": false}', input_tokens=40, output_tokens=10)

    store = store_for(project)
    user = store.create("辅助调用", "hash")["user_id"]
    runtime = create_runtime(
        root=project,
        user_id=user,
        provider="demo",
        model=Classifier(),
        model_transform=lambda model: MeteredModel(model, store, user),
    )
    try:
        await runtime.safety_response("最近压力大得受不了")
        assert store.quota(user)["used"] == 50 and calls
        with store.db:
            store.db.execute(
                "UPDATE account_quota SET used_tokens=? WHERE user_id=?", (FREE_TOKENS, user)
            )
        count = len(calls)
        with pytest.raises(QuotaExceeded):
            await runtime.safety_response("最近压力大得受不了")
        assert len(calls) == count
    finally:
        runtime.close()
        store.close()


async def test_all_runtime_model_roles_share_the_account_ledger(project):
    import yaml

    config_path = project / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["policy_judge"] = {"enabled": True}
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    class RoleModel:
        async def chat(self, messages, tools):
            return ModelResponse(text="ok", input_tokens=50, output_tokens=10)

    store = store_for(project)
    user = store.create("多角色额度", "hash")["user_id"]
    runtime = create_runtime(
        root=project,
        user_id=user,
        provider="demo",
        mode="multi",
        model=RoleModel(),
        specialist_model=RoleModel(),
        reviewer_model=RoleModel(),
        model_transform=lambda model: MeteredModel(model, store, user),
    )
    try:
        for role in (runtime.model, runtime.specialist_model, runtime.reviewer_model):
            assert isinstance(role, MeteredModel)
            await role.chat([], [])
        assert runtime.session.policy_judge.model is runtime.model
        assert store.quota(user)["used"] == 180
    finally:
        runtime.close()
        store.close()
