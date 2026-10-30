"""Explicit account quota exemptions retain site protection and never follow a reused name."""

import json

import pytest

from harness.metering import QuotaExceeded, SiteBudgetExhausted, SitePaused
from memory.accounts import FREE_TOKENS, AccountStore


def test_unlimited_account_persists_meters_and_can_be_revoked(tmp_path):
    path = tmp_path / "app.db"
    store = AccountStore(path)
    user = store.create("stantest", "hash")["user_id"]
    normal = store.create("normal", "hash")["user_id"]
    with store.db:
        store.db.execute("UPDATE account_quota SET used_tokens=?", (FREE_TOKENS * 100,))
    store.set_unlimited_quota(user, True, "stan")
    store.close()
    store = AccountStore(path)
    assert store.quota(user)["limit"] is None
    assert store.quota(user)["remaining"] is None
    call, output = store.reserve_tokens(user, 1000, 8192)
    assert output == 8192
    store.settle_tokens(call, 1000, 500)
    assert store.quota(user)["used"] == FREE_TOKENS * 100 + 1500
    assert store.costs.spend(0)["tokens"] == 1500
    accounts, _ = store.list_accounts("stantest")
    assert accounts[0]["quota"]["limit"] is None
    json.dumps(accounts, allow_nan=False)
    with pytest.raises(QuotaExceeded):
        store.reserve_tokens(normal, 1000, 8192)
    store.set_unlimited_quota(user, False, "stan")
    with pytest.raises(QuotaExceeded):
        store.reserve_tokens(user, 1000, 8192)
    assert store.costs.audit_log()[0]["detail"]["enabled"] is False
    store.close()


def test_unlimited_keeps_site_budget_and_anomaly_pause(tmp_path):
    store = AccountStore(tmp_path / "app.db", cost_defaults={"daily_token_budget": 2000})
    user = store.create("stantest", "hash")["user_id"]
    store.set_unlimited_quota(user, True, "stan")
    call, output = store.reserve_tokens(user, 1000, 8192)
    assert output == 1000
    store.settle_tokens(call, 1000, 1000)
    with pytest.raises(SiteBudgetExhausted):
        store.reserve_tokens(user, 100, 512)
    store.costs.update({"daily_token_budget": 0, "burst_site_tokens": 1000}, "stan")
    with pytest.raises(SitePaused):
        store.reserve_tokens(user, 100, 512)
    store.close()


def test_deletion_does_not_give_unlimited_quota_to_reused_name(tmp_path):
    store = AccountStore(tmp_path / "app.db")
    user = store.create("stantest", "hash")["user_id"]
    store.set_unlimited_quota(user, True, "stan")
    store.delete(user)
    assert store.db.execute("SELECT COUNT(*) FROM account_quota_unlimited").fetchone()[0] == 0
    new = store.create("stantest", "hash")["user_id"]
    assert store.quota(new)["limit"] == FREE_TOKENS
    store.close()
