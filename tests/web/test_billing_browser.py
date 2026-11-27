"""Real-browser tests for standalone /billing page, recharge modal and quota guidance."""

from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")
sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
uvicorn = pytest.importorskip("uvicorn")

from app import create_runtime  # noqa: E402
from harness.models import ModelResponse  # noqa: E402
from memory.accounts import AccountStore  # noqa: E402
from memory.billing import AfdianConfig  # noqa: E402
from tests.conftest import ScriptedModel  # noqa: E402
from web import create_web_app  # noqa: E402


def make_billing_config() -> AfdianConfig:
    return AfdianConfig.from_env(
        {
            "AFDIAN_CREATOR_URL": "https://afdian.com/a/zhiming_ai",
            "AFDIAN_USER_ID": "ae4a6bfeea3211f1aea952540025c377",
            "AFDIAN_API_TOKEN": "test-api-token-secret",
            "AFDIAN_WEBHOOK_SECRET": "test-secret-0123456789abcdef",
            "AFDIAN_TIP_PLAN_ID": "f2dce26eea3311f18be1525400c8052f",
            "AFDIAN_PLUS_PLAN_ID": "cf5d2596ea3411f19a8052540025c377",
            "AFDIAN_PRO_PLAN_ID": "ff1c165cea3411f1bcc952540025c377",
        }
    )


@pytest.fixture
def billing_site(project):
    config = make_billing_config()

    def factory(**kwargs):
        return create_runtime(
            **kwargs,
            seed=42,
            model=ScriptedModel([ModelResponse(text="ok")]),
        )

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_web_app(root=project, runtime_factory=factory, afdian_config=config),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            pytest.fail("网页服务未能启动")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", project
    server.should_exit = True
    thread.join(10)


@pytest.fixture
def chromium():
    with sync_api.sync_playwright() as playwright:
        browser = None
        last_error = None
        for kwargs in ({}, {"channel": "chrome"}, {"channel": "msedge"}):
            try:
                browser = playwright.chromium.launch(**kwargs)
                break
            except sync_api.Error as error:
                last_error = error
        if browser is None:
            pytest.skip(f"Chromium 不可用：{last_error}")
        yield browser
        browser.close()


def test_billing_page_modal_and_exhausted_quota_flow(billing_site, chromium):
    base, project = billing_site
    context = chromium.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
    page = context.new_page()

    # 1. Guest visits /billing: sees guest CTA, subscription tiers first, tip separated below.
    page.goto(f"{base}/billing")
    expect(page.locator("#billing-guest-box")).to_be_visible()
    expect(page.locator("#billing-sub-plans .billing-tier")).to_have_count(2)
    tier_titles = page.locator("#billing-sub-plans .billing-tier h3").all_text_contents()
    assert tier_titles == ["Zhiming Plus", "ZhiMing Pro"]
    expect(page.locator("#billing-tip-section")).to_be_visible()

    # 2. Guest visits /ask: sees guest header link to /billing.
    page.goto(f"{base}/ask?provider=demo")
    expect(page.locator("#guest-billing-link")).to_be_visible()
    expect(page.locator("#guest-billing-link")).to_have_attribute("href", "/billing")

    # 3. Register an account via /login?tab=register&next=/billing -> lands back on /billing.
    page.goto(f"{base}/login?tab=register&next=/billing")
    page.fill("#account-name", "ux-buyer@example.com")
    page.fill("#account-password", "StrongPass123")
    page.fill("#account-confirm", "StrongPass123")
    page.check("#accept-privacy")
    page.click("#account-submit")
    page.wait_for_url(f"{base}/billing")
    expect(page.locator("#billing-account-email")).to_have_text("ux-buyer@example.com")
    expect(page.locator("#billing-guest-box")).to_be_hidden()
    expect(page.locator("#billing-self-help")).to_be_visible()

    # 4. Signed-in user on /ask sees prominent "充值额度" button and opens standalone #billing-dialog.
    page.goto(f"{base}/ask")
    expect(page.locator("#account-sponsor-btn")).to_be_visible()
    expect(page.locator("#account-sponsor-btn")).to_have_text("充值额度")
    page.click("#account-sponsor-btn")
    expect(page.locator("#billing-dialog")).to_be_visible()
    expect(page.locator("#billing-dialog .billing-plans .billing-plan")).to_have_count(2)
    modal_plans = page.locator("#billing-dialog .billing-plans .billing-plan strong").all_text_contents()
    assert modal_plans == ["Zhiming Plus", "ZhiMing Pro"]
    expect(page.locator("#billing-dialog .billing-plan-tip")).to_be_visible()
    expect(page.locator('#billing-dialog a[href="/billing"]')).to_be_visible()

    # 5. Exhaust account quota directly in DB -> composer bar & error guidance appear on /dream.
    store = AccountStore(project / "data/app.db")
    try:
        creds = store.credentials("ux-buyer@example.com")
        assert creds is not None
        user_id = creds[0]["user_id"]
        remaining = store.quota(user_id)["remaining"]
        call_id, _ = store.reserve_tokens(user_id, remaining, 0)
        store.settle_tokens(call_id, remaining, 0)
        assert store.quota(user_id)["remaining"] == 0
    finally:
        store.close()

    page.goto(f"{base}/dream")
    expect(page.locator("#account-sponsor-btn")).to_have_text("立即充值")
    expect(page.locator("#composer-quota-bar")).to_be_visible()
    expect(page.locator("#composer-quota-bar")).to_contain_text("当前可用额度已用完")

    page.fill("#message", "我梦见一条大河")
    with page.expect_response(lambda r: r.url.endswith("/api/chat")) as resp:
        page.click("#send")
    assert resp.value.status in (200, 403)
    expect(page.locator(".msg-error .msg-actions button")).to_have_text("立即充值额度")
    expect(page.locator("#notice")).to_be_visible()
    page.locator(".msg-error .msg-actions button").click()
    expect(page.locator("#billing-dialog")).to_be_visible()

    context.close()
