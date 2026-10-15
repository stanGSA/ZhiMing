"""Browser API integration against the real, offline Agent and a temporary database."""

import asyncio

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from web import BirthInfo, create_web_app

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


async def test_page_and_chat_followup(browser):
    client, _, _ = browser
    page = await client.get("/")
    assert page.status_code == 200
    assert "观天时" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    initial = await client.get("/api/session")
    assert "HttpOnly" in initial.headers["set-cookie"]
    assert initial.json()["messages"] == []
    response = await client.post("/api/chat", json={"message": "下个月适合跳槽吗？"})
    assert response.status_code == 200
    data = response.json()
    assert data["messages"][-1]["status"] == "submit_reading"
    assert len(data["reading"]["tarot"]["cards"]) == 3
    assert data["reading"]["output"]["advice"]
    original = data["reading"]
    followup = await client.post("/api/chat", json={"message": "第二张牌具体什么意思？"})
    reading = followup.json()["reading"]
    assert reading["reading_id"] == original["reading_id"]
    assert reading["tarot"]["cards"] == original["tarot"]["cards"]
    assert "第2张" in reading["output"]["summary"]
    refreshed = (await client.get("/api/session")).json()
    assert len(refreshed["messages"]) == 4
    assert refreshed["reading"] == reading


async def test_new_chat_history_isolation_and_forget(browser):
    client, app, _ = browser
    await client.get("/api/session")
    result = (await client.post("/api/chat", json={"message": "抽一张牌"})).json()
    reading_id = result["reading"]["reading_id"]
    new = (await client.post("/api/new", json={"provider": "demo"})).json()
    assert new["messages"] == []
    assert new["reading"] is None
    assert len(new["history"]) == 1
    assert (await client.get(f"/api/readings/{reading_id}")).status_code == 200
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
    ) as stranger:
        assert (await stranger.post("/api/chat", json={"message": "hi"})).status_code == 401
        assert (await stranger.get("/api/session")).json()["history"] == []
        assert (await stranger.get(f"/api/readings/{reading_id}")).status_code == 404
    deleted = (await client.delete("/api/session")).json()
    assert deleted["messages"] == deleted["history"] == []
    assert deleted["birth"]["date"] is None
    assert (await client.get(f"/api/readings/{reading_id}")).status_code == 404


async def test_birth_is_passed_as_user_evidence(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    birth = {
        "date": "1995-03-21",
        "time": "14:30",
        "unknown_time": True,
        "place": "中国浙江杭州",
        "gender": "female",
    }
    response = await client.post("/api/chat", json={"message": "抽一张牌", "birth": birth})
    assert response.status_code == 200
    actual = runtimes[-1].session.user_messages[-1]
    assert "公历 1995-03-21" in actual
    assert "出生时间不确定" in actual
    assert "14:30" not in actual
    assert "中国浙江杭州" in actual
    assert "性别为女" in actual
    assert response.json()["birth"]["time"] == ""


async def test_validation_and_local_origin(browser):
    client, _, _ = browser
    await client.get("/api/session")
    for payload in (
        {"message": " "},
        {"message": "a" * 4001},
        {"message": "hi", "birth": {"date": "2999-01-01"}},
        {"message": "hi", "birth": {"time": "12:00"}},
        {"message": "hi", "birth": {"date": "1995-01-01", "time": "25:00"}},
        {"message": "hi", "system": "unknown"},
    ):
        assert (await client.post("/api/chat", json=payload)).status_code == 422
    assert (
        await client.post(
            "/api/chat", json={"message": "hi"}, headers={"Origin": "https://example.com"}
        )
    ).status_code == 403
    assert (
        await client.post("/api/chat", json={"message": "hi"}, headers={"X-Zhiming-Client": ""})
    ).status_code == 403
    assert (await client.get("/", headers={"Host": "example.com"})).status_code == 400


async def test_demo_without_birth_requests_data_instead_of_inventing_a_chart(browser):
    client, _, _ = browser
    await client.get("/api/session")
    await client.post("/api/new", json={"provider": "demo"})
    result = await client.post("/api/chat", json={"message": "看我的星盘", "system": "astro"})
    assert result.status_code == 200
    assert result.json()["chart"] is None
    assert "出生日期" in result.json()["messages"][-1]["text"]
    assert "未调用模型解读" in result.json()["messages"][-1]["text"]


async def test_parallel_mutations_rejected_and_error_recovers(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    started, release = asyncio.Event(), asyncio.Event()
    original = runtimes[-1].turn

    async def slow_turn(message):
        started.set()
        await release.wait()
        return await original(message)

    runtimes[-1].turn = slow_turn
    task = asyncio.create_task(client.post("/api/chat", json={"message": "抽一张牌"}))
    await asyncio.wait_for(started.wait(), timeout=3)
    assert (await client.get("/api/session")).json()["busy"] is True
    assert (await client.post("/api/new", json={})).status_code == 409
    assert (await client.delete("/api/session")).status_code == 409
    assert (await client.post("/api/chat", json={"message": "再问"})).status_code == 409
    release.set()
    assert (await task).status_code == 200

    async def broken_turn(message):
        raise RuntimeError("private upstream diagnostic")

    runtimes[-1].turn = broken_turn
    result = (await client.post("/api/chat", json={"message": "继续"})).json()
    assert result["busy"] is False
    assert result["messages"][-1]["status"] == "error"
    assert "private upstream" not in result["messages"][-1]["text"]


def test_birth_evidence_does_not_invent_time():
    birth = BirthInfo(date="1995-03-21", place="杭州")
    assert "出生时间不确定" in birth.evidence()
    assert "00:00" not in birth.evidence()
    from common.input_evidence import supported_birth

    known = BirthInfo(date="2001-11-25", time="10:11", location_id="1803361")
    assert supported_birth("2001-11-25T10:11:00", known.evidence(), True)


async def test_offline_bootstrap_without_configured_model(project):
    def factory(**kwargs):
        if kwargs.get("provider") != "demo":
            raise ValueError("Missing model configuration")
        return create_runtime(**kwargs)

    app = create_web_app(root=project, runtime_factory=factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as client:
            assert (await client.get("/api/session")).status_code == 503
            offline = await client.get("/api/session?provider=demo")
            assert offline.status_code == 200
            assert offline.json()["provider"] == "demo"
            result = await client.post("/api/chat", json={"message": "抽一张牌"})
            assert result.json()["messages"][-1]["status"] == "submit_reading"


async def test_region_cascade_and_deterministic_birth_chart(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    provinces = (await client.get("/api/locations?parent=CN")).json()["options"]
    anhui = next(p for p in provinces if p["name"] == "安徽省")
    cities = (await client.get("/api/locations", params={"parent": anhui["id"]})).json()["options"]
    fuyang = next(c for c in cities if c["name"] == "阜阳市")
    counties = (await client.get("/api/locations", params={"parent": fuyang["id"]})).json()[
        "options"
    ]
    linquan = next(c for c in counties if c["name"] == "临泉县")
    location = (await client.get("/api/locations/" + linquan["id"])).json()
    assert [p["name"] for p in location["path"]] == ["中国", "安徽省", "阜阳市", "临泉县"]
    birth = {"date": "2001-11-25", "time": "10:11", "gender": "male", "location_id": linquan["id"]}
    data = (await client.post("/api/chart", json={"system": "bazi", "birth": birth})).json()
    assert data["chart"]["result"]["pillars"] == {
        "year": "辛巳",
        "month": "己亥",
        "day": "壬辰",
        "time": "乙巳",
    }
    assert data["chart"]["result"]["day_master"] == "壬水"
    assert runtimes[-1].session.model_calls == 0
    assert (await client.get("/api/session")).json()["chart"] == data["chart"]
    astro = (await client.post("/api/chart", json={"system": "astro", "birth": birth})).json()
    assert len(astro["chart"]["result"]["planets"]) == 10
    assert astro["chart"]["result"]["asc"] is not None
    unknown = {**birth, "unknown_time": True}
    astro = (await client.post("/api/chart", json={"system": "astro", "birth": unknown})).json()
    assert astro["chart"]["result"]["asc"] is None
    assert astro["chart"]["result"]["cusps"] is None
    assert (
        await client.post(
            "/api/chart", json={"system": "bazi", "birth": {"location_id": "not-a-place"}}
        )
    ).status_code == 422


async def test_offline_bazi_chat_and_tarot_spread(browser):
    client, _, _ = browser
    await client.get("/api/session")
    await client.post("/api/new", json={"provider": "demo"})
    result = (
        await client.post(
            "/api/chat",
            json={
                "message": "我的八字是什么",
                "system": "bazi",
                "birth": {"date": "2001-11-25", "time": "10:11", "location_id": "1803361"},
            },
        )
    ).json()
    assert result["busy"] is False
    assert "辛巳" in result["messages"][-1]["text"]
    assert result["reading"] is None
    assert result["chart"]["result"]["dayun"] is None
    tarot = (
        await client.post(
            "/api/chat", json={"message": "给我一个思考线索", "system": "tarot", "spread": "single"}
        )
    ).json()
    assert len(tarot["reading"]["tarot"]["cards"]) == 1


async def test_xinjiang_clock_not_assumed(browser):
    client, _, _ = browser
    await client.get("/api/session")
    from common.regions import region_data

    location = next(
        n
        for n in region_data()["nodes"].values()
        if n.get("location", {}).get("tz") == "Asia/Urumqi"
    )
    birth = {"date": "2001-11-25", "time": "10:11", "location_id": location["id"]}
    response = (await client.post("/api/chart", json={"system": "bazi", "birth": birth})).json()
    assert response["chart"] is None
    assert response["code"] == "confirm_clock_timezone"
    birth["clock_tz"] = "Asia/Shanghai"
    response = (await client.post("/api/chart", json={"system": "bazi", "birth": birth})).json()
    assert response["chart"]["result"]["pillars"]["time"] == "乙巳"
