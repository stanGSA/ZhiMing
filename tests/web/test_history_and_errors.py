"""History management, data export, uniform error replies and the privacy notice."""

import asyncio
import json

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from memory.accounts import PRIVACY_VERSION
from web import PAGES, create_web_app

HEADERS = {"X-Zhiming-Client": "web", "Origin": "http://testserver"}


@pytest.fixture
async def browser(project):
    runtimes = []

    def factory(**kwargs):
        runtime = create_runtime(**kwargs, seed=42)
        runtimes.append(runtime)
        return runtime

    app = create_web_app(root=project, runtime_factory=factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client:
            yield client, app, runtimes


async def ask(client, question):
    """A finished tarot reading in its own conversation."""
    await client.post("/api/new", json={"provider": "configured"})
    return (await client.post("/api/chat", json={"message": question})).json()["reading"]


async def test_history_pages_filters_and_searches(browser):
    client, _, _ = browser
    await client.get("/api/session")
    readings = [await ask(client, f"第{n}个问题：工作") for n in range(3)]
    readings.append(await ask(client, "感情 100% 的把握_吗"))
    await client.post("/api/chat", json={"message": "第二张牌具体什么意思？"})

    state = (await client.get("/api/session")).json()
    assert state["history_total"] == 4
    assert state["history"][0]["response_count"] == 1

    first = (await client.get("/api/history?limit=2")).json()
    second = (await client.get("/api/history?limit=2&offset=2")).json()
    assert first["total"] == second["total"] == 4
    listed = [item["reading_id"] for item in first["items"] + second["items"]]
    assert listed == [r["reading_id"] for r in reversed(readings)]

    work = (await client.get("/api/history", params={"q": "工作"})).json()
    assert work["total"] == 3
    # LIKE wildcards in a search are literal characters.
    literal = (await client.get("/api/history", params={"q": "100%"})).json()
    assert [i["reading_id"] for i in literal["items"]] == [readings[-1]["reading_id"]]
    assert (await client.get("/api/history", params={"q": "_吗"})).json()["total"] == 1
    assert (await client.get("/api/history?system=tarot")).json()["total"] == 4
    assert (await client.get("/api/history?system=bazi")).json()["total"] == 0
    bad = await client.get("/api/history?system=unknown")
    assert bad.status_code == 422 and bad.json()["detail"]["message"] == "功能选项无效。"
    assert (await client.get("/api/history?limit=500")).status_code == 422


async def test_deleting_a_reading_removes_its_follow_ups_traces_and_conversation(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    kept = await ask(client, "保留的问题")
    current = await ask(client, "要删除的问题")
    await client.post("/api/chat", json={"message": "第二张牌具体什么意思？"})
    runtime = runtimes[-1]
    traces = runtime.tracer.user_dir(runtime.session.user_id)

    def tagged(reading_id):
        return any(
            json.loads(line).get("reading_id") == reading_id
            for path in traces.glob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
        )

    assert tagged(current["reading_id"]) and tagged(kept["reading_id"])
    deleted = await client.delete(f"/api/readings/{current['reading_id']}")
    assert deleted.json() == {"deleted": [current["reading_id"]]}
    assert (await client.get(f"/api/readings/{current['reading_id']}")).status_code == 404
    assert not tagged(current["reading_id"]) and tagged(kept["reading_id"])
    store = runtimes[-1].store
    assert store.reading_responses(runtime.session.user_id, current["reading_id"]) == []
    state = (await client.get("/api/session")).json()
    # The conversation about the deleted record starts over instead of failing later.
    assert state["reading"] is None and state["messages"] == []
    assert [item["reading_id"] for item in state["history"]] == [kept["reading_id"]]
    missing = await client.delete(f"/api/readings/{current['reading_id']}")
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "not_found"

    await ask(client, "再问一个")
    cleared = (await client.delete("/api/readings")).json()
    assert len(cleared["deleted"]) == 2
    state = (await client.get("/api/session")).json()
    assert state["history"] == [] and state["history_total"] == 0


async def test_records_are_not_deleted_while_a_reading_is_in_progress(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    reading = await ask(client, "进行中")
    started, release = asyncio.Event(), asyncio.Event()
    original = runtimes[-1].turn

    async def slow_turn(message, **options):
        started.set()
        await release.wait()
        return await original(message, **options)

    runtimes[-1].turn = slow_turn
    task = asyncio.create_task(client.post("/api/chat", json={"message": "再抽一张"}))
    await asyncio.wait_for(started.wait(), timeout=3)
    for request in (
        client.delete(f"/api/readings/{reading['reading_id']}"),
        client.delete("/api/readings"),
    ):
        busy = await request
        assert busy.status_code == 409 and busy.json()["detail"]["code"] == "conflict"
    release.set()
    assert (await task).status_code == 200
    assert (await client.delete(f"/api/readings/{reading['reading_id']}")).status_code == 200


async def test_export_contains_everything_entered(browser):
    client, _, _ = browser
    await client.get("/api/session")
    await client.put("/api/birth", json={"date": "2001-11-25", "location_id": "1803361"})
    reading = await ask(client, "导出的问题")
    await client.post("/api/chat", json={"message": "第二张牌具体什么意思？"})
    response = await client.get("/api/export")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["format"] == "zhiming-export" and data["account"] is None
    assert data["birth"]["date"] == "2001-11-25"
    assert data["profile"]["birth_local_dt"] == "2001-11-25"
    assert data["profile_history"]
    (saved,) = data["readings"]
    assert saved["reading_id"] == reading["reading_id"]
    assert saved["question"].startswith("导出的问题") and saved["output"]["summary"]
    assert len(saved["responses"]) == 1 and len(saved["tarot"]["cards"]) == 3


async def test_errors_share_one_shape_and_never_leak_internals(browser, monkeypatch):
    client, _, runtimes = browser
    unknown = await client.get("/api/does-not-exist")
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": {"code": "not_found", "message": "找不到请求的内容。"}}
    page = await client.get("/no-such-page")
    assert page.status_code == 404 and "此路不通" in page.text
    assert (await client.put("/api/history")).json()["detail"]["code"] == "method_not_allowed"

    expired = await client.post("/api/chat", json={"message": "hi"})
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "session_expired"

    await client.get("/api/session")
    for payload, message in (
        ({"message": " "}, "请先写下你的问题"),
        ({}, "问题缺少必填项。"),
        ({"message": "a" * 4001}, "问题过长（最多 4000 个字符）。"),
        ({"message": "hi", "birth": {"date": "1995-01-01", "time": "25:00"}}, "时间格式不正确。"),
        ({"message": "hi", "spread": "seven"}, "牌阵选项无效。"),
    ):
        response = await client.post("/api/chat", json=payload)
        assert response.status_code == 422, payload
        detail = response.json()["detail"]
        assert detail["code"] == "invalid_input" and detail["message"] == message
        assert detail["errors"][0]["message"] == message
    conflict = await client.post("/api/chat", json={"message": "hi", "reading_id": "missing"})
    assert conflict.json()["detail"] == {"code": "not_found", "message": "找不到这份解读。"}

    def broken(*args, **kwargs):
        raise RuntimeError("private database path /secret")

    monkeypatch.setattr(runtimes[-1].store, "reading_page", broken)
    failed = await client.get("/api/history")
    assert failed.status_code == 500
    detail = failed.json()["detail"]
    assert detail["code"] == "internal_error" and "secret" not in failed.text
    assert detail["request_id"] == failed.headers["x-request-id"]
    assert failed.headers["content-security-policy"].startswith("default-src 'self'")


async def test_privacy_notice_is_linked_everywhere(browser):
    client, _, _ = browser
    notice = await client.get("/privacy")
    assert notice.status_code == 200
    assert "隐私说明" in notice.text and PRIVACY_VERSION in notice.text
    assert "style=" not in notice.text
    for section in ("collect", "share", "retention", "rights", "security", "cookies"):
        assert f'id="{section}"' in notice.text
    entrance = (await client.get("/login")).text
    assert 'href="/privacy"' in entrance and 'id="accept-privacy"' in entrance
    assert "筹备中" not in entrance
    for slug in PAGES:
        assert 'href="/privacy"' in (await client.get(f"/{slug}")).text, slug


async def test_deleting_a_shared_record_clears_every_conversation_in_one_step(project):
    runtimes, broken = [], []

    def factory(**kwargs):
        if broken:
            raise RuntimeError("model configuration missing")
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
        tarot = await client.post("/api/chat", json={"message": "下个月的重心", "system": "tarot"})
        reading_id = tarot.json()["reading"]["reading_id"]
        # The ask page follows up on the same record: two conversations now refer to it.
        await client.post(
            "/api/chat", json={"message": "第二张牌具体什么意思？", "reading_id": reading_id}
        )
        assert all(r.session.state.get("active_reading_id") == reading_id for r in runtimes)
        built = len(runtimes)
        broken.append(True)  # rebuilding a runtime now fails, as without a model config
        deleted = await client.delete(f"/api/readings/{reading_id}")
        assert deleted.status_code == 200
        assert len(runtimes) == built  # cleared in memory, nothing rebuilt
        for system in ("auto", "tarot"):
            state = (await client.get(f"/api/session?system={system}")).json()
            assert state["messages"] == [] and state["reading"] is None
        for runtime in runtimes:
            assert not runtime.session.state and runtime.session.pinned_reading_id is None
            # The model's memory note no longer mentions the deleted record.
            notes = [m["content"] for m in runtime.session.messages if m["role"] == "system"]
            assert not any(reading_id in note or "下个月的重心" in note for note in notes)
        broken.clear()
        again = await client.post("/api/chat", json={"message": "抽一张牌", "system": "tarot"})
        assert again.json()["messages"][-1]["status"] == "submit_reading"
