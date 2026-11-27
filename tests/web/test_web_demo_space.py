"""Offline demo-only & iframe embedding support (e.g. Hugging Face Spaces)."""

import httpx
import pytest

pytest.importorskip("fastapi")

from web import create_web_app

HF_ORIGIN = "https://stangsa-zhiming.hf.space"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"extra_hosts": ("",)},
        {"extra_hosts": ("bad host",)},
        {"embed_ancestors": ("http://huggingface.co",)},
        {"embed_ancestors": ("https://huggingface.co; script-src *",)},
    ],
)
def test_demo_space_rejects_invalid_host_or_ancestor_config(kwargs):
    with pytest.raises(ValueError):
        create_web_app(**kwargs)


async def test_demo_only_forces_demo_provider_and_allows_hf_iframe(project):
    seen_providers = []

    def tracking_factory(**kwargs):
        from app import create_runtime

        seen_providers.append(kwargs.get("provider"))
        return create_runtime(**kwargs, seed=42)

    app = create_web_app(
        root=project,
        runtime_factory=tracking_factory,
        demo_only=True,
        extra_hosts=("*.hf.space",),
        embed_ancestors=("https://huggingface.co", "https://*.hf.space"),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=HF_ORIGIN,
            headers={"Origin": HF_ORIGIN, "X-Zhiming-Client": "web"},
        ) as client,
    ):
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"ok": True, "mode": "demo"}
        csp = health.headers["content-security-policy"]
        assert "frame-ancestors 'self' https://huggingface.co https://*.hf.space;" in csp

        # Even requesting provider=configured must stay pinned to demo.
        session = await client.get("/api/session?provider=configured")
        assert session.status_code == 200
        assert session.json()["provider"] == "demo"
        cookie = session.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=none" in cookie

        # Switching mode via /api/new cannot escape demo_only either.
        switched = await client.post("/api/new", json={"provider": "configured", "system": "tarot"})
        assert switched.status_code == 200
        assert switched.json()["provider"] == "demo"
        assert seen_providers and all(p == "demo" for p in seen_providers)

        # Untrusted Host header is still rejected.
        assert (await client.get("/healthz", headers={"Host": "evil.example"})).status_code == 400
