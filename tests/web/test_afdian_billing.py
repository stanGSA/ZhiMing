"""Afdian (爱发电) billing, rolling-month dual-pool quota, webhook verification and admin tools."""

from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import httpx

from memory.accounts import FREE_TOKENS, AccountStore, add_calendar_months
from memory.billing import (
    AfdianClient,
    AfdianConfig,
    BillingStore,
    sign_afdian_request,
)
from web import create_web_app

SHANGHAI = ZoneInfo("Asia/Shanghai")
HEADERS = {"Origin": "https://testserver", "X-Zhiming-Client": "web"}
WEBHOOK_SECRET = "test-afdian-webhook-secret-0123456789abcdef"


def make_afdian_config() -> AfdianConfig:
    return AfdianConfig.from_env(
        {
            "AFDIAN_CREATOR_URL": "https://afdian.com/a/zhiming_ai",
            "AFDIAN_USER_ID": "ae4a6bfeea3211f1aea952540025c377",
            "AFDIAN_API_TOKEN": "test-api-token-secret",
            "AFDIAN_WEBHOOK_SECRET": WEBHOOK_SECRET,
            "AFDIAN_TIP_PLAN_ID": "f2dce26eea3311f18be1525400c8052f",
            "AFDIAN_PLUS_PLAN_ID": "cf5d2596ea3411f19a8052540025c377",
            "AFDIAN_PRO_PLAN_ID": "ff1c165cea3411f1bcc952540025c377",
        }
    )


def make_mock_afdian_client(config: AfdianConfig, orders_by_id: dict[str, dict]) -> AfdianClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        expected = sign_afdian_request(
            config.user_id, config.api_token, body["params"], int(body["ts"])
        )
        assert body["user_id"] == config.user_id
        assert body["sign"] == expected
        params = json.loads(body["params"])
        if request.url.path == "/api/open/ping":
            return httpx.Response(
                200, json={"ec": 200, "em": "ok", "data": {"uid": config.user_id}}
            )
        if request.url.path == "/api/open/query-order":
            trade_no = params.get("out_trade_no")
            if trade_no:
                item = orders_by_id.get(trade_no)
                items = [item] if item else []
            else:
                items = list(orders_by_id.values())
            return httpx.Response(
                200,
                json={
                    "ec": 200,
                    "em": "ok",
                    "data": {"list": items, "total_count": len(items), "total_page": 1},
                },
            )
        return httpx.Response(404, json={"ec": 404, "em": "not found"})

    return AfdianClient(config, transport=httpx.MockTransport(handler))


def browser_client(app, ip="203.0.113.10"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 40000)),
        base_url="https://testserver",
        headers=HEADERS,
    )


def test_add_calendar_months_clamps_month_end_and_preserves_time():
    nov27 = datetime(2026, 11, 27, 16, 25, 30, tzinfo=SHANGHAI).timestamp()
    dec27 = add_calendar_months(nov27, 1)
    assert datetime.fromtimestamp(dec27, SHANGHAI) == datetime(
        2026, 12, 27, 16, 25, 30, tzinfo=SHANGHAI
    )

    jan31 = datetime(2026, 1, 31, 15, 0, 0, tzinfo=SHANGHAI).timestamp()
    assert datetime.fromtimestamp(add_calendar_months(jan31, 1), SHANGHAI) == datetime(
        2026, 2, 28, 15, 0, 0, tzinfo=SHANGHAI
    )
    assert datetime.fromtimestamp(add_calendar_months(jan31, 2), SHANGHAI) == datetime(
        2026, 3, 31, 15, 0, 0, tzinfo=SHANGHAI
    )

    leap_jan31 = datetime(2028, 1, 31, 9, 30, 0, tzinfo=SHANGHAI).timestamp()
    assert datetime.fromtimestamp(add_calendar_months(leap_jan31, 1), SHANGHAI) == datetime(
        2028, 2, 29, 9, 30, 0, tzinfo=SHANGHAI
    )


def test_dual_pool_priority_stacking_expiry_and_inflight_settlement(project):
    store = AccountStore(project / "data/app.db")
    try:
        user = store.create("sub@example.com", "hash")["user_id"]
        t_nov27 = datetime(2026, 11, 27, 16, 0, 0, tzinfo=SHANGHAI).timestamp()
        t_nov29 = datetime(2026, 11, 29, 10, 0, 0, tzinfo=SHANGHAI).timestamp()
        t_dec27_after = datetime(2026, 12, 27, 16, 0, 1, tzinfo=SHANGHAI).timestamp()
        t_dec29_after = datetime(2026, 12, 29, 10, 0, 1, tzinfo=SHANGHAI).timestamp()

        assert store.quota(user, now=t_nov27)["remaining"] == FREE_TOKENS

        with store.db:
            store.add_subscription_grants(
                user,
                order_out_trade_no="trade_plus_1",
                plan_key="plus",
                tokens_per_month=500_000,
                months=1,
                starts_at=t_nov27,
                now=t_nov27,
            )
            store.add_subscription_grants(
                user,
                order_out_trade_no="trade_pro_1",
                plan_key="pro",
                tokens_per_month=1_000_000,
                months=1,
                starts_at=t_nov29,
                now=t_nov29,
            )

        # Stacked within same rolling window: 500k + 1M + 250k = 1,750,000.
        detail = store.quota_detail(user, now=t_nov29)
        assert detail["remaining"] == 1_750_000
        assert detail["subscription"]["remaining"] == 1_500_000
        assert detail["permanent"]["remaining"] == FREE_TOKENS
        assert detail["subscription"]["earliest_expires_at"] == add_calendar_months(t_nov27, 1)
        assert detail["subscription"]["latest_expires_at"] == add_calendar_months(t_nov29, 1)

        # Consume 520,000 -> drains Plus (500k) first, then 20k from Pro; permanent untouched!
        c1, _ = store.reserve_tokens(user, 500_000, 20_000, now=t_nov29)
        store.settle_tokens(c1, 500_000, 20_000)
        d1 = store.quota_detail(user, now=t_nov29)
        assert d1["permanent"]["used"] == 0
        assert d1["permanent"]["remaining"] == FREE_TOKENS
        assert d1["subscription"]["active_grants"][0]["remaining"] == 0  # Plus drained
        assert d1["subscription"]["active_grants"][1]["remaining"] == 980_000  # Pro -20k

        # Start an in-flight call right before Pro expires, settle AFTER expiry: no held leak!
        t_just_before = datetime(2026, 12, 29, 9, 59, 55, tzinfo=SHANGHAI).timestamp()
        c2, _ = store.reserve_tokens(user, 1000, 2000, now=t_just_before)
        assert store.quota(user, now=t_just_before)["reserved"] == 3000
        store.settle_tokens(c2, 1200, 300)

        # After Dec 27 Plus expired, only Pro was active; after Dec 29 both expired -> 250k permanent remains!
        d_mid = store.quota_detail(user, now=t_dec27_after)
        assert len(d_mid["subscription"]["active_grants"]) == 1
        assert d_mid["subscription"]["remaining"] == 978_500

        d_end = store.quota_detail(user, now=t_dec29_after)
        assert d_end["subscription"]["remaining"] == 0
        assert d_end["subscription"]["reserved"] == 0
        assert d_end["permanent"]["remaining"] == FREE_TOKENS
        assert d_end["remaining"] == FREE_TOKENS

        # Exhausting subscription + spilling into permanent works in a single call.
        with store.db:
            store.add_subscription_grants(
                user,
                order_out_trade_no="trade_small",
                plan_key="plus",
                tokens_per_month=1_000,
                months=1,
                starts_at=t_dec29_after,
                now=t_dec29_after,
            )
        c3, _ = store.reserve_tokens(user, 2_000, 1_000, now=t_dec29_after)
        store.settle_tokens(c3, 2_000, 500)
        d_spill = store.quota_detail(user, now=t_dec29_after)
        assert d_spill["subscription"]["remaining"] == 0
        assert d_spill["permanent"]["used"] == 1_500
        assert d_spill["permanent"]["remaining"] == FREE_TOKENS - 1_500
    finally:
        store.close()


def test_multi_month_subscription_and_tip_plan(project):
    config = make_afdian_config()
    accounts = AccountStore(project / "data/app.db")
    billing = BillingStore(accounts, config)
    try:
        user = accounts.create("multi@example.com", "hash")["user_id"]
        t0 = datetime(2026, 11, 27, 12, 0, 0, tzinfo=SHANGHAI).timestamp()
        checkout = billing.create_checkout(user, "plus", now=t0)

        res = billing.ingest_verified_order(
            {
                "out_trade_no": "2026112700000001",
                "user_id": "afd_buyer_1",
                "custom_order_id": checkout["custom_order_id"],
                "plan_id": config.plan_by_key("plus").plan_id,
                "product_type": 0,
                "month": 3,
                "total_amount": "19.98",
                "status": 2,
                "remark": "",
                "create_time": int(t0),
            },
            now=t0,
        )
        assert res["process_status"] == "credited"
        assert res["tokens_granted"] == 1_500_000

        # Only month 1 (500k) is active at t0; months 2 and 3 are upcoming.
        d0 = accounts.quota_detail(user, now=t0)
        assert d0["subscription"]["remaining"] == 500_000
        assert len(d0["subscription"]["active_grants"]) == 1
        assert len(d0["subscription"]["upcoming_grants"]) == 2

        # At month 2 start (Dec 27 12:00), month 1 expires and month 2 activates automatically.
        t1 = add_calendar_months(t0, 1)
        d1 = accounts.quota_detail(user, now=t1)
        assert d1["subscription"]["remaining"] == 500_000
        assert len(d1["subscription"]["active_grants"]) == 1
        assert len(d1["subscription"]["upcoming_grants"]) == 1

        # Tip plan ("一盏清茶"): 0 tokens, badge & record stored.
        tip_res = billing.ingest_verified_order(
            {
                "out_trade_no": "2026112700000002",
                "user_id": "afd_buyer_1",  # auto-matched via afdian_user_links!
                "custom_order_id": "",
                "plan_id": config.plan_by_key("tip").plan_id,
                "product_type": 0,
                "month": 1,
                "total_amount": "5.00",
                "status": 2,
                "remark": "",
                "create_time": int(t0),
            },
            now=t0,
        )
        assert tip_res["process_status"] == "tip_recorded"
        assert tip_res["tokens_granted"] == 0
        summary = billing.user_summary(user, now=t0)
        assert summary["tea_support"]["count"] == 1
        assert any(b["key"] == "tip" for b in summary["badges"])
        assert summary["quota"]["remaining"] == FREE_TOKENS + 500_000
    finally:
        accounts.close()


async def test_checkout_webhook_security_idempotency_claim_and_admin_bind(project):
    config = make_afdian_config()
    orders_by_id: dict[str, dict] = {}
    mock_client = make_mock_afdian_client(config, orders_by_id)

    # First create an admin account directly so we can pass admin_ids to create_web_app.
    seed_store = AccountStore(project / "data/app.db")
    admin_acct = seed_store.create("admin@example.com", "placeholder")
    seed_store.close()

    # Use real password hash for admin login via normal app flow after setting password hash.
    from memory.accounts import hash_password

    seed_store = AccountStore(project / "data/app.db")
    seed_store.set_password(admin_acct["user_id"], hash_password("AdminPass123!"))
    seed_store.close()

    app = create_web_app(
        root=project,
        public_origin="https://testserver",
        admin_ids=admin_acct["user_id"],
        afdian_config=config,
        afdian_client=mock_client,
    )

    async with (
        app.router.lifespan_context(app),
        browser_client(app, "203.0.113.11") as buyer,
        browser_client(app, "203.0.113.12") as other_user,
        browser_client(app, "203.0.113.13") as admin_browser,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("198.51.100.5", 50000)),
            base_url="https://testserver",
        ) as afdian_hook,
    ):
        # Register buyer & other_user, login admin.
        assert (
            await buyer.post(
                "/api/account/register",
                json={
                    "email": "buyer@example.com",
                    "password": "BuyerPass123",
                    "accept_privacy": True,
                },
            )
        ).status_code == 201
        assert (
            await other_user.post(
                "/api/account/register",
                json={
                    "email": "other@example.com",
                    "password": "OtherPass123",
                    "accept_privacy": True,
                },
            )
        ).status_code == 201
        assert (
            await admin_browser.post(
                "/api/account/login",
                json={"email": "admin@example.com", "password": "AdminPass123!"},
            )
        ).status_code == 200

        # Plans endpoint exposes 3 plans and 250,000 free registration tokens.
        plans_resp = await buyer.get("/api/billing/plans")
        assert plans_resp.status_code == 200
        plans_data = plans_resp.json()
        assert plans_data["enabled"] is True
        assert plans_data["free_registration_tokens"] == FREE_TOKENS
        assert [p["key"] for p in plans_data["plans"]] == ["tip", "plus", "pro"]

        # Create checkout URL for Plus.
        co = await buyer.post("/api/billing/afdian/checkout", json={"plan_key": "plus"})
        assert co.status_code == 200
        co_data = co.json()
        parsed_qs = parse_qs(urlsplit(co_data["pay_url"]).query)
        assert parsed_qs["plan_id"] == [config.plan_by_key("plus").plan_id]
        assert parsed_qs["product_type"] == ["0"]
        assert parsed_qs["custom_order_id"] == [co_data["custom_order_id"]]
        assert parsed_qs["remark"] == ["buyer@example.com"]

        # 1. Wrong webhook secret -> 404 (no Origin or X-Zhiming-Client header required).
        bad_secret = await afdian_hook.post(
            "/api/webhooks/afdian/wrong-secret",
            json={
                "ec": 200,
                "data": {"type": "order", "order": {"out_trade_no": "2026112799999999"}},
            },
        )
        assert bad_secret.status_code == 404

        # 2. Forged webhook with fake out_trade_no not in Afdian OpenAPI -> credits nothing!
        forged = await afdian_hook.post(
            f"/api/webhooks/afdian/{WEBHOOK_SECRET}",
            json={
                "ec": 200,
                "data": {
                    "type": "order",
                    "order": {
                        "out_trade_no": "2026112700009999",
                        "custom_order_id": co_data["custom_order_id"],
                        "plan_id": config.plan_by_key("pro").plan_id,
                        "status": 2,
                        "total_amount": "10.00",
                    },
                },
            },
        )
        assert forged.status_code == 200 and forged.json() == {"ec": 200, "em": ""}
        assert (await buyer.get("/api/billing/status")).json()["quota"]["remaining"] == FREE_TOKENS

        # 3. Legitimate order verified via OpenAPI -> credits +500,000, strictly idempotent on replay.
        orders_by_id["2026112710000001"] = {
            "out_trade_no": "2026112710000001",
            "user_id": "afd_u_buyer",
            "custom_order_id": co_data["custom_order_id"],
            "plan_id": config.plan_by_key("plus").plan_id,
            "product_type": 0,
            "month": 1,
            "total_amount": "6.66",
            "status": 2,
            "remark": "buyer@example.com",
        }
        for _ in range(2):
            hook_ok = await afdian_hook.post(
                f"/api/webhooks/afdian/{WEBHOOK_SECRET}",
                json={
                    "ec": 200,
                    "data": {"type": "order", "order": {"out_trade_no": "2026112710000001"}},
                },
            )
            assert hook_ok.status_code == 200 and hook_ok.json() == {"ec": 200, "em": ""}

        status_after = (await buyer.get("/api/billing/status")).json()
        assert status_after["quota"]["remaining"] == FREE_TOKENS + 500_000

        # 4. Same buyer upgrades to Pro directly on Afdian (no custom_order_id) -> auto-linked & stacked!
        orders_by_id["2026112710000002"] = {
            "out_trade_no": "2026112710000002",
            "user_id": "afd_u_buyer",
            "custom_order_id": "",
            "plan_id": config.plan_by_key("pro").plan_id,
            "product_type": 0,
            "month": 1,
            "total_amount": "3.34",  # upgrade price difference
            "status": 2,
            "remark": "",
        }
        sync_resp = await buyer.post("/api/billing/afdian/sync", json={})
        assert sync_resp.status_code == 200
        assert sync_resp.json()["quota"]["remaining"] == FREE_TOKENS + 1_500_000

        # 5. Another user cannot steal buyer's already-credited order via self-claim.
        steal = await other_user.post(
            "/api/billing/afdian/claim", json={"out_trade_no": "2026112710000001"}
        )
        assert steal.status_code == 409

        # 6. Direct order with no link and no remark lands as unmatched; user can self-claim,
        #    and another unmatched order can be bound by admin.
        orders_by_id["2026112710000003"] = {
            "out_trade_no": "2026112710000003",
            "user_id": "afd_u_other",
            "custom_order_id": "",
            "plan_id": config.plan_by_key("tip").plan_id,
            "product_type": 0,
            "month": 1,
            "total_amount": "5.00",
            "status": 2,
            "remark": "",
        }
        orders_by_id["2026112710000004"] = {
            "out_trade_no": "2026112710000004",
            "user_id": "afd_u_manual",
            "custom_order_id": "",
            "plan_id": config.plan_by_key("plus").plan_id,
            "product_type": 0,
            "month": 1,
            "total_amount": "6.66",
            "status": 2,
            "remark": "忘记写邮箱了",
        }
        admin_sync = await admin_browser.post("/api/admin/afdian/sync", json={})
        assert admin_sync.status_code == 200
        assert admin_sync.json()["sync"]["unmatched"] == 2

        # Other user self-claims the tip order -> gets tea badge, 0 extra tokens.
        claimed = await other_user.post(
            "/api/billing/afdian/claim", json={"out_trade_no": "2026112710000003"}
        )
        assert claimed.status_code == 200
        assert claimed.json()["order"]["process_status"] == "tip_recorded"
        assert claimed.json()["billing"]["tea_support"]["count"] == 1
        assert claimed.json()["quota"]["remaining"] == FREE_TOKENS

        # Admin lists unmatched orders and binds 2026112710000004 to other@example.com.
        unmatched_list = await admin_browser.get("/api/admin/afdian/orders?status=unmatched")
        assert unmatched_list.status_code == 200
        assert [o["out_trade_no"] for o in unmatched_list.json()["items"]] == ["2026112710000004"]

        bound = await admin_browser.post(
            "/api/admin/afdian/orders/2026112710000004/bind",
            json={"account": "other@example.com"},
        )
        assert bound.status_code == 200
        assert bound.json()["order"]["process_status"] == "credited"
        assert bound.json()["order"]["tokens_granted"] == 500_000
        assert (await other_user.get("/api/billing/status")).json()["quota"]["remaining"] == (
            FREE_TOKENS + 500_000
        )

        # Admin overview includes afdian stats and audit log records afdian_bind_order.
        overview = (await admin_browser.get("/api/admin/overview")).json()
        assert overview["afdian"]["unmatched_orders"] == 0
        assert overview["afdian"]["fulfilled_orders"] == 4
        assert any(a["action"] == "afdian_bind_order" for a in overview["audit"])
