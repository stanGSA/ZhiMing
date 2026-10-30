"""Operator quota management and real-adapter probe behavior, with offline upstream responses."""

import asyncio
import json
import time
import uuid

import httpx
import pytest

from harness.llm import OpenAIModel
from harness.metering import ConcurrencyGate
from memory.accounts import FREE_TOKENS, AccountStore, hash_password
from ops.probe import ProbeService
from web import create_web_app

HEADERS = {"Origin": "https://testserver", "X-Zhiming-Client": "web"}


def test_registration_allowance_is_snapshotted_and_migrated(tmp_path):
    path = tmp_path / "app.db"
    s = AccountStore(path)
    old = s.create("旧账号", "hash")["user_id"]
    with s.db:
        s.db.execute("DROP TABLE account_allowances")  # Database from the previous release.
    s.close()
    s = AccountStore(path)
    s.set_registration_allowance(900_000, "stan")
    new = s.create("新账号", "hash")["user_id"]
    s.set_registration_allowance(0, "stan")
    zero = s.create("零额度", "hash")["user_id"]
    s.close()
    s = AccountStore(path)
    assert s.quota(old)["limit"] == FREE_TOKENS
    assert s.quota(new)["limit"] == 900_000
    assert s.quota(zero)["limit"] == 0
    assert s.registration_allowance() == 0
    listed, _ = s.list_accounts("新账号")
    assert listed[0]["quota"]["limit"] == 900_000
    s.close()


def test_distribution_is_atomic_idempotent_and_excludes_unlimited(tmp_path):
    s = AccountStore(tmp_path / "app.db")
    old = s.create("普通账号", "hash")["user_id"]
    unlimited = s.create("不限账号", "hash")["user_id"]
    s.set_unlimited_quota(unlimited, True, "stan")
    with s.db:
        s.db.execute("UPDATE account_quota SET used_tokens=100 WHERE user_id=?", (old,))
    request = str(uuid.uuid4())
    assert s.distribute_tokens(5000, request, "stan")["recipients"] == 1
    assert s.distribute_tokens(5000, request, "stan")["replayed"]
    assert s.quota(old)["remaining"] == FREE_TOKENS + 5000 - 100
    assert s.costs.control(unlimited)["bonus_tokens"] == 0
    assert s.create("之后注册", "hash")
    assert s.quota(s.credentials("之后注册")[0]["user_id"])["limit"] == FREE_TOKENS
    with pytest.raises(ValueError):
        s.distribute_tokens(100, "not-a-uuid", "stan")
    with pytest.raises(Exception, match="已完成"):
        s.distribute_tokens(6000, request, "stan")
    # A failed audit rolls back every recipient, as well as the idempotency record.
    s.db.execute(
        "CREATE TEMP TRIGGER fail_audit BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'fail'); END"
    )
    before = s.quota(old)
    with pytest.raises(Exception, match="fail"):
        s.distribute_tokens(900, str(uuid.uuid4()), "stan")
    assert s.quota(old) == before
    s.close()


def probe_factory(monkeypatch, handler):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")

    def factory():
        return OpenAIModel(
            "offline-probe",
            timeout=1,
            max_tokens=32,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    return factory


async def test_probe_real_adapter_metering_failures_and_restart(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    store = AccountStore(path, cost_defaults={"daily_token_budget": 10000})
    fail = [False]
    requests = []

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["max_tokens"] == 32 and body["messages"] == [
            {"role": "user", "content": "Reply with OK only."}
        ]
        if fail[0]:
            return httpx.Response(401, json={"error": {"message": "secret-must-not-leak"}})
        return httpx.Response(
            200,
            json={
                "id": "probe",
                "model": "offline-probe",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            },
        )

    gate = ConcurrencyGate(lambda: 1, 0.1)
    config = {"llm": {"provider": "openai", "model": "offline-probe"}}
    service = ProbeService(lambda: store, gate, config, probe_factory(monkeypatch, upstream))
    service.configure(5, "stan")
    assert (await service.run("stan"))["latest"]["status"] == "success"
    assert store.costs.spend(0)["tokens"] == 11 and gate.active == 0
    assert store.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    fail[0] = True
    failed = (await service.run())["latest"]
    assert failed["status"] == "failure" and failed["error"] == "AuthenticationError"
    assert "secret-must-not-leak" not in json.dumps(service.snapshot())
    fail[0] = False
    assert (await service.run())["latest"]["status"] == "success"
    assert len(service.snapshot()["history"]) == 3
    store.costs.manual_pause("维护", "stan")
    assert (await service.run())["latest"]["status"] == "skipped"
    assert len(requests) == 3
    store.costs.manual_resume("stan")
    store.costs.update({"daily_token_budget": 1}, "stan")
    assert (await service.run())["latest"]["error"] == "SiteBudgetExhausted"
    store.close()
    store = AccountStore(path)
    restarted = ProbeService(lambda: store, gate, config)
    assert restarted.snapshot()["interval_min"] == 5
    assert len(restarted.snapshot()["history"]) == 5
    store.close()


async def test_scheduler_and_manual_probe_do_not_overlap(tmp_path, monkeypatch):
    store = AccountStore(tmp_path / "app.db")
    started, release = asyncio.Event(), asyncio.Event()

    async def upstream(request):
        started.set()
        await release.wait()
        return httpx.Response(401, json={"error": {"message": "bad"}})

    service = ProbeService(
        lambda: store,
        ConcurrencyGate(lambda: 1, 0.1),
        {"llm": {"provider": "openai"}},
        probe_factory(monkeypatch, upstream),
    )
    service.configure(1, "stan")
    task = asyncio.create_task(service.schedule())
    await asyncio.wait_for(started.wait(), 2)
    assert (await service.run("stan"))["busy"]
    release.set()
    for _ in range(50):
        if service.snapshot()["latest"]:
            break
        await asyncio.sleep(0.01)
    assert service.snapshot()["latest"]["status"] == "failure"
    assert service.snapshot()["next_at"] > time.time()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    store.close()


async def test_new_admin_endpoints_permissions_validation_and_defaults(project):
    store = AccountStore(project / "data/app.db")
    admin = store.create("stan", hash_password("test-pass123"))["user_id"]
    app = create_web_app(root=project, public_origin="https://testserver", admin_ids=[admin])
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://testserver", headers=HEADERS
        ) as browser,
    ):
        for method, url, body in [
            ("PUT", "/api/admin/registration-allowance", {"tokens": 1000}),
            (
                "POST",
                "/api/admin/accounts/distribute",
                {"tokens": 1000, "request_id": str(uuid.uuid4())},
            ),
            ("PUT", "/api/admin/model-probe", {"minutes": 5}),
            ("POST", "/api/admin/model-probe/run", {}),
        ]:
            assert (await browser.request(method, url, json=body)).status_code == 404
        assert (
            await browser.post(
                "/api/account/login", json={"username": "stan", "password": "test-pass123"}
            )
        ).status_code == 200
        assert (
            await browser.put("/api/admin/registration-allowance", json={"tokens": -1})
        ).status_code == 422
        assert (
            await browser.put("/api/admin/registration-allowance", json={"tokens": True})
        ).status_code == 422
        assert (
            await browser.put("/api/admin/registration-allowance", json={"tokens": 600000})
        ).json()["tokens"] == 600000
        assert (await browser.get("/api/account")).json()["registration_free_tokens"] == 600000
        assert (await browser.put("/api/admin/model-probe", json={"minutes": 0})).json()[
            "interval_min"
        ] == 0
        assert (
            await browser.put("/api/admin/model-probe", json={"minutes": -1})
        ).status_code == 422
        assert (await browser.post("/api/admin/model-probe/run", json={})).json()["latest"][
            "status"
        ] == "failure"  # Demo config cannot pretend to be a real model.
        request = {"tokens": 1000, "request_id": str(uuid.uuid4())}
        assert (await browser.post("/api/admin/accounts/distribute", json=request)).json()[
            "recipients"
        ] == 1
        assert (await browser.post("/api/admin/accounts/distribute", json=request)).json()[
            "replayed"
        ]
        assert (
            await browser.put(
                "/api/admin/registration-allowance",
                json={"tokens": 1},
                headers={"Origin": "https://evil.example"},
            )
        ).status_code == 403
        snapshot = (await browser.get("/api/admin/overview")).json()
        assert snapshot["registration_free_tokens"] == 600000
        assert snapshot["model_probe"]["latest"]["error"] == "ValueError"
    store.close()
