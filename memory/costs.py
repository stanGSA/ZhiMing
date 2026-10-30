"""Site-wide cost control: daily budget, anomaly auto-pause, account suspension and a ledger.

Everything runs on the account store's connection, inside the transaction that reserves an
account's tokens, so two processes (or two requests) cannot both pass the same budget.
``site_usage`` is the site's own ledger: unlike ``model_usage`` it survives account deletion
(the user id is cleared), so deleting an account never resets today's spend.

Amounts are estimates from the provider's reported usage and the configured unit prices;
they are not the provider's bill.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Code defaults leave every limit off; config.yaml (cost_control) sets the deployed values and
# the admin page stores overrides in the database.
DEFAULTS = {
    "timezone": "Asia/Shanghai",
    "daily_token_budget": 0,
    "daily_cost_budget": 0.0,
    "currency": "CNY",
    "input_price_per_mtok": 0.0,
    "output_price_per_mtok": 0.0,
    "max_concurrent_calls": 0,
    "queue_wait_s": 20,
    "burst_window_min": 10,
    "burst_site_tokens": 0,
    "burst_account_tokens": 0,
    "auto_resume_min": 0,
}
# key -> (type, minimum, maximum)
BOUNDS = {
    "daily_token_budget": (int, 0, 10**10),
    "daily_cost_budget": (float, 0, 10**7),
    "input_price_per_mtok": (float, 0, 10**4),
    "output_price_per_mtok": (float, 0, 10**4),
    "max_concurrent_calls": (int, 0, 256),
    "queue_wait_s": (int, 0, 120),
    "burst_window_min": (int, 1, 1440),
    "burst_site_tokens": (int, 0, 10**10),
    "burst_account_tokens": (int, 0, 10**10),
    "auto_resume_min": (int, 0, 10080),
}
TEXT_SETTINGS = {"currency": 8}
USAGE_RETENTION = 90 * 86400
EVENT_RETENTION = 180 * 86400
AUDIT_RETENTION = 365 * 86400
SCHEMA = """
CREATE TABLE IF NOT EXISTS site_usage(call_id TEXT PRIMARY KEY, user_id TEXT, model TEXT,
  reserved_tokens INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
  status TEXT NOT NULL, error TEXT, created_at REAL NOT NULL, settled_at REAL);
CREATE INDEX IF NOT EXISTS site_usage_time ON site_usage(created_at);
CREATE INDEX IF NOT EXISTS site_usage_user ON site_usage(user_id, created_at);
CREATE TABLE IF NOT EXISTS site_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS site_events(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
  kind TEXT NOT NULL, level TEXT NOT NULL, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS site_events_time ON site_events(at);
CREATE TABLE IF NOT EXISTS account_controls(user_id TEXT PRIMARY KEY
  REFERENCES accounts(user_id) ON DELETE CASCADE,
  suspended_reason TEXT, suspended_at REAL, suspended_by TEXT, resumed_at REAL,
  bonus_tokens INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS admin_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
  admin TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS admin_audit_time ON admin_audit(at);
"""
# Tokens a row counts toward spend: settled usage, or the whole reservation while unknown.
EFFECTIVE = (
    "CASE status WHEN 'settled' THEN input_tokens+output_tokens "
    "WHEN 'rejected' THEN 0 ELSE reserved_tokens END"
)
# Errors exclude cancellations: a closed page or a reading's own deadline is not a fault.
FAILED = "error IS NOT NULL AND error<>'cancelled'"


class SettingsError(ValueError):
    def __init__(self, key: str, message: str):
        super().__init__(message)
        self.key = key
        self.message = message


def validate(changes: dict) -> dict:
    clean = {}
    for key, value in changes.items():
        if key in TEXT_SETTINGS:
            if not isinstance(value, str) or not value.strip().isalpha():
                raise SettingsError(key, "币种只能是字母，例如 CNY 或 USD。")
            if len(value.strip()) > TEXT_SETTINGS[key]:
                raise SettingsError(key, "币种过长。")
            clean[key] = value.strip().upper()
            continue
        if key not in BOUNDS:
            raise SettingsError(key, f"不支持的设置项：{key}")
        kind, low, high = BOUNDS[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise SettingsError(key, "需要填写数字。")
        if kind is int and value != int(value):
            raise SettingsError(key, "需要填写整数。")
        if not low <= value <= high:
            raise SettingsError(key, f"超出允许范围（{low}–{high}）。")
        clean[key] = kind(value)
    return clean


class CostControl:
    def __init__(self, db, defaults: dict | None = None):
        self.db = db
        self.db.executescript(SCHEMA)
        base = dict(DEFAULTS)
        if defaults:
            if defaults.get("timezone"):
                base["timezone"] = str(defaults["timezone"])
            base.update(
                validate({k: v for k, v in defaults.items() if k in DEFAULTS and k != "timezone"})
            )
        self.defaults = base
        self.zone = ZoneInfo(base["timezone"])

    # ---------- settings and state ----------

    def _get(self, key: str):
        row = self.db.execute("SELECT value FROM site_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _put(self, key: str, value) -> None:
        if value is None:
            self.db.execute("DELETE FROM site_settings WHERE key=?", (key,))
        else:
            self.db.execute(
                "INSERT OR REPLACE INTO site_settings VALUES(?,?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def overrides(self) -> dict:
        return self._get("cost_overrides") or {}

    def settings(self) -> dict:
        merged = {**self.defaults}
        for key, value in self.overrides().items():
            if key in BOUNDS or key in TEXT_SETTINGS:
                merged[key] = value
        return merged

    def update(self, changes: dict, admin: str) -> dict:
        clean = validate(changes)
        with self.db:
            overrides = {**self.overrides(), **clean}
            # A value equal to the configured default is not an override.
            overrides = {k: v for k, v in overrides.items() if v != self.defaults.get(k)}
            self._put("cost_overrides", overrides or None)
            self.audit(admin, "update_settings", clean)
        return self.settings()

    def reset(self, admin: str) -> dict:
        with self.db:
            self._put("cost_overrides", None)
            self.audit(admin, "reset_settings", {})
        return self.settings()

    def pause_state(self) -> dict | None:
        return self._get("pause")

    def pause(self, reason: str, by: str, *, auto: bool = False, now: float | None = None):
        now = time.time() if now is None else now
        state = {"reason": reason[:200], "by": by, "auto": auto, "at": now}
        self._put("pause", state)
        self.event(
            "site_paused_auto" if auto else "site_paused",
            "critical" if auto else "warning",
            {"reason": state["reason"], "by": by},
            now,
        )
        if not auto:
            self.audit(by, "pause_models", {"reason": state["reason"]}, now)
        return state

    def resume(self, by: str, *, now: float | None = None, auto: bool = False) -> None:
        now = time.time() if now is None else now
        self._put("pause", None)
        # Spend before the resume does not count toward the next burst window.
        self._put("burst_since", now)
        self.event("site_resumed_auto" if auto else "site_resumed", "info", {"by": by}, now)
        if not auto:
            self.audit(by, "resume_models", {}, now)

    def manual_pause(self, reason: str, by: str) -> dict:
        with self.db:
            return self.pause(reason or "管理员手动暂停", by)

    def manual_resume(self, by: str) -> None:
        with self.db:
            self.resume(by)

    # ---------- account controls ----------

    def control(self, user_id: str) -> dict:
        row = self.db.execute(
            "SELECT * FROM account_controls WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            return {"suspended": None, "bonus_tokens": 0, "resumed_at": None}
        suspended = (
            {
                "reason": row["suspended_reason"],
                "at": row["suspended_at"],
                "by": row["suspended_by"],
            }
            if row["suspended_at"] is not None
            else None
        )
        return {
            "suspended": suspended,
            "bonus_tokens": row["bonus_tokens"],
            "resumed_at": row["resumed_at"],
        }

    def _ensure(self, user_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO account_controls(user_id) VALUES(?)", (user_id,))

    def suspend(self, user_id: str, reason: str, by: str, *, auto=False, now=None) -> None:
        now = time.time() if now is None else now
        self._ensure(user_id)
        self.db.execute(
            "UPDATE account_controls SET suspended_reason=?,suspended_at=?,suspended_by=? "
            "WHERE user_id=?",
            (reason[:200], now, by, user_id),
        )
        if auto:
            self.event(
                "account_suspended_auto", "warning", {"user_id": user_id, "reason": reason}, now
            )
        else:
            self.audit(by, "suspend_account", {"user_id": user_id, "reason": reason[:200]}, now)

    def unsuspend(self, user_id: str, by: str, now=None) -> None:
        now = time.time() if now is None else now
        self._ensure(user_id)
        self.db.execute(
            "UPDATE account_controls SET suspended_reason=NULL,suspended_at=NULL,"
            "suspended_by=NULL,resumed_at=? WHERE user_id=?",
            (now, user_id),
        )
        self.audit(by, "unsuspend_account", {"user_id": user_id}, now)

    def grant(self, user_id: str, tokens: int, by: str, now=None) -> None:
        self._ensure(user_id)
        self.db.execute(
            "UPDATE account_controls SET bonus_tokens=MAX(0,bonus_tokens+?) WHERE user_id=?",
            (tokens, user_id),
        )
        self.audit(by, "grant_tokens", {"user_id": user_id, "tokens": tokens}, now)

    # ---------- admission (inside the reservation transaction) ----------

    def day_start(self, now: float) -> float:
        local = datetime.fromtimestamp(now, self.zone)
        return local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def next_day(self, now: float) -> float:
        # Aware datetimes add wall-clock days, so this is the next local midnight.
        return (
            datetime.fromtimestamp(self.day_start(now), self.zone) + timedelta(days=1)
        ).timestamp()

    def gatekeep(self, user_id: str, now: float) -> None:
        """Refuse while the site is paused or the account suspended."""
        from harness.metering import AccountSuspended, SitePaused

        state = self.pause_state()
        if state is not None:
            minutes = self.settings()["auto_resume_min"]
            if state.get("auto") and minutes and now - state["at"] >= minutes * 60:
                self.resume("system", now=now, auto=True)
            else:
                raise SitePaused()
        if self.control(user_id)["suspended"] is not None:
            raise AccountSuspended()

    def budget_room(self, now: float) -> int | None:
        """Tokens left in today's site budget (token and cost limits), or None if unlimited."""
        settings = self.settings()
        rooms = []
        start = self.day_start(now)
        spent = self.spend(start, now)
        if settings["daily_token_budget"] > 0:
            rooms.append(settings["daily_token_budget"] - spent["tokens"])
        price = max(settings["input_price_per_mtok"], settings["output_price_per_mtok"])
        if settings["daily_cost_budget"] > 0 and price > 0:
            left = settings["daily_cost_budget"] - spent["cost"]
            # The epsilon keeps float noise (0.08 / 40e-6 = 1999.99…) from costing a token.
            rooms.append(int(left * 1_000_000 / price + 1e-6))
        return max(0, min(rooms)) if rooms else None

    def budget_refused_since(self, now: float) -> float | None:
        """When today's budget started refusing calls, or None once that is over.

        Refusal can begin below 100%: once the remainder cannot hold a call's minimum
        reservation. It is over when the remainder can again hold the smallest reservation that
        was refused (a raised budget or lower prices), or at midnight; changing unrelated
        settings does not end it."""
        block = self._get("budget_block")
        if not block:
            return None
        room = self.budget_room(now)
        if block["at"] >= self.day_start(now) and room is not None and room < block["needed"]:
            return block["at"]
        # Over: forget it, so a later refusal is reported from its own time.
        started = self.db.in_transaction
        self._put("budget_block", None)
        if not started:
            self.db.commit()
        return None

    def budget_exhausted(self, now: float, needed: int) -> None:
        """Record a refusal for want of budget; ``needed`` is the smallest reservation it would
        have taken. The first refusal of a blocked period also becomes an event."""
        since = self.budget_refused_since(now)
        if since is None:
            self._put("budget_block", {"at": now, "needed": needed})
            self.event("budget_exhausted", "critical", self.spend(self.day_start(now), now), now)
        else:
            block = self._get("budget_block")
            self._put("budget_block", {**block, "needed": min(block["needed"], needed)})

    def trip(self, user_id: str, reservation: int, now: float):
        """Auto-pause the site or suspend the account when the window's spend is anomalous.
        Returns the refusal to raise, or None."""
        from harness.metering import AccountSuspended, SitePaused

        settings = self.settings()
        window = settings["burst_window_min"] * 60
        if settings["burst_site_tokens"] > 0:
            since = max(now - window, self._get("burst_since") or 0)
            used = self.spend(since, now)["tokens"]
            if used + reservation > settings["burst_site_tokens"]:
                self.pause(
                    f"{settings['burst_window_min']} 分钟内全站消耗 {used:,} token，"
                    f"加上本次预留超过阈值 {settings['burst_site_tokens']:,}",
                    "system",
                    auto=True,
                    now=now,
                )
                return SitePaused()
        if user_id is not None and settings["burst_account_tokens"] > 0:
            since = max(now - window, self.control(user_id)["resumed_at"] or 0)
            used = self.spend(since, now, user_id)["tokens"]
            if used + reservation > settings["burst_account_tokens"]:
                self.suspend(
                    user_id,
                    f"{settings['burst_window_min']} 分钟内消耗 {used:,} token，"
                    f"加上本次预留超过单账号阈值 {settings['burst_account_tokens']:,}",
                    "system",
                    auto=True,
                    now=now,
                )
                return AccountSuspended()
        return None

    # ---------- ledger ----------

    def reserve(self, call_id, user_id, model, reserved, now) -> None:
        self.db.execute(
            "INSERT INTO site_usage(call_id,user_id,model,reserved_tokens,status,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (call_id, user_id, model, reserved, "reserved", now),
        )

    def settle(self, call_id, input_tokens, output_tokens, status, error, now) -> None:
        self.db.execute(
            "UPDATE site_usage SET input_tokens=?,output_tokens=?,status=?,error=?,settled_at=? "
            "WHERE call_id=? AND status='reserved'",
            (input_tokens, output_tokens, status, error, now, call_id),
        )

    def spend(self, since: float, until: float | None = None, user_id: str | None = None):
        settings = self.settings()
        pin = settings["input_price_per_mtok"] / 1_000_000
        pout = settings["output_price_per_mtok"] / 1_000_000
        worst = max(pin, pout)
        sql = (
            f"SELECT COALESCE(SUM({EFFECTIVE}),0), COUNT(*), "
            f"COALESCE(SUM(CASE WHEN {FAILED} THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(CASE status WHEN 'settled' THEN input_tokens*?+output_tokens*? "
            "WHEN 'rejected' THEN 0 ELSE reserved_tokens*? END),0), "
            "COALESCE(SUM(CASE status WHEN 'reserved' THEN 1 ELSE 0 END),0) "
            "FROM site_usage WHERE created_at>=?"
        )
        params: list = [pin, pout, worst, since]
        if until is not None:
            sql += " AND created_at<=?"
            params.append(until)
        if user_id is not None:
            sql += " AND user_id=?"
            params.append(user_id)
        tokens, calls, errors, cost, pending = self.db.execute(sql, params).fetchone()
        return {
            "tokens": int(tokens),
            "calls": calls,
            "errors": errors,
            "pending": pending,
            "cost": round(float(cost), 6),
        }

    def error_kinds(self, since: float) -> dict:
        rows = self.db.execute(
            "SELECT error, COUNT(*) FROM site_usage WHERE created_at>=? AND error IS NOT NULL "
            "GROUP BY error ORDER BY COUNT(*) DESC",
            (since,),
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def hourly(self, now: float, hours: int = 24) -> list[dict]:
        start = (int(now) // 3600 - hours + 1) * 3600
        rows = self.db.execute(
            f"SELECT CAST((created_at-?)/3600 AS INTEGER), COALESCE(SUM({EFFECTIVE}),0), "
            f"COUNT(*), COALESCE(SUM(CASE WHEN {FAILED} THEN 1 ELSE 0 END),0) "
            "FROM site_usage WHERE created_at>=? GROUP BY 1",
            (start, start),
        ).fetchall()
        found = {row[0]: row[1:] for row in rows}
        return [
            {
                "start": start + 3600 * index,
                "tokens": int(found.get(index, (0, 0, 0))[0]),
                "calls": found.get(index, (0, 0, 0))[1],
                "errors": found.get(index, (0, 0, 0))[2],
            }
            for index in range(hours)
        ]

    def top_accounts(self, since: float, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            f"SELECT u.user_id, a.username, SUM({EFFECTIVE}) t, "
            "COUNT(*) FROM site_usage u LEFT JOIN accounts a ON a.user_id=u.user_id "
            "WHERE u.created_at>=? AND u.user_id IS NOT NULL GROUP BY u.user_id "
            "ORDER BY t DESC LIMIT ?",
            (since, limit),
        ).fetchall()
        return [
            {"user_id": r[0], "username": r[1], "tokens": int(r[2] or 0), "calls": r[3]}
            for r in rows
        ]

    def forget_user(self, user_id: str) -> None:
        """An account's deletion keeps the site's spend but drops the link to the person."""
        self.db.execute("UPDATE site_usage SET user_id=NULL WHERE user_id=?", (user_id,))

    # ---------- events and audit ----------

    def event(self, kind: str, level: str, detail: dict, now: float | None = None) -> None:
        self.db.execute(
            "INSERT INTO site_events(at,kind,level,detail) VALUES(?,?,?,?)",
            (
                time.time() if now is None else now,
                kind,
                level,
                json.dumps(detail, ensure_ascii=False),
            ),
        )

    def events(self, since: float = 0, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT id,at,kind,level,detail FROM site_events WHERE at>=? ORDER BY id DESC LIMIT ?",
            (since, limit),
        ).fetchall()
        return [
            {"id": r[0], "at": r[1], "kind": r[2], "level": r[3], "detail": json.loads(r[4])}
            for r in rows
        ]

    def audit(self, admin: str, action: str, detail: dict, now: float | None = None) -> None:
        self.db.execute(
            "INSERT INTO admin_audit(at,admin,action,detail) VALUES(?,?,?,?)",
            (
                time.time() if now is None else now,
                admin,
                action,
                json.dumps(detail, ensure_ascii=False),
            ),
        )

    def audit_log(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT at,admin,action,detail FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"at": r[0], "admin": r[1], "action": r[2], "detail": json.loads(r[3])} for r in rows
        ]

    def prune(self, now: float) -> None:
        self.db.execute(
            "DELETE FROM site_usage WHERE created_at<? AND status<>'reserved'",
            (now - USAGE_RETENTION,),
        )
        self.db.execute("DELETE FROM site_events WHERE at<?", (now - EVENT_RETENTION,))
        self.db.execute("DELETE FROM admin_audit WHERE at<?", (now - AUDIT_RETENTION,))
