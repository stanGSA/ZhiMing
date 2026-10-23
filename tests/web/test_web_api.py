"""Browser API integration against the real, offline Agent and a temporary database."""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from harness.models import ModelResponse, ToolCall
from plugins.tarot.draw import draw_tarot
from tests.plugins.test_name_dream_daily import with_birth
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

    async def slow_turn(message, **options):
        started.set()
        await release.wait()
        return await original(message, **options)

    runtimes[-1].turn = slow_turn
    task = asyncio.create_task(client.post("/api/chat", json={"message": "抽一张牌"}))
    await asyncio.wait_for(started.wait(), timeout=3)
    assert (await client.get("/api/session")).json()["busy"] is True
    assert (await client.post("/api/new", json={})).status_code == 409
    assert (await client.delete("/api/session")).status_code == 409
    assert (await client.post("/api/chat", json={"message": "再问"})).status_code == 409
    release.set()
    assert (await task).status_code == 200

    async def broken_turn(message, **options):
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


async def test_tarot_picks_decide_the_cards(browser):
    client, _, _ = browser
    await client.get("/api/session")
    for bad in (
        {"spread": "three_card", "picks": [1, 2]},
        {"spread": "three_card", "picks": [1, 1, 2]},
        {"spread": "single", "picks": [78]},
        {"spread": "single", "picks": [0], "system": "auto"},
    ):
        body = {"message": "最近的状态", "system": "tarot", **bad}
        assert (await client.post("/api/chat", json=body)).status_code == 422
    result = (
        await client.post(
            "/api/chat",
            json={
                "message": "最近的状态",
                "system": "tarot",
                "spread": "three_card",
                "picks": [70, 5, 33],
            },
        )
    ).json()
    drawn = result["reading"]["tarot"]
    assert drawn["picks"] == [70, 5, 33]
    assert result["tarot_round"] is None  # answered with cards: nothing left open
    expected = draw_tarot(drawn["spread"], drawn["question"], drawn["seed"], [70, 5, 33])
    assert [c["card_id"] for c in drawn["cards"]] == [c["card_id"] for c in expected["cards"]]
    # Both the session's reading and a record opened from 足迹 carry the record's question.
    assert result["reading"]["question"].startswith("最近的状态")
    saved = (await client.get(f"/api/readings/{result['reading']['reading_id']}")).json()
    assert saved["question"] == result["reading"]["question"]


async def test_clarifying_reply_continues_the_round_with_the_latest_picks(browser, scripted_model):
    client, _, runtimes = browser
    await client.get("/api/session")

    def response(name, **arguments):
        return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=arguments)])

    runtimes[-1].model = scripted_model(
        [
            response("start_reading", question="A 还是 B？"),
            response("ask_user", question="A 和 B 分别是什么？"),
            response("draw_tarot", spread="decision", question="A 还是 B？"),
            response("ask_user", question="还想看哪一张？"),
        ]
    )
    body = {"system": "tarot", "spread": "decision"}
    first = await client.post(
        "/api/chat", json={**body, "message": "A 还是 B？", "picks": [1, 2, 3]}
    )
    assert first.json()["messages"][-1]["status"] == "ask_user"
    # The round stays open on the session, so a reloaded page can continue it.
    assert first.json()["tarot_round"] == {
        "question": "A 还是 B？",
        "spread": "decision",
        "picks": [1, 2, 3],
    }
    reply = {**body, "message": "A 是留在原公司，B 是去新公司", "picks": [60, 8, 34]}
    second = (await client.post("/api/chat", json=reply)).json()
    # The reading started in the first turn draws in the second, with the choice sent last.
    assert runtimes[-1].session.state["tarot_result"]["picks"] == [60, 8, 34]
    assert second["tarot_round"]["question"] == "A 还是 B？"
    assert second["tarot_round"]["picks"] == [60, 8, 34]
    renewed = (await client.post("/api/new", json={"provider": "configured"})).json()
    assert renewed["tarot_round"] is None


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


@pytest.mark.parametrize("change_timezone", [False, True])
async def test_daily_birth_form_keeps_consultation_timezone(
    browser, scripted_model, change_timezone
):
    client, _, runtimes = browser
    await client.get("/api/session")
    runtime = runtimes[-1]
    with_birth(runtime, consultation_tz="America/Los_Angeles")
    runtime.clock = lambda: datetime(2026, 10, 20, 16, 1, tzinfo=UTC)
    zone = "America/New_York" if change_timezone else "America/Los_Angeles"
    question = "本次咨询按America/New_York时间看今天运势" if change_timezone else "看看今天运势"

    def response(name, **arguments):
        return ModelResponse(tool_calls=[ToolCall(id=name, name=name, arguments=arguments)])

    responses = [response("start_reading", question=question)]
    if change_timezone:
        responses.append(
            response("update_profile", field="consultation_tz", value=zone, evidence=question)
        )
    responses.extend(
        [
            response("daily_fortune", date="2026-10-20"),
            response("ask_user", question="还有想了解的方面吗？"),
        ]
    )
    runtime.model = scripted_model(responses)
    result = await client.post(
        "/api/chat",
        json={
            "message": question,
            "birth": {"date": "1996-05-10", "time": "08:30", "location_id": "1803361"},
        },
    )
    assert result.status_code == 200
    assert "出生钟表时区为Asia/Shanghai" in runtime.session.user_messages[-1]
    daily = runtime.session.state.get("daily_result")
    assert daily is not None, result.json()
    assert daily["tz"] == zone and daily["date"] == "2026-10-20"
    assert runtime.session.calendar_timezone == zone
    profile = runtime.store.get_profile(runtime.session.user_id)
    assert profile["tz"] == "Asia/Shanghai" and profile["consultation_tz"] == zone


async def test_entrance_and_consultation_pages(browser):
    client, _, _ = browser
    entrance = await client.get("/")
    assert entrance.status_code == 200 and "叩门问道" in entrance.text
    assert entrance.headers["cache-control"] == "no-store"
    for slug in ("ask", "bazi", "astro", "tarot", "name", "dream", "daily"):
        page = await client.get(f"/{slug}")
        assert page.status_code == 200
        assert f'data-page="{slug}"' in page.text
        assert "style=" not in page.text  # The CSP forbids inline styles.
    await client.get("/api/session")
    returning = await client.get("/", follow_redirects=False)
    assert returning.status_code == 303 and returning.headers["location"] == "/ask"
    assert "叩门问道" in (await client.get("/login")).text


async def test_new_systems_hint_the_method_and_keep_birth_private(browser):
    client, _, runtimes = browser
    await client.get("/api/session")
    birth = {"date": "1995-03-21", "time": "14:30", "place": "中国浙江杭州"}
    for system, label in (("dream", "解梦"), ("name", "姓名五格"), ("daily", "每日运势")):
        response = await client.post(
            "/api/chat", json={"message": "抽一张牌", "system": system, "birth": birth}
        )
        assert response.status_code == 200
        sent = runtimes[-1].session.user_messages[-1]
        assert f"本次希望使用{label}来解读" in sent
        assert ("1995-03-21" in sent) is (system == "daily")
        assert response.json()["messages"][-1]["system"] == system
        await client.post("/api/new", json={"provider": "configured"})


async def test_demo_does_not_answer_dreams_names_or_days_with_cards(browser):
    client, _, _ = browser
    await client.get("/api/session?provider=demo")
    for system in ("dream", "name", "daily"):
        data = (
            await client.post("/api/chat", json={"message": "梦见掉牙", "system": system})
        ).json()
        assert data["messages"][-1]["status"] == "demo_unsupported"
        assert data["reading"] is None


async def test_name_grids_are_calculated_without_a_model(browser):
    client, _, _ = browser
    await client.get("/api/session")
    result = (await client.post("/api/name", json={"surname": "陈", "given": "知远"})).json()[
        "result"
    ]
    assert result["grids"] == {"天格": 17, "人格": 24, "地格": 25, "外格": 18, "总格": 41}
    assert result["elements"] == {
        "天格": "金",
        "人格": "火",
        "地格": "土",
        "外格": "金",
        "总格": "木",
    }
    assert [c["form"] for c in result["chars"]] == ["陳", "知", "遠"]
    assert result["sancai"]["key"] == "金火土"
    for payload in (
        {"surname": "Li", "given": "明"},
        {"surname": "陈", "given": ""},
        {"surname": "陈", "given": "知远", "forms": {"杰": "傑"}},
    ):
        assert (await client.post("/api/name", json=payload)).status_code == 422


async def test_almanac_day_and_personal_ten_gods(browser):
    client, _, _ = browser
    await client.get("/api/session")
    plain = (await client.post("/api/almanac", json={"date": "2026-10-22"})).json()
    assert (plain["year_pillar"], plain["month_pillar"], plain["day_pillar"]) == (
        "丙午",
        "戊戌",
        "己巳",
    )
    assert plain["lunar_date"] == "九月十三" and plain["weekday"] == "四"
    assert plain["next_term"] == {"name": "霜降", "date": "2026-10-23"}
    assert plain["day_element"] == "土" and "黄" in plain["day_element_note"]
    assert plain["ten_god"] is None and plain["day_master"] is None
    assert [d["date"] for d in plain["week"]][::6] == ["2026-10-19", "2026-10-25"]
    birth = {"date": "1994-03-18", "time": "08:30", "location_id": "6607381"}
    personal = (
        await client.post("/api/almanac", json={"date": "2026-10-22", "birth": birth})
    ).json()
    assert personal["day_master"] == "癸水" and personal["ten_god"] == "七杀"
    assert [d["ten_god"] for d in personal["week"]] == [
        "正财",
        "偏财",
        "正官",
        "七杀",
        "正印",
        "偏印",
        "劫财",
    ]
    assert (await client.post("/api/almanac", json={"date": "1800-01-01"})).status_code == 422


async def test_birth_profile_is_saved_for_every_page(browser):
    client, _, _ = browser
    await client.get("/api/session")
    birth = {"date": "1994-03-18", "time": "08:30", "location_id": "6607381"}
    chart = (await client.post("/api/chart", json={"system": "bazi", "birth": birth})).json()
    assert chart["chart"]["result"]["day_master"] == "癸水"
    same = (await client.put("/api/birth", json=birth)).json()
    assert same["chart"] is not None and same["birth"]["place"].endswith("西湖区")
    changed = (await client.put("/api/birth", json={**birth, "time": "09:30"})).json()
    assert changed["chart"] is None
    assert (await client.get("/api/session")).json()["birth"]["time"] == "09:30"
    assert (await client.put("/api/birth", json={"time": "09:30"})).status_code == 422
