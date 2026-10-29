"""Accounts: registration, sign-in, cloud-kept records, guest hand-over and account removal."""

import json
import shutil
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from memory.accounts import PRIVACY_VERSION, AccountStore, hash_password, verify_password
from memory.store import Store
from web import ACCOUNT_IDLE, MAX_IDLE, create_web_app

HEADERS = {"X-Zhiming-Client": "web", "Origin": "http://testserver"}
PASSWORD = "abc12345"
BIRTH = {"date": "2001-11-25", "time": "10:11", "location_id": "1803361"}


def client_for(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
    )


@pytest.fixture
async def site(project):
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtimes.append(runtime)
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with app.router.lifespan_context(app):
        async with client_for(app) as client:
            yield client, app, runtimes


async def register(client, username="云端用户", keep=False, **extra):
    return await client.post(
        "/api/account/register",
        json={
            "username": username,
            "password": PASSWORD,
            "accept_privacy": True,
            "keep_guest_records": keep,
            **extra,
        },
    )


async def login(client, username="云端用户", password=PASSWORD, keep=False):
    return await client.post(
        "/api/account/login",
        json={"username": username, "password": password, "keep_guest_records": keep},
    )


async def guest_with_records(client):
    await client.get("/api/session")
    await client.put("/api/birth", json=BIRTH)
    reading = (await client.post("/api/chat", json={"message": "下个月的重心"})).json()
    return reading["reading"]["reading_id"]


def database(project):
    return Store(project / "data/app.db")


def test_passwords_are_salted_scrypt_hashes():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first.startswith("scrypt$") and first != second
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first) and not verify_password("abc12346", first)
    assert not verify_password(PASSWORD, "scrypt$broken") and not verify_password(PASSWORD, "")


async def test_register_keeps_guest_records_and_birth(site, project):
    client, _, runtimes = site
    reading_id = await guest_with_records(client)
    guest_id = runtimes[0].session.user_id
    info = (await client.get("/api/account")).json()
    assert info == {"account": None, "guest": {"readings": 1, "birth": True}}

    created = await register(client, keep=True)
    assert created.status_code == 201
    assert created.json()["account"]["username"] == "云端用户"
    assert created.json()["moved_readings"] == 1
    cookie = created.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert f"Max-Age={ACCOUNT_IDLE}" in cookie

    state = (await client.get("/api/session")).json()
    assert state["account"]["username"] == "云端用户"
    assert state["birth"]["date"] == BIRTH["date"]
    assert [item["reading_id"] for item in state["history"]] == [reading_id]
    assert state["history_total"] == 1
    saved = (await client.get(f"/api/readings/{reading_id}")).json()
    assert saved["question"].startswith("下个月的重心")
    store = database(project)
    try:
        # Nothing is left under the guest identity, and the account has no idle deadline.
        assert store.get_reading(guest_id, reading_id) is None
        assert store.get_web_birth(guest_id) is None
        leases = [row[0] for row in store.db.execute("SELECT user_id FROM web_identities")]
        assert guest_id not in leases
        assert not any(user_id.startswith("acct-") for user_id in leases)
    finally:
        store.close()


async def test_register_without_keeping_deletes_guest_records(site, project):
    client, _, runtimes = site
    reading_id = await guest_with_records(client)
    guest = runtimes[0]
    traces = guest.tracer.user_dir(guest.session.user_id)
    assert traces.exists()
    assert (await register(client)).json()["moved_readings"] == 0
    state = (await client.get("/api/session")).json()
    assert state["history"] == [] and state["birth"]["date"] is None
    assert (await client.get(f"/api/readings/{reading_id}")).status_code == 404
    store = database(project)
    try:
        assert store.recent_readings(guest.session.user_id) == []
        assert store.get_profile(guest.session.user_id) == {"version": 0}
    finally:
        store.close()
    assert not traces.exists()


async def test_account_records_survive_a_restart(project):
    def factory(**kwargs):
        return create_runtime(**kwargs, seed=42)

    first = create_web_app(root=project, runtime_factory=factory)
    async with first.router.lifespan_context(first), client_for(first) as client:
        reading_id = await guest_with_records(client)
        await register(client, keep=True)
        before = (await client.get("/api/session")).json()
        cookies = dict(client.cookies)
    restarted = create_web_app(root=project, runtime_factory=factory)
    async with restarted.router.lifespan_context(restarted), client_for(restarted) as client:
        client.cookies.update(cookies)
        entrance = await client.get("/", follow_redirects=False)
        assert entrance.status_code == 303 and entrance.headers["location"] == "/ask"
        after = (await client.get("/api/session")).json()
        assert after["account"] == before["account"]
        assert after["instance"] != before["instance"]
        assert after["birth"] == before["birth"]
        assert after["birth_version"] == before["birth_version"]
        assert [item["reading_id"] for item in after["history"]] == [reading_id]
        restored = (await client.get(f"/api/readings/{reading_id}")).json()
        assert restored["stale"] is False


async def test_account_rules_and_duplicate_names(site):
    client, _, _ = site
    for body, code in (
        ({"username": "a"}, "invalid_username"),
        ({"username": "有 空格"}, "invalid_username"),
        ({"username": "合规名字", "password": "short1"}, "weak_password"),
        ({"username": "合规名字", "password": "onlyletters"}, "weak_password"),
        ({"username": "合规名字", "accept_privacy": False}, "privacy_consent_required"),
    ):
        response = await client.post(
            "/api/account/register",
            json={"username": "x", "password": PASSWORD, "accept_privacy": True, **body},
        )
        assert response.status_code == 422, body
        assert response.json()["detail"]["code"] == code
    assert (await register(client, "Stan_1")).status_code == 201
    await client.post("/api/account/logout")
    # Names are unique regardless of case and full-width forms.
    taken = await register(client, "ｓｔａｎ_1")
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "username_taken"
    assert (await login(client, "STAN_1")).status_code == 200


async def test_failed_sign_ins_are_limited(site):
    client, _, _ = site
    await register(client)
    await client.post("/api/account/logout")
    for _ in range(5):
        failed = await login(client, password="wrong-pass1")
        assert failed.status_code == 401
        assert failed.json()["detail"] == {
            "code": "invalid_credentials",
            "message": "账号或密码不正确。",
        }
    limited = await login(client)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert limited.json()["detail"]["code"] == "rate_limited"
    unknown = await login(client, "从未注册")
    assert unknown.json()["detail"]["code"] == "invalid_credentials"


async def test_two_browsers_share_an_account_until_the_password_changes(site):
    client, app, _ = site
    await register(client)
    await client.put("/api/birth", json=BIRTH)
    async with client_for(app) as phone:
        assert (await login(phone)).status_code == 200
        shared = (await phone.get("/api/session")).json()
        assert shared["birth"]["date"] == BIRTH["date"]
        reading = (await phone.post("/api/chat", json={"message": "抽一张牌"})).json()
        mine = (await client.get("/api/session")).json()
        assert mine["history"][0]["reading_id"] == reading["reading"]["reading_id"]

        wrong = await client.post(
            "/api/account/password",
            json={"current_password": "not-it-123", "new_password": "newpass123"},
        )
        assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "wrong_password"
        changed = await client.post(
            "/api/account/password",
            json={"current_password": PASSWORD, "new_password": "newpass123"},
        )
        assert changed.json() == {"ok": True, "signed_out_elsewhere": 1}
        refused = await phone.post("/api/chat", json={"message": "再问"})
        assert refused.status_code == 401
        assert refused.json()["detail"]["code"] == "session_expired"
        # Reloading the page there starts a guest session; the account is not reachable.
        assert (await phone.get("/api/session")).json()["account"] is None
    assert (await client.get("/api/session")).json()["account"]["username"] == "云端用户"
    await client.post("/api/account/logout")
    assert (await login(client)).status_code == 401
    assert (await login(client, password="newpass123")).status_code == 200


async def test_logout_and_account_deletion(site, project):
    client, _, runtimes = site
    await register(client)
    await client.put("/api/birth", json=BIRTH)
    await client.post("/api/chat", json={"message": "抽一张牌"})
    user_id = runtimes[-1].session.user_id
    assert user_id.startswith("acct-")
    traces = runtimes[-1].tracer.user_dir(user_id)
    assert traces.exists()

    out = await client.post("/api/account/logout")
    assert out.status_code == 200 and "zhiming_session=" in out.headers["set-cookie"]
    assert (await client.get("/api/account")).json()["account"] is None
    guest = (await client.get("/api/session")).json()
    assert guest["account"] is None and guest["history"] == []
    assert (await client.post("/api/account/logout")).json()["detail"]["code"] == "not_signed_in"

    await login(client)
    assert (await client.get("/api/session")).json()["history_total"] == 1
    refused = await client.post("/api/account/delete", json={"password": "wrong-pass1"})
    assert refused.status_code == 403
    deleted = await client.post("/api/account/delete", json={"password": PASSWORD})
    assert deleted.status_code == 200
    assert (await client.get("/api/account")).json()["account"] is None
    assert (await login(client)).status_code == 401
    store, accounts = database(project), AccountStore(project / "data/app.db")
    try:
        assert store.recent_readings(user_id) == [] and store.get_web_birth(user_id) is None
        assert accounts.get(user_id) is None
        assert accounts.db.execute("SELECT COUNT(*) FROM account_sessions").fetchone()[0] == 0
    finally:
        store.close()
        accounts.close()
    assert not traces.exists()


async def test_guest_cleanup_never_touches_accounts(project, monkeypatch):
    now = [1_800_000_000.0]
    monkeypatch.setattr("web.time.time", lambda: now[0])
    app = create_web_app(root=project, runtime_factory=lambda **k: create_runtime(**k, seed=42))
    async with app.router.lifespan_context(app), client_for(app) as owner:
        await register(owner)
        await owner.post("/api/chat", json={"message": "抽一张牌"})
        async with client_for(app) as guest:
            await guest.get("/api/session")
            await guest.post("/api/chat", json={"message": "抽一张牌"})
            now[0] += MAX_IDLE + 1
            assert (await guest.post("/api/chat", json={"message": "再问"})).status_code == 401
        assert (await owner.get("/api/session")).json()["history_total"] == 1
        # A login unused for its whole lifetime ends; the records stay for the next sign-in.
        now[0] += ACCOUNT_IDLE + 1
        expired = await owner.post("/api/chat", json={"message": "再问"})
        assert expired.json()["detail"]["code"] == "session_expired"
        await login(owner)
        assert (await owner.get("/api/session")).json()["history_total"] == 1


async def test_login_merges_guest_records_and_marks_other_births_stale(project):
    store = database(project)
    try:
        account, guest = "acct-merge", "web-merge"
        own = {**BIRTH, "unknown_time": False}
        other = {**own, "date": "1990-01-01"}
        store.save_web_birth(account, own, 4)
        store.save_web_birth(guest, other, 9)
        store.update_profile_fields(account, {"birth_local_dt": "2001-11-25 10:11"}, "账号")
        store.update_profile_fields(guest, {"birth_local_dt": "1990-01-01 10:11"}, "访客")
        for reading_id, birth in (("same", own), ("other", other)):
            store.db.execute(
                "INSERT INTO readings(reading_id,user_id,session_id,question,question_type,"
                "systems_used,signals_json,output_json,kb_version,profile_version,mode,"
                "created_at,birth_context_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    reading_id,
                    guest,
                    "s",
                    "问",
                    "general",
                    '["bazi"]',
                    "[]",
                    json.dumps({"summary": "答"}),
                    "kb",
                    1,
                    "single",
                    "2026-10-29T00:00:00",
                    json.dumps({"version": 9, "birth": birth}),
                ),
            )
        store.db.commit()
        moved = store.merge_user(guest, account, lambda a, b: a == b)
        assert moved == {"readings": 2, "adopted_birth": False}
        # The account keeps its own birth and profile; readings follow its revision.
        assert store.get_web_birth(account) == (own, 4)
        assert store.get_profile(account)["birth_local_dt"] == "2001-11-25 10:11"
        assert store.get_reading(account, "same")["birth_context_json"]["version"] == 4
        assert store.get_reading(account, "other")["birth_context_json"]["version"] == -1
        assert store.get_profile(guest) == {"version": 0}
        assert store.get_web_birth(guest) is None
    finally:
        store.close()


async def guest_with_two_trace_files(client, runtimes):
    """A guest whose ask and tarot conversations each wrote a trace file."""
    reading_id = await guest_with_records(client)
    await client.post("/api/chat", json={"message": "抽一张牌", "system": "tarot"})
    guest = runtimes[0]
    traces = guest.tracer.user_dir(guest.session.user_id)
    assert len(list(traces.glob("*.jsonl"))) == 2
    return reading_id, guest.session.user_id, traces


def account_count(project):
    accounts = AccountStore(project / "data/app.db")
    try:
        return accounts.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    finally:
        accounts.close()


async def test_a_failed_trace_move_changes_nothing(site, project, monkeypatch):
    client, _, runtimes = site
    reading_id, guest_id, traces = await guest_with_two_trace_files(client, runtimes)
    before = sorted(path.name for path in traces.glob("*.jsonl"))
    real_replace, moves = Path.replace, []

    def second_move_fails(self, target):
        if self.suffix == ".jsonl" and self.parent == traces:
            moves.append(self)
            if len(moves) == 2:
                raise PermissionError("file in use")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", second_move_fails)
    refused = await register(client, keep=True)
    monkeypatch.setattr(Path, "replace", real_replace)
    assert refused.status_code == 503
    assert refused.json()["detail"]["code"] == "records_not_moved"
    # The first file came back, the account was not kept and the guest carries on.
    assert sorted(path.name for path in traces.glob("*.jsonl")) == before
    assert account_count(project) == 0
    state = (await client.get("/api/session")).json()
    assert state["account"] is None and state["history_total"] == 2
    store = database(project)
    try:
        assert store.get_reading(guest_id, reading_id) is not None
        assert guest_id in [r[0] for r in store.db.execute("SELECT user_id FROM web_identities")]
    finally:
        store.close()
    retried = await register(client, keep=True)
    assert retried.status_code == 201 and retried.json()["moved_readings"] == 2
    assert not traces.exists()


async def test_a_failed_merge_removes_the_new_account(site, project, monkeypatch):
    client, _, runtimes = site
    reading_id, guest_id, traces = await guest_with_two_trace_files(client, runtimes)

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "merge_user", locked)
    failed = await register(client, keep=True)
    monkeypatch.undo()
    assert failed.status_code == 500
    assert account_count(project) == 0
    assert len(list(traces.glob("*.jsonl"))) == 2  # moved back
    assert (await client.get("/api/session")).json()["history_total"] == 2
    retried = await register(client, keep=True)
    assert retried.status_code == 201 and retried.json()["moved_readings"] == 2


async def test_unremovable_guest_traces_keep_the_guest_records(site, project, monkeypatch):
    client, _, runtimes = site
    reading_id = await guest_with_records(client)
    guest_id = runtimes[0].session.user_id

    def busy(*args, **kwargs):
        raise PermissionError("trace file in use")

    monkeypatch.setattr("app.shutil.rmtree", busy)
    refused = await register(client)
    monkeypatch.undo()
    assert refused.status_code == 503
    assert refused.json()["detail"]["code"] == "records_not_removed"
    assert account_count(project) == 0
    store = database(project)
    try:
        assert store.get_reading(guest_id, reading_id) is not None
    finally:
        store.close()
    assert (await register(client)).status_code == 201


async def test_a_leftover_guest_trace_directory_is_cleaned_later(site, project, monkeypatch):
    client, _, runtimes = site
    _, guest_id, traces = await guest_with_two_trace_files(client, runtimes)
    real_rmtree = shutil.rmtree

    def busy(path, *args, **kwargs):
        if Path(path) == traces:
            raise PermissionError("directory in use")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("web.shutil.rmtree", busy)
    assert (await register(client, keep=True)).status_code == 201
    assert traces.exists() and not list(traces.glob("*.jsonl"))
    monkeypatch.undo()
    store = database(project)
    try:
        # An already expired lease hands the directory to the regular guest cleanup.
        assert guest_id in store.expired_web_identities(time.time())
    finally:
        store.close()
    await client.get("/api/locations")
    assert not traces.exists()


async def test_deleting_records_never_compacts_in_the_event_loop(project, monkeypatch):
    checkpoints, statements = [], []
    monkeypatch.setattr("web.checkpoint", checkpoints.append)
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtime.store.db.set_trace_callback(statements.append)
        runtimes.append(runtime)
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with app.router.lifespan_context(app), client_for(app) as client:
        await guest_with_records(client)
        await register(client)  # deletes the guest's records
        await client.post("/api/chat", json={"message": "抽一张牌"})
        await client.delete("/api/readings")
        await client.delete("/api/session")
        await client.post("/api/account/delete", json={"password": PASSWORD})
    assert not [s for s in statements if "VACUUM" in s.upper()]
    assert checkpoints  # run in a worker thread instead, and finished before shutdown


async def test_export_states_its_scope_and_the_consent(site):
    client, _, _ = site
    await register(client)
    await client.post("/api/chat", json={"message": "抽一张牌"})
    data = (await client.get("/api/export")).json()
    assert data["format_version"] == 2
    assert "不是备份" in data["scope"]["purpose"]
    assert any("运行日志" in item for item in data["scope"]["excluded"])
    assert data["account"]["username"] == "云端用户"
    assert data["account"]["privacy_version"] == PRIVACY_VERSION
    assert data["account"]["privacy_accepted_at"]
    assert "user_id" not in data["account"]
    (reading,) = data["readings"]
    for key in ("signals", "merge", "specialist_reports", "review_notes", "responses"):
        assert key in reading
