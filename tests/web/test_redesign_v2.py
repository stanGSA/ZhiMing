"""Tests for v2 redesign fixes: sky almanac fields, lunar calendar APIs, and CSP/DOM parity."""

import httpx
import pytest

pytest.importorskip("fastapi")

from app import create_runtime
from web import create_web_app

HEADERS = {"X-Zhiming-Client": "web", "Origin": "http://testserver"}


@pytest.fixture
async def client(project):
    app = create_web_app(root=project, runtime_factory=lambda **kw: create_runtime(**kw, seed=42))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=HEADERS
        ) as c:
            yield c


async def test_almanac_includes_western_sky_snapshot(client):
    await client.get("/api/session")
    res = await client.post("/api/almanac", json={"date": "2026-11-27"})
    assert res.status_code == 200
    data = res.json()
    assert data["year_pillar"] == "丙午"
    assert data["month_pillar"] == "己亥"
    assert data["day_pillar"] == "乙巳"
    sky = data["sky"]
    assert sky is not None
    assert sky["sun_sign_zh"] == "射手座"
    assert sky["moon_phase_zh"] == "亏凸月"
    assert sky["mercury_status"] == "水星顺行"
    assert data["birth_preview"] is None

    with_birth = await client.post(
        "/api/almanac",
        json={
            "date": "2026-11-27",
            "birth": {
                "date": "1994-03-18",
                "time": "08:30",
                "location_id": "6607381",
                "gender": "female",
            },
        },
    )
    assert with_birth.status_code == 200
    preview = with_birth.json()["birth_preview"]
    assert preview is not None
    assert preview["bazi"]["pillars"]["year"] == "甲戌"
    assert preview["bazi"]["pillars"]["day"] == "癸卯"
    assert preview["astro"]["sun_sign_zh"] == "双鱼座"
    assert len(preview["astro"]["planets"]) == 10
    assert "08:30" not in str(preview)


async def test_lunar_calendar_endpoints_round_trip_and_leap_month(client):
    months_resp = await client.get("/api/calendar/lunar-year", params={"year": 2025})
    assert months_resp.status_code == 200
    months = months_resp.json()["months"]
    leap = [m for m in months if m["leap"]]
    assert len(leap) == 1
    assert leap[0]["month"] == -6
    assert leap[0]["label"] == "闰六月"

    to_solar = await client.get(
        "/api/calendar/lunar-to-solar", params={"year": 2025, "month": -6, "day": 15}
    )
    assert to_solar.status_code == 200
    assert to_solar.json()["solar"] == "2025-08-08"
    assert to_solar.json()["lunar_label"] == "乙巳年闰六月十五"

    to_lunar = await client.get("/api/calendar/solar-to-lunar", params={"date": "2025-08-08"})
    assert to_lunar.status_code == 200
    body = to_lunar.json()
    assert (body["year"], body["month"], body["day"], body["leap"]) == (2025, -6, 15, True)
    assert body["lunar_label"] == "乙巳年闰六月十五"

    bad = await client.get(
        "/api/calendar/lunar-to-solar", params={"year": 2025, "month": -5, "day": 1}
    )
    assert bad.status_code == 422


async def test_login_and_ask_pages_csp_and_required_production_hooks(client):
    login_html = (await client.get("/login")).text
    assert "style=" not in login_html
    assert "<script>" not in login_html
    for token in (
        'id="tab-guest"',
        'id="tab-account"',
        'id="tab-register"',
        'id="signed-in"',
        'id="keep-guest-row"',
        'id="account-error"',
        'id="astrolabe"',
    ):
        assert token in login_html

    ask_html = (await client.get("/ask")).text
    assert "style=" not in ask_html
    assert "<script>" not in ask_html
    for token in (
        'id="today-moon-phase"',
        'id="today-sun-sign"',
        'id="today-mercury"',
        'id="today-foot"',
        'id="enroll-saved"',
        'id="birth-dots"',
        'id="reading"',
        'id="provider"',
    ):
        assert token in ask_html
