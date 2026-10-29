"""Guest requests cannot construct a configured model, including direct API requests."""

import httpx
import pytest

from app import create_runtime
from web import create_web_app

SYSTEMS = ("auto", "bazi", "astro", "tarot", "name", "dream", "daily")
HEADERS = {"Origin": "https://testserver", "X-Zhiming-Client": "web"}


@pytest.fixture
async def public_site(project):
    providers = []

    def factory(**kwargs):
        providers.append(kwargs.get("provider"))
        # Real account access is exercised without sending a paid request.
        return create_runtime(**{**kwargs, "provider": "demo"}, seed=42)

    app = create_web_app(root=project, public_origin="https://testserver", runtime_factory=factory)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver", headers=HEADERS
        ) as client,
    ):
        yield client, app, providers


async def test_guests_stay_offline_across_direct_links_and_api_switches(public_site):
    client, _, providers = public_site
    for system in SYSTEMS:
        state = await client.get(f"/api/session?provider=configured&system={system}")
        assert state.status_code == 200
        assert state.json()["provider"] == "demo"
        assert state.json()["account"] is None
        blocked = await client.post("/api/new", json={"provider": "configured", "system": system})
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "account_required"
        assert (await client.get(f"/api/session?system={system}")).json()["provider"] == "demo"
    assert providers and set(providers) == {"demo"}
    reading = await client.post("/api/chat", json={"message": "抽一张牌", "system": "tarot"})
    assert reading.status_code == 200 and reading.json()["reading"]
    assert set(providers) == {"demo"}
    # A returning guest still sees the account entrance on the home page.
    entrance = await client.get("/", follow_redirects=False)
    assert entrance.status_code == 200
    assert 'id="tab-account"' in entrance.text


async def test_accounts_can_use_models_and_logout_returns_to_offline(public_site):
    client, _, providers = public_site
    await client.get("/api/session?provider=configured")
    assert providers == ["demo"]
    credentials = {"username": "模型账号", "password": "model-pass123"}
    created = await client.post(
        "/api/account/register", json={**credentials, "accept_privacy": True}
    )
    assert created.status_code == 201
    for system in SYSTEMS:
        state = await client.get(f"/api/session?system={system}")
        assert state.json()["provider"] == "configured"
        assert state.json()["account"]["username"] == credentials["username"]
    assert providers.count(None) == len(SYSTEMS)
    home = await client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert (await client.post("/api/new", json={"provider": "demo"})).json()["provider"] == "demo"
    assert (await client.post("/api/new", json={"provider": "configured"})).json()[
        "provider"
    ] == "configured"
    token = client.cookies.get("zhiming_session")
    assert token
    assert (await client.post("/api/account/logout")).status_code == 200
    calls = len(providers)
    offline = await client.get("/api/session?provider=configured")
    assert offline.json()["provider"] == "demo" and offline.json()["account"] is None
    assert providers[calls:] == ["demo"]
    client.cookies.clear()
    client.cookies.set("zhiming_session", token)
    assert (await client.get("/api/session")).json()["provider"] == "demo"
    assert (await client.post("/api/account/login", json=credentials)).status_code == 200
    assert (await client.get("/api/session")).json()["provider"] == "configured"
