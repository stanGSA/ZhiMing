"""User journeys across feature windows, changed birth forms and saved follow-ups."""

import asyncio
import json

import httpx

from harness.models import ModelResponse, ToolCall
from tests.plugins.test_name_dream_daily import with_birth
from tests.web.test_web_api import HEADERS
from tests.web.test_web_api import browser as browser

BIRTH = {"date": "2001-11-25", "time": "10:11", "location_id": "1803361"}


def call(name, **arguments):
    return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=arguments)])


def results(runtime, name):
    return [
        json.loads(m["content"])
        for m in runtime.session.messages
        if m["role"] == "tool" and m["tool_call_id"] == name
    ]


async def test_current_form_overrides_old_profile_and_rejects_stale_arguments(
    browser, scripted_model
):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    with_birth(runtime)
    runtime.model = scripted_model(
        [
            call("start_reading", question="按表单看八字"),
            call("compute_bazi", birth_local="1996-05-10 08:30"),
            call("compute_bazi"),
            call("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    data = (
        await client.post(
            "/api/chat", json={"message": "按表单看八字", "system": "bazi", "birth": BIRTH}
        )
    ).json()
    assert data["messages"][-1]["status"] == "ask_user"
    stale, current = results(runtime, "compute_bazi")
    assert not stale["ok"] and "表单不一致" in stale["error"]
    assert current["ok"]
    assert current["data"]["pillars"] == data["chart"]["result"]["pillars"]
    stored = runtime.store.get_calculation(
        "bazi", runtime.session.user_id, runtime.session.state["bazi_id"]
    )
    assert stored["input"]["birth_local"] == "2001-11-25 10:11"
    assert runtime.session.profile["birth_local_dt"] == "2001-11-25 10:11"
    assert runtime.session.birth_binding["profile"]["location_id"] == "1803361"

    previous = runtime.session.state["active_reading_id"]
    runtime.model = scripted_model(
        [
            call("start_reading", question="更正出生时间"),
            call("compute_bazi"),
            call("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    changed = (
        await client.post(
            "/api/chat",
            json={"message": "更正出生时间", "system": "bazi", "birth": {**BIRTH, "time": "12:30"}},
        )
    ).json()
    assert runtime.session.state["active_reading_id"] != previous
    assert (
        results(runtime, "compute_bazi")[-1]["data"]["pillars"]
        == changed["chart"]["result"]["pillars"]
    )


async def test_unknown_time_and_missing_location_never_reuse_previous_birth(
    browser, scripted_model
):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    with_birth(runtime)
    runtime.model = scripted_model(
        [
            call("start_reading", question="未知时辰看三柱"),
            call("compute_bazi"),
            call("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    await client.post(
        "/api/chat",
        json={
            "message": "未知时辰看三柱",
            "system": "bazi",
            "birth": {**BIRTH, "unknown_time": True},
        },
    )
    computed = results(runtime, "compute_bazi")[-1]
    assert computed["ok"] and "time" not in computed["data"]["pillars"]
    runtime.model = scripted_model(
        [
            call("start_reading", question="地点还没选择"),
            call("compute_bazi"),
            call("ask_user", question="请在表单选择出生地点"),
        ]
    )
    await client.post(
        "/api/chat",
        json={
            "message": "地点还没选择",
            "system": "bazi",
            "birth": {"date": BIRTH["date"], "unknown_time": True},
        },
    )
    computed = results(runtime, "compute_bazi")[-1]
    assert computed["data"]["status"] == "needs_input"
    assert not runtime.session.profile["location_id"]


async def test_unfinished_tarot_does_not_block_bazi_or_reset_other_features(
    browser, scripted_model
):
    client, _, runtimes = browser
    await client.get("/api/session?system=tarot")
    tarot = runtimes[-1]
    tarot.max_steps = 2
    tarot.model = scripted_model(
        [
            call("start_reading", question="抽一张牌"),
            call("draw_tarot", question="抽一张牌", spread="single"),
        ]
    )
    pending = (
        await client.post(
            "/api/chat", json={"message": "抽一张牌", "system": "tarot", "spread": "single"}
        )
    ).json()
    assert pending["messages"][-1]["failure"]["reason"] == "step_limit"
    draw = tarot.session.state["tarot_result"]
    await client.get("/api/session?system=bazi")
    bazi = runtimes[-1]
    bazi.model = scripted_model(
        [
            call("start_reading", question="看八字"),
            call("compute_bazi"),
            call("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    data = (
        await client.post("/api/chat", json={"message": "看八字", "system": "bazi", "birth": BIRTH})
    ).json()
    assert results(bazi, "start_reading")[-1]["ok"]
    assert data["messages"][-1]["status"] == "ask_user"
    assert all(m["system"] == "bazi" for m in data["messages"])
    await client.post("/api/new", json={"system": "bazi", "provider": "demo"})
    restored = (await client.get("/api/session?system=tarot")).json()
    assert restored["messages"] == pending["messages"]
    assert tarot.session.state["tarot_result"] == draw


async def test_feature_locks_are_independent_but_forget_checks_all_features(browser):
    client, _, runtimes = browser
    await client.get("/api/session?system=tarot")
    tarot = runtimes[-1]
    started, release = asyncio.Event(), asyncio.Event()
    original = tarot.turn

    async def slow(message, **kwargs):
        started.set()
        await release.wait()
        return await original(message, **kwargs)

    tarot.turn = slow
    pending = asyncio.create_task(
        client.post("/api/chat", json={"message": "抽一张牌", "system": "tarot"})
    )
    try:
        await asyncio.wait_for(started.wait(), 3)
        await client.get("/api/session?system=bazi")
        response = await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})
        assert response.status_code == 200 and response.json()["chart"]
        assert not (await client.get("/api/session?system=bazi")).json()["busy"]
        assert (await client.delete("/api/session?system=bazi")).status_code == 409
    finally:
        release.set()
        await pending
    await client.delete("/api/session?system=bazi")
    for system in ("auto", "tarot", "bazi"):
        data = (await client.get(f"/api/session?system={system}")).json()
        assert data["messages"] == data["history"] == []
        assert data["chart"] is None and data["birth"]["date"] is None


async def test_shared_birth_keeps_separate_chart_slots(browser):
    client, _, _ = browser
    await client.get("/api/session")
    bazi = (await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})).json()[
        "chart"
    ]
    astro = (await client.post("/api/chart", json={"system": "astro", "birth": BIRTH})).json()[
        "chart"
    ]
    assert (await client.get("/api/session?system=bazi")).json()["chart"] == bazi
    assert (await client.get("/api/session?system=astro")).json()["chart"] == astro
    await client.put("/api/birth?system=bazi", json={**BIRTH, "time": "12:30"})
    assert (await client.get("/api/session?system=astro")).json()["chart"] is None


async def test_history_followup_binds_a_after_b_and_keeps_response_history(browser):
    client, app, _ = browser
    await client.get("/api/session?system=tarot")
    a = (
        await client.post(
            "/api/chat", json={"message": "抽一张牌", "system": "tarot", "spread": "single"}
        )
    ).json()["reading"]
    await client.post("/api/new", json={"system": "tarot", "provider": "demo"})
    b = (await client.post("/api/chat", json={"message": "抽三张牌", "system": "tarot"})).json()[
        "reading"
    ]
    viewed = (await client.get(f"/api/readings/{a['reading_id']}?system=tarot")).json()
    assert viewed["output"] == a["output"]
    assert (await client.get("/api/session?system=tarot")).json()["reading"]["reading_id"] == b[
        "reading_id"
    ]
    follow = (
        await client.post(
            "/api/chat",
            json={
                "message": "第一张牌具体什么意思？",
                "system": "tarot",
                "reading_id": a["reading_id"],
            },
        )
    ).json()["reading"]
    assert follow["reading_id"] == a["reading_id"] and follow["tarot"] == a["tarot"]
    assert len(follow["responses"]) == 1
    saved = (await client.get(f"/api/readings/{a['reading_id']}")).json()
    assert saved["output"] == a["output"]
    assert saved["responses"][0]["output"] == follow["output"]
    assert saved["responses"][0]["question"].startswith("第一张牌")
    assert len((await client.get("/api/session?system=tarot")).json()["history"]) == 2
    assert (
        await client.post(
            "/api/chat", json={"message": "解释", "system": "bazi", "reading_id": a["reading_id"]}
        )
    ).status_code == 422
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
    ) as stranger:
        await stranger.get("/api/session")
        assert (
            await stranger.post(
                "/api/chat", json={"message": "解释", "reading_id": a["reading_id"]}
            )
        ).status_code == 404


async def test_history_followup_guard_cannot_switch_or_recompute(browser, scripted_model):
    client, _, runtimes = browser
    await client.get("/api/session?system=tarot")
    a = (
        await client.post(
            "/api/chat", json={"message": "抽一张牌", "system": "tarot", "spread": "single"}
        )
    ).json()["reading"]
    await client.post("/api/new", json={"system": "tarot", "provider": "demo"})
    b = (await client.post("/api/chat", json={"message": "抽三张牌", "system": "tarot"})).json()[
        "reading"
    ]
    runtime = runtimes[-1]
    runtime.model = scripted_model(
        [
            call("read_reading", reading_id=b["reading_id"]),
            call("draw_tarot", question="追问", spread="single"),
            call("ask_user", question="想了解原记录的哪个方面？"),
        ]
    )
    await client.post(
        "/api/chat",
        json={"message": "追问这张牌", "system": "tarot", "reading_id": a["reading_id"]},
    )
    assert results(runtime, "read_reading")[-1]["code"] == "reading_mismatch"
    assert results(runtime, "draw_tarot")[-1]["code"] == "followup_only"
    assert runtime.session.state["tarot_result"] == a["tarot"]
    index = runtime.session.state["question_message_index"]
    assert runtime.session.user_messages[index].startswith("追问这张牌")


async def test_crisis_pause_survives_feature_switch_and_new_chat(browser):
    client, _, _ = browser
    await client.get("/api/session?system=tarot")
    response = await client.post("/api/chat", json={"message": "我想自杀", "system": "tarot"})
    assert response.json()["messages"][-1]["status"] == "crisis_support"
    await client.post("/api/new", json={"system": "bazi", "provider": "demo"})
    chart = (await client.post("/api/chart", json={"system": "bazi", "birth": BIRTH})).json()
    assert chart["code"] == "safety_confirmation_required"


async def test_correcting_birth_keeps_an_unfinished_auto_tarot_draw(browser, scripted_model):
    client, _, runtimes = browser
    await client.get("/api/session")
    runtime = runtimes[-1]
    runtime.model = scripted_model(
        [
            call("start_reading", question="结合八字和塔罗看工作", systems=["bazi", "tarot"]),
            call("compute_bazi"),
            call("draw_tarot", question="工作", spread="single"),
            call("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    await client.post(
        "/api/chat", json={"message": "结合八字和塔罗看工作，抽一张牌", "birth": BIRTH}
    )
    original = runtime.session.state["tarot_result"]
    reading_id = runtime.session.state["active_reading_id"]
    runtime.model = scripted_model(
        [call("compute_bazi"), call("ask_user", question="还有想了解的方面吗？")]
    )
    await client.post(
        "/api/chat",
        json={"message": "更正出生时刻，保持原来的牌面", "birth": {**BIRTH, "time": "12:30"}},
    )
    assert runtime.session.state["active_reading_id"] == reading_id
    assert runtime.session.state["tarot_result"] == original
    assert runtime.session.state["tarot_drawn"]
    assert runtime.session.state["bazi_result"]["input"]["birth_local"] == "2001-11-25 12:30"
    assert all(
        s["ref_id"] in runtime.session.state["allowed_refs"]
        for s in runtime.session.state["signals"]
    )


async def test_bound_form_reaches_birth_specialist_without_expanding_other_profiles(
    browser, scripted_model
):
    client, _, runtimes = browser
    await client.get("/api/session?system=bazi")
    runtime = runtimes[-1]
    runtime.model = scripted_model([call("ask_user", question="还有想了解的方面吗？")])
    await client.post(
        "/api/chat", json={"message": "按表单看八字", "system": "bazi", "birth": BIRTH}
    )
    common = dict(
        messages=[], state={}, parent_call_id=None, budget=None, continue_prompt="continue"
    )
    tarot = runtime.session.spawn("tarot", "tarot", profile={}, **common)
    assert tarot.birth_binding is None and tarot.profile == {}
    bazi = runtime.session.spawn("bazi", "bazi", profile={"birth_local_dt": "old"}, **common)
    assert bazi.birth_binding == runtime.session.birth_binding
    from harness.guard import Guard

    Guard(runtime.registry).check(ToolCall(id="profile", name="get_profile", arguments={}), bazi)
    assert bazi.profile == {"birth_local_dt": "2001-11-25 10:11"}
