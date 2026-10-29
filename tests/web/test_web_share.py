"""Public HTTPS preserves session isolation, with an optional password for private sharing."""

import httpx
import pytest

pytest.importorskip("fastapi")

from web import create_web_app

ORIGIN = "https://friends.example.com"
PASSWORD = "test-password-not-a-real-secret"


@pytest.mark.parametrize(
    "settings",
    [
        {"share_password": PASSWORD},
        {"public_origin": "http://friends.example.com"},
        {"public_origin": ORIGIN + "/path"},
        {"public_origin": "http://friends.example.com", "share_password": PASSWORD},
        {"public_origin": ORIGIN + "/path", "share_password": PASSWORD},
        {"public_origin": "https://*.example.com", "share_password": PASSWORD},
        {"public_origin": "https://user@example.com", "share_password": PASSWORD},
        {"public_origin": ORIGIN, "share_password": "short"},
        {"public_origin": ORIGIN, "share_password": ""},
    ],
)
def test_sharing_requires_exact_https_origin_and_strong_password(settings):
    with pytest.raises(ValueError):
        create_web_app(**settings)


async def test_all_shared_routes_require_credentials_before_creating_runtime():
    def forbidden_factory(**kwargs):
        pytest.fail("Unauthenticated visitors must not create a runtime")

    app = create_web_app(
        public_origin=ORIGIN, share_password=PASSWORD, runtime_factory=forbidden_factory
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
        for path in ("/", "/static/app.js", "/api/session", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 401
            assert response.headers["www-authenticate"].startswith("Basic ")
            assert response.headers["cache-control"] == "no-store"
        for authorization in ("Basic !!!", "Basic ü", "Bearer abc", "Basic ZnJpZW5kOndyb25n"):
            # HTTP headers are bytes; malformed non-ASCII payloads must also fail closed.
            response = await client.post(
                "/api/chat", headers={b"authorization": authorization.encode()}, json={}
            )
            assert response.status_code == 401
        assert (await client.get("/", auth=("other", PASSWORD))).status_code == 401
        assert (await client.get("/", auth=("friend", PASSWORD))).status_code == 200


@pytest.mark.parametrize("share_password", [None, PASSWORD])
async def test_shared_chat_secure_cookie_origins_and_separate_browsers(project, share_password):
    app = create_web_app(root=project, public_origin=ORIGIN, share_password=share_password)
    auth = ("friend", share_password) if share_password else None
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
            auth=auth,
            headers={"Origin": ORIGIN, "X-Zhiming-Client": "web"},
        ) as client,
    ):
        for path in ("/", "/login", "/privacy", "/static/login.js"):
            page = await client.get(path)
            assert page.status_code == 200
            assert "www-authenticate" not in page.headers
        session = await client.get("/api/session?provider=demo")
        assert session.status_code == 200
        cookie = session.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
        response = await client.post("/api/chat", json={"message": "抽一张牌"})
        assert response.status_code == 200
        assert response.json()["reading"]
        for origin in ("https://evil.example", "http://127.0.0.1:8766"):
            assert (
                await client.post("/api/new", json={}, headers={"Origin": origin})
            ).status_code == 403
        assert (
            await client.post("/api/new", json={}, headers={"X-Zhiming-Client": ""})
        ).status_code == 403
        assert (await client.get("/", headers={"Host": "evil.example"})).status_code == 400
        # The optional sharing gate remains independent of the browser session.
        assert (await client.get("/api/session", auth=None)).status_code == (
            401 if share_password else 200
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, auth=auth
        ) as friend:
            other = await friend.get("/api/session?provider=demo")
            assert other.json()["history"] == []
            reading_id = response.json()["reading"]["reading_id"]
            assert (await friend.get(f"/api/readings/{reading_id}")).status_code == 404


async def test_public_account_registration_and_login_without_sharing_password(project):
    app = create_web_app(root=project, public_origin=ORIGIN)
    credentials = {"username": "公开注册用户", "password": "account-pass123"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=ORIGIN,
            headers={"Origin": ORIGIN, "X-Zhiming-Client": "web"},
        ) as client,
    ):
        created = await client.post(
            "/api/account/register", json={**credentials, "accept_privacy": True}
        )
        assert created.status_code == 201
        assert created.json()["account"]["username"] == credentials["username"]
        assert "Secure" in created.headers["set-cookie"]
        assert (await client.post("/api/account/logout")).status_code == 200
        signed_in = await client.post("/api/account/login", json=credentials)
        assert signed_in.status_code == 200
        assert signed_in.json()["account"]["username"] == credentials["username"]
        assert "www-authenticate" not in signed_in.headers
