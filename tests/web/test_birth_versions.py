"""Birth revisions protect current results while preserving original historical evidence."""

import asyncio
import json

import pytest

from harness.models import ModelResponse, ToolCall
from tests.plugins.test_astro_bazi_integration import draft
from tests.web.test_feature_sessions import BIRTH, call
from tests.web.test_web_api import browser as browser


class ReadingModel:
    def __init__(self, runtime, gate=None):
        self.runtime = runtime
        self.step = 0
        self.gate = gate

    async def chat(self, messages, tools):
        step = self.step
        self.step += 1
        if step == 0:
            return call("start_reading", question="我的性格与工作方向")
        if step == 1:
            return call("compute_bazi")
        if step == 2:
            if self.gate:
                self.gate[0].set()
                await self.gate[1].wait()
            return ModelResponse(
                tool_calls=[
                    ToolCall(id="submit", name="submit_reading", arguments=draft(self.runtime))
                ]
            )
        return call("ask_user", question="请确认当前生辰后继续。")


async def complete_reading(client, runtimes, gate=None):
    await client.get("/api/session?system=bazi")
    runtimes[-1].model = ReadingModel(runtimes[-1], gate)
    return await client.post(
        "/api/chat",
        json={
            "message": "我的性格与工作方向",
            "system": "bazi",
            "birth": BIRTH,
            "expected_birth_version": 0,
        },
    )


async def test_rechart_invalidates_current_reading_and_preserves_history(browser):
    client, _, runtimes = browser
    original = (await complete_reading(client, runtimes)).json()
    assert original["messages"][-1]["status"] == "submit_reading"
    reading = original["reading"]
    changed = (
        await client.post(
            "/api/chart",
            json={
                "system": "bazi",
                "birth": {**BIRTH, "time": "12:30"},
                "expected_birth_version": original["birth_version"],
            },
        )
    ).json()
    assert changed["birth_version"] == 2
    assert changed["chart"]["result"]["input"]["birth_local"].endswith("12:30")
    assert changed["reading"] is None and changed["birth_stale"]
    assert all(m["stale"] for m in changed["messages"])
    runtime = next(r for r in runtimes if r.session.id == changed["session_epoch"])
    assert "bazi_result" not in runtime.session.state
    assert not runtime.session.cache and runtime.session.birth_binding is None
    assert runtime.store.get_profile(runtime.session.user_id)["birth_local_dt"].endswith("12:30")
    saved = (await client.get(f"/api/readings/{reading['reading_id']}")).json()
    assert saved["output"] == reading["output"]
    assert saved["birth_context"]["birth"]["time"] == "10:11"
    assert saved["stale"] and saved["historical"]


async def test_old_tab_missing_revision_and_aba_cannot_overwrite_birth(browser):
    client, _, _ = browser
    await client.get("/api/session")
    initial = (await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})).json()
    changed = await client.put(
        "/api/birth",
        json={**BIRTH, "time": "12:30"},
        headers={"X-Zhiming-Birth-Version": str(initial["birth_version"])},
    )
    assert changed.status_code == 200
    for payload in (
        {"system": "astro", "birth": BIRTH, "expected_birth_version": 1},
        {"system": "astro", "birth": BIRTH},
    ):
        response = await client.post("/api/chart", json=payload)
        assert response.status_code == 409
    returned = await client.put("/api/birth", json=BIRTH, headers={"X-Zhiming-Birth-Version": "2"})
    assert returned.json()["birth_version"] == 3
    stale = await client.post(
        "/api/chat",
        json={
            "system": "bazi",
            "birth": BIRTH,
            "message": "继续",
            "expected_birth_version": 1,
        },
    )
    assert stale.status_code == 409
    assert (await client.get("/api/session")).json()["birth_version"] == 3


async def test_birth_task_rejects_mutation_but_allows_parallel_same_birth(browser):
    client, _, runtimes = browser
    entered, release = asyncio.Event(), asyncio.Event()
    pending = asyncio.create_task(complete_reading(client, runtimes, (entered, release)))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        changed = await client.post(
            "/api/chart",
            json={
                "system": "astro",
                "birth": {**BIRTH, "time": "12:30"},
                "expected_birth_version": 1,
            },
        )
        assert changed.status_code == 409
        assert changed.json()["detail"]["code"] == "birth_in_use"
        same = await client.post(
            "/api/chart",
            json={
                "system": "astro",
                "birth": BIRTH,
                "expected_birth_version": 1,
            },
        )
        assert same.status_code == 200 and same.json()["chart"]
    finally:
        release.set()
        finished = await pending
    assert finished.json()["messages"][-1]["status"] == "submit_reading"
    retry = await client.put(
        "/api/birth", json={**BIRTH, "time": "12:30"}, headers={"X-Zhiming-Birth-Version": "1"}
    )
    assert retry.status_code == 200


@pytest.mark.parametrize("outcome", ["error", "cancel"])
async def test_failed_or_cancelled_task_releases_birth_registration(browser, outcome):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    entered, release = asyncio.Event(), asyncio.Event()

    async def fail(*args, **kwargs):
        entered.set()
        await release.wait()
        raise RuntimeError("synthetic failure")

    runtime.turn = fail
    pending = asyncio.create_task(
        client.post(
            "/api/chat",
            json={
                "system": "bazi",
                "message": "我的性格",
                "birth": BIRTH,
            },
        )
    )
    await asyncio.wait_for(entered.wait(), 5)
    if outcome == "cancel":
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        release.set()
        await pending
    response = await client.put(
        "/api/birth", json={**BIRTH, "time": "12:30"}, headers={"X-Zhiming-Birth-Version": "1"}
    )
    assert response.status_code == 200


async def test_historical_followup_uses_snapshot_and_does_not_change_shared_birth(browser):
    client, _, runtimes = browser
    original = (await complete_reading(client, runtimes)).json()["reading"]
    await client.put(
        "/api/birth", json={**BIRTH, "time": "12:30"}, headers={"X-Zhiming-Birth-Version": "1"}
    )
    runtime = runtimes[-1]
    # Historical follow-ups are submitted against the stored calculation, not today's form.
    from tests.conftest import ScriptedModel

    saved = runtime.store.get_reading(runtime.session.user_id, original["reading_id"])
    runtime.model = ScriptedModel([call("submit_reading", **saved["output_json"])])
    response = await client.post(
        "/api/chat",
        json={
            "system": "bazi",
            "message": "解释原记录",
            "reading_id": original["reading_id"],
            "birth": BIRTH,
            "expected_birth_version": 0,
        },
    )
    data = response.json()
    assert data["messages"][-1]["status"] == "submit_reading"
    assert data["birth"]["time"] == "12:30" and data["birth_version"] == 2
    assert data["reading"]["birth_context"]["birth"]["time"] == "10:11"
    assert data["reading"]["stale"] and data["reading"]["historical"]
    assert len(data["reading"]["responses"]) == 1


async def test_normalized_same_birth_keeps_version_and_other_chart(browser):
    client, _, _ = browser
    await client.get("/api/session")
    first = (
        await client.post(
            "/api/chart",
            json={
                "system": "bazi",
                "birth": {**BIRTH, "unknown_time": True},
            },
        )
    ).json()
    second = (
        await client.post(
            "/api/chart",
            json={
                "system": "astro",
                "birth": {**BIRTH, "time": "", "unknown_time": False},
                "expected_birth_version": first["birth_version"],
            },
        )
    ).json()
    assert second["birth_version"] == first["birth_version"]
    assert (await client.get("/api/session?system=bazi")).json()["chart"] == first["chart"]


async def test_submit_rechecks_version_after_async_policy_check(browser):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    runtime.model = ReadingModel(runtime)

    class Policy:
        async def check(self, texts, session):
            # Simulate a future mutation path after the first submit check. The store
            # must still reject the write, even if a caller forgets task registration.
            session.birth_version_valid = lambda: False

    runtime.session.policy_judge = Policy()
    response = (
        await client.post(
            "/api/chat",
            json={
                "system": "bazi",
                "message": "我的性格与工作方向",
                "birth": BIRTH,
            },
        )
    ).json()
    submit = [
        json.loads(m["content"])
        for m in runtime.session.messages
        if m["role"] == "tool" and m["tool_call_id"] == "submit"
    ]
    assert submit[-1]["code"] == "birth_version_conflict"
    assert response["history"] == [] and response["reading"] is None


async def test_two_tabs_cannot_both_commit_against_the_same_revision(browser):
    client, _, _ = browser
    await client.get("/api/session")
    await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/chart",
                json={
                    "system": system,
                    "birth": {**BIRTH, "time": clock},
                    "expected_birth_version": 1,
                },
            )
            for system, clock in (("bazi", "12:30"), ("astro", "14:00"))
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    latest = (await client.get("/api/session")).json()
    assert latest["birth_version"] == 2
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert latest["birth"] == winner["birth"]


async def test_forget_keeps_revision_monotonic_and_rejects_old_tabs(browser):
    client, _, _ = browser
    await client.get("/api/session")
    before = (await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})).json()
    deleted = (await client.delete("/api/session?system=bazi")).json()
    assert deleted["birth_version"] > before["birth_version"]
    assert deleted["session_revision"] > before["session_revision"]
    stale = await client.post(
        "/api/chart",
        json={
            "system": "astro",
            "birth": BIRTH,
            "expected_birth_version": before["birth_version"],
        },
    )
    assert stale.status_code == 409
    assert (await client.get("/api/session")).json()["birth"]["date"] is None
