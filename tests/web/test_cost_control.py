"""Site-wide cost control, the admin console API and the monitor's endpoints, without paid calls."""

import asyncio

import httpx
import pytest

from app import create_runtime
from harness.metering import (
    AccountSuspended,
    ConcurrencyGate,
    MeteredModel,
    ModelBusy,
    QuotaExceeded,
    SiteBudgetExhausted,
    SitePaused,
)
from harness.models import ModelResponse
from memory.accounts import FREE_TOKENS, AccountStore
from web import create_web_app

HEADERS = {"Origin": "https://testserver", "X-Zhiming-Client": "web"}
TOKEN = "m" * 40


def store_for(project, **defaults):
    return AccountStore(project / "data/app.db", cost_defaults=defaults or None)


def test_daily_budget_shrinks_then_refuses_and_survives_account_deletion(project):
    store = store_for(project, daily_token_budget=20_000)
    user = store.create("预算一", "hash")["user_id"]
    call, output = store.reserve_tokens(user, 1000, 8192, model="flash")
    assert output == 8192
    store.settle_tokens(call, 9000, 1000)
    # 10,000 left today: the output allowance shrinks to fit the site budget.
    call, output = store.reserve_tokens(user, 2000, 8192)
    assert output == 8000
    store.settle_tokens(call, 2000, 7000)
    with pytest.raises(SiteBudgetExhausted) as refused:
        store.reserve_tokens(user, 2000, 8192)
    assert refused.value.retryable and isinstance(refused.value, QuotaExceeded)
    events = [e["kind"] for e in store.costs.events()]
    assert events.count("budget_exhausted") == 1
    with pytest.raises(SiteBudgetExhausted):
        store.reserve_tokens(user, 2000, 8192)
    assert [e["kind"] for e in store.costs.events()].count("budget_exhausted") == 1
    # Deleting the spender does not hand the site its budget back.
    store.delete(user)
    other = store.create("预算二", "hash")["user_id"]
    with pytest.raises(SiteBudgetExhausted):
        store.reserve_tokens(other, 2000, 8192)
    assert store.db.execute("SELECT COUNT(*) FROM site_usage WHERE user_id IS NULL").fetchone()[0]
    store.close()


def test_cost_budget_uses_unit_prices_and_the_worst_price_while_unknown(project):
    store = store_for(
        project, daily_cost_budget=1.0, input_price_per_mtok=10.0, output_price_per_mtok=40.0
    )
    user = store.create("金额预算", "hash")["user_id"]
    call, _ = store.reserve_tokens(user, 10_000, 4096)
    spend = store.costs.spend(0)
    # Pending reservations are priced at the higher (output) price.
    assert spend["cost"] == pytest.approx(14_096 * 40 / 1e6)
    store.settle_tokens(call, 10_000, 2_000)
    assert store.costs.spend(0)["cost"] == pytest.approx(0.1 + 0.08)
    # 0.92 spent: 0.08 left buys 2,000 tokens at the worst price, so the output shrinks.
    with store.db:
        store.db.execute("UPDATE site_usage SET input_tokens=92000, output_tokens=0")
    call, output = store.reserve_tokens(user, 1000, 4096)
    assert output == 1000
    store.settle_tokens(call, 0, 0)
    with store.db:
        store.db.execute("UPDATE site_usage SET input_tokens=99000 WHERE input_tokens=92000")
    with pytest.raises(SiteBudgetExhausted):
        store.reserve_tokens(user, 1000, 4096)
    store.close()


def test_burst_auto_pauses_the_site_and_resume_starts_a_new_window(project, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr("memory.accounts.time.time", lambda: now[0])
    store = store_for(project, burst_site_tokens=30_000, burst_window_min=10)
    user = store.create("突发", "hash")["user_id"]
    call, _ = store.reserve_tokens(user, 10_000, 8192)
    store.settle_tokens(call, 10_000, 8000)
    with pytest.raises(SitePaused):
        store.reserve_tokens(user, 10_000, 8192)
    state = store.costs.pause_state()
    assert state["auto"] and "阈值" in state["reason"]
    assert store.costs.events()[0]["kind"] == "site_paused_auto"
    # Stays paused for everyone, even small requests and after the window passes.
    other = store.create("旁人", "hash")["user_id"]
    now[0] += 3600
    with pytest.raises(SitePaused):
        store.reserve_tokens(other, 100, 512)
    store.costs.manual_resume("管理员")
    call, _ = store.reserve_tokens(other, 100, 512)
    assert store.costs.pause_state() is None
    assert store.costs.audit_log()[0]["action"] == "resume_models"
    store.close()


def test_auto_pause_can_resume_by_itself_but_a_manual_pause_cannot(project, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr("memory.accounts.time.time", lambda: now[0])
    store = store_for(project, burst_site_tokens=5_000, auto_resume_min=30)
    user = store.create("自动恢复", "hash")["user_id"]
    with pytest.raises(SitePaused):
        store.reserve_tokens(user, 4000, 2048)
    now[0] += 29 * 60
    with pytest.raises(SitePaused):
        store.reserve_tokens(user, 100, 512)
    now[0] += 60
    store.reserve_tokens(user, 100, 512)
    assert store.costs.events()[0]["kind"] == "site_resumed_auto"
    store.costs.manual_pause("维护", "管理员")
    now[0] += 7 * 86400
    with pytest.raises(SitePaused):
        store.reserve_tokens(user, 100, 512)
    store.close()


def test_account_burst_suspends_only_that_account(project):
    store = store_for(project, burst_account_tokens=20_000)
    user = store.create("刷量", "hash")["user_id"]
    other = store.create("正常", "hash")["user_id"]
    call, _ = store.reserve_tokens(user, 10_000, 8192)
    store.settle_tokens(call, 10_000, 8000)
    with pytest.raises(AccountSuspended) as refused:
        store.reserve_tokens(user, 2000, 1024)
    assert not refused.value.retryable
    assert store.costs.control(user)["suspended"]["by"] == "system"
    store.reserve_tokens(other, 2000, 1024)
    store.set_suspended(user, None, "管理员")
    store.reserve_tokens(user, 2000, 1024)
    store.close()


def test_grants_extend_the_account_limit_and_errors_are_ledgered(project):
    store = store_for(project)
    user = store.create("加额度", "hash")["user_id"]
    with store.db:
        store.db.execute(
            "UPDATE account_quota SET used_tokens=? WHERE user_id=?", (FREE_TOKENS, user)
        )
    with pytest.raises(QuotaExceeded):
        store.reserve_tokens(user, 100, 512)
    store.grant_tokens(user, 10_000, "管理员")
    assert store.quota(user)["limit"] == FREE_TOKENS + 10_000
    call, _ = store.reserve_tokens(user, 100, 512)
    store.settle_tokens(call, None, None, rejected=True, error="http_429")
    call, _ = store.reserve_tokens(user, 100, 512)
    store.settle_tokens(call, None, None, error="cancelled")
    spend = store.costs.spend(0)
    assert spend["calls"] == 2 and spend["errors"] == 1
    assert store.costs.error_kinds(0) == {"http_429": 1, "cancelled": 1}
    items, total = store.list_accounts("加")
    assert total == 1 and items[0]["quota"]["bonus"] == 10_000
    store.close()


async def test_concurrency_gate_queues_in_order_and_gives_up_after_waiting():
    limit = [1]
    gate = ConcurrencyGate(lambda: limit[0], 0.2)
    await gate.acquire()
    waiter = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    assert gate.snapshot() == {"active": 1, "waiting": 1, "limit": 1}
    gate.release()
    await waiter
    assert gate.active == 1
    with pytest.raises(ModelBusy):
        await gate.acquire()
    # Raising the limit live lets waiters through.
    late = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    limit[0] = 2
    gate.dispatch()
    await late
    assert gate.active == 2
    cancelled = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert gate.snapshot()["waiting"] == 0
    gate.release()
    gate.release()
    assert gate.active == 0


async def test_metered_calls_hold_a_gate_slot_until_they_settle(project):
    store = store_for(project)
    user = store.create("并发", "hash")["user_id"]
    gate = ConcurrencyGate(lambda: 1, 0.05)
    release = asyncio.Event()

    class Slow:
        async def chat(self, messages, tools):
            await release.wait()
            return ModelResponse(text="ok", input_tokens=10, output_tokens=5)

    first = asyncio.create_task(MeteredModel(Slow(), store, user, gate).chat([], []))
    await asyncio.sleep(0.01)
    assert gate.active == 1
    with pytest.raises(ModelBusy):
        await MeteredModel(Slow(), store, user, gate).chat([], [])
    release.set()
    await first
    assert gate.active == 0
    assert store.quota(user)["used"] == 15
    # A refused reservation must not keep the slot.
    store.costs.manual_pause("维护", "管理员")
    with pytest.raises(SitePaused):
        await MeteredModel(Slow(), store, user, gate).chat([], [])
    assert gate.active == 0
    store.close()


def client(app, ip="203.0.113.9"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 40000)),
        base_url="https://testserver",
        headers=HEADERS,
    )


async def register(browser, name):
    response = await browser.post(
        "/api/account/register",
        json={"username": name, "password": "test-pass123", "accept_privacy": True},
    )
    assert response.status_code == 201
    return response


async def test_paused_site_turns_chat_into_a_retryable_refusal(project):
    class FakeModel:
        async def chat(self, messages, tools):
            return ModelResponse(text="测试回复", input_tokens=100, output_tokens=10)

    def factory(**kwargs):
        return create_runtime(**{**kwargs, "provider": "demo", "model": FakeModel()})

    app = create_web_app(root=project, public_origin="https://testserver", runtime_factory=factory)
    async with app.router.lifespan_context(app), client(app) as browser:
        await register(browser, "暂停中")
        await browser.get("/api/session")
        store = store_for(project)
        store.costs.manual_pause("维护", "管理员")
        reply = await browser.post("/api/chat", json={"message": "你好"})
        if reply.status_code == 200:
            last = reply.json()["messages"][-1]
            assert last["status"] == "quota_exhausted" and "暂停" in last["text"]
        else:
            assert reply.status_code == 503
            assert reply.json()["detail"]["code"] == "model_paused"
        assert store.quota(store.credentials("暂停中")[0]["user_id"])["used"] == 0
        store.close()


async def test_admin_console_is_hidden_from_everyone_but_named_admins(project, tmp_path):
    status = tmp_path / "monitor-status.json"
    status.write_text('{"generated_at": 1, "checks": []}', encoding="utf-8")
    app = create_web_app(
        root=project,
        public_origin="https://testserver",
        admin_users="管理员甲, ",
        monitor_token=TOKEN,
        monitor_status=status,
    )
    async with (
        app.router.lifespan_context(app),
        client(app) as admin,
        client(app, "203.0.113.10") as user,
        client(app, "203.0.113.11") as stranger,
        client(app, "127.0.0.1") as local,
    ):
        # Anyone: health answers, nothing else.
        health = await stranger.get("/healthz")
        assert health.status_code == 200 and health.json() == {"status": "ok"}
        assert (await stranger.get("/api/ops/metrics")).status_code == 404
        wrong = await stranger.get("/api/ops/metrics", headers={"Authorization": "Bearer x"})
        assert wrong.status_code == 404
        # The right token from a remote address is still refused; the monitor runs on-host.
        remote = await stranger.get(
            "/api/ops/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert remote.status_code == 404
        metrics = await local.get("/api/ops/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        assert metrics.status_code == 200 and "errors" in metrics.json()
        assert (await stranger.get("/admin")).status_code == 303
        assert (await stranger.get("/api/admin/overview")).status_code == 404

        await register(user, "普通用户")
        assert (await user.get("/admin")).status_code == 404
        assert (await user.get("/api/admin/overview")).status_code == 404
        assert (await user.post("/api/admin/models/pause", json={})).status_code == 404

        await register(admin, "管理员甲")
        page = await admin.get("/admin")
        assert page.status_code == 200 and "admin.js" in page.text
        overview = (await admin.get("/api/admin/overview")).json()
        assert overview["admin"] == "管理员甲"
        assert overview["monitor"] == {"generated_at": 1, "checks": []}
        assert len(overview["hourly"]) == 24
        assert overview["system"]["accounts"] == 2

        # Settings: validated, stored, audited, resettable.
        bad = await admin.put("/api/admin/settings", json={"max_concurrent_calls": -1})
        assert bad.status_code == 422 and bad.json()["detail"]["field"] == "max_concurrent_calls"
        unknown = await admin.put("/api/admin/settings", json={"evil": 1})
        assert unknown.status_code == 422
        saved = await admin.put(
            "/api/admin/settings", json={"daily_token_budget": 123_456, "max_concurrent_calls": 2}
        )
        assert saved.json()["settings"]["daily_token_budget"] == 123_456
        overview = (await admin.get("/api/admin/overview")).json()
        assert overview["site"]["concurrency"]["limit"] == 2
        assert overview["settings"]["overrides"] == {
            "daily_token_budget": 123_456,
            "max_concurrent_calls": 2,
        }
        assert overview["audit"][0]["action"] == "update_settings"
        reset = await admin.post("/api/admin/settings/reset")
        assert reset.json()["settings"]["daily_token_budget"] == 3_000_000  # config.yaml default

        # A state change without the page's headers is refused before it reaches the API.
        bare = await admin.post(
            "/api/admin/models/pause", json={}, headers={"X-Zhiming-Client": ""}
        )
        assert bare.status_code == 403
        assert (await admin.post("/api/admin/models/pause", json={"reason": "升级"})).json()[
            "paused"
        ]["reason"] == "升级"
        metrics = await local.get("/api/ops/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        assert metrics.json()["paused"]["by"] == "管理员甲"
        assert (await admin.post("/api/admin/models/resume")).json() == {"paused": None}

        # Accounts: list, suspend, grant, end logins.
        listed = (await admin.get("/api/admin/accounts", params={"q": "普通"})).json()
        assert listed["total"] == 1
        target = listed["items"][0]["user_id"]
        assert (await admin.post(f"/api/admin/accounts/{target}/suspend", json={})).json()
        store = store_for(project)
        assert store.costs.control(target)["suspended"]["reason"] == "管理员暂停"
        with pytest.raises(AccountSuspended):
            store.reserve_tokens(target, 100, 512)
        await admin.post(f"/api/admin/accounts/{target}/unsuspend")
        granted = await admin.post(f"/api/admin/accounts/{target}/grant", json={"tokens": 5000})
        assert granted.json()["quota"]["limit"] == FREE_TOKENS + 5000
        assert (await user.get("/api/account")).json()["account"]["quota"]["limit"] == (
            FREE_TOKENS + 5000
        )
        missing = await admin.post("/api/admin/accounts/acct-none/grant", json={"tokens": 1})
        assert missing.status_code == 404
        ended = await admin.post(f"/api/admin/accounts/{target}/logout")
        assert ended.json() == {"ended": 1}
        assert (await user.get("/api/account")).json()["account"] is None
        store.close()


def test_admin_and_monitor_settings_are_checked_at_startup(project):
    with pytest.raises(ValueError, match="监控令牌"):
        create_web_app(root=project, monitor_token="short")
