"""Browser accounts: registration, password hashes and login tokens.

Passwords are kept only as salted scrypt hashes. A login token is random; the database keeps
its SHA-256, so a copy of the database cannot be replayed as a browser cookie. Records that
belong to an account live in the ordinary business tables (memory/store.py) under its user id.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from memory.costs import CostControl

# Bump when the privacy notice (web_static/privacy.html) changes in substance.
PRIVACY_VERSION = "2026-11-27"
FREE_TOKENS = 250_000
REGISTRATION_WINDOW = 7 * 24 * 3600
SHANGHAI = ZoneInfo("Asia/Shanghai")
SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def add_calendar_months(ts: float, months: int, zone: ZoneInfo = SHANGHAI) -> float:
    """Advance a timestamp by ``months`` calendar months in ``zone``, clamping month-end days.

    E.g. 2026-11-27 16:30 -> 2026-12-27 16:30; 2026-01-31 15:00 -> 2026-02-28 15:00.
    """
    if months < 0:
        raise ValueError("months must be non-negative")
    dt = datetime.fromtimestamp(ts, zone)
    total = (dt.month - 1) + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day).timestamp()


EMAIL_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")
EMAIL_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
EMAIL_TLD = re.compile(r"(?:[A-Za-z]{2,}|xn--[A-Za-z0-9-]{2,})")


class AccountError(ValueError):
    """A refusal the browser can show as is."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def email_key(value: str) -> str:
    """Account emails (and legacy usernames) are unique regardless of case and full/half width."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


username_key = email_key


def check_email(value: str) -> str:
    email = unicodedata.normalize("NFKC", value).strip().lower()
    local, sep, domain = email.partition("@")
    if (
        not sep
        or "@" in domain
        or len(email) > 254
        or not (1 <= len(local) <= 64)
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not EMAIL_LOCAL.fullmatch(local)
        or "." not in domain
    ):
        raise AccountError("invalid_email", "请输入有效的邮箱地址。")
    labels = domain.split(".")
    if not all(EMAIL_LABEL.fullmatch(label) for label in labels) or not EMAIL_TLD.fullmatch(
        labels[-1]
    ):
        raise AccountError("invalid_email", "请输入有效的邮箱地址。")
    return email


def check_password(password: str, email: str = "") -> None:
    if len(password) < 8:
        raise AccountError("weak_password", "密码至少需要 8 个字符。")
    if len(password) > 128:
        raise AccountError("weak_password", "密码不能超过 128 个字符。")
    kinds = sum(bool(re.search(p, password)) for p in (r"[A-Za-z]", r"\d", r"[^A-Za-z\d]"))
    if kinds < 2:
        raise AccountError("weak_password", "密码需包含字母、数字、符号中的至少两类。")
    if email and email_key(password) == email_key(email):
        raise AccountError("weak_password", "密码不能与邮箱相同。")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=64 << 20, **SCRYPT)
    encode = base64.b64encode
    return "scrypt${n}${r}${p}${salt}${digest}".format(
        **SCRYPT, salt=encode(salt).decode(), digest=encode(digest).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest, validate=True)
        actual = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt, validate=True),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=64 << 20,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Checked against when a name is unknown, so a miss takes as long as a wrong password.
_DUMMY_HASH: list[str] = []


def dummy_verify(password: str) -> bool:
    if not _DUMMY_HASH:
        _DUMMY_HASH.append(hash_password(secrets.token_urlsafe(16)))
    verify_password(password, _DUMMY_HASH[0])
    return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccountStore:
    def __init__(self, path: Path, cost_defaults: dict | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts(user_id TEXT PRIMARY KEY, username TEXT NOT NULL,
          username_key TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          privacy_version TEXT NOT NULL, privacy_accepted_at TEXT NOT NULL,
          created_at TEXT NOT NULL, password_changed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS account_sessions(token_hash TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
          created_at REAL NOT NULL, expires_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS account_sessions_user ON account_sessions(user_id);
        CREATE TABLE IF NOT EXISTS account_quota(user_id TEXT PRIMARY KEY
          REFERENCES accounts(user_id) ON DELETE CASCADE,
          used_tokens INTEGER NOT NULL DEFAULT 0, held_tokens INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS account_quota_unlimited(user_id TEXT PRIMARY KEY
          REFERENCES accounts(user_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS account_allowances(user_id TEXT PRIMARY KEY
          REFERENCES accounts(user_id) ON DELETE CASCADE, tokens INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS quota_distributions(request_id TEXT PRIMARY KEY,
          tokens INTEGER NOT NULL, recipients INTEGER NOT NULL, created_at REAL NOT NULL);
        INSERT OR IGNORE INTO account_allowances SELECT user_id,250000 FROM accounts;
        CREATE TABLE IF NOT EXISTS account_token_grants(grant_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
          source TEXT NOT NULL, order_out_trade_no TEXT, plan_key TEXT NOT NULL,
          granted_tokens INTEGER NOT NULL, used_tokens INTEGER NOT NULL DEFAULT 0,
          held_tokens INTEGER NOT NULL DEFAULT 0, starts_at REAL NOT NULL,
          expires_at REAL NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS account_token_grants_user
          ON account_token_grants(user_id, expires_at, starts_at);
        CREATE TABLE IF NOT EXISTS model_usage(call_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
          reserved_tokens INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
          status TEXT NOT NULL, created_at REAL NOT NULL,
          grant_holds_json TEXT NOT NULL DEFAULT '[]',
          permanent_reserved INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS model_usage_user ON model_usage(user_id);
        CREATE TABLE IF NOT EXISTS registration_devices(pair_hash TEXT PRIMARY KEY,
          user_id TEXT NOT NULL, registered_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS account_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO account_quota(user_id) SELECT user_id FROM accounts;
        """)
        usage_columns = {row[1] for row in self.db.execute("PRAGMA table_info(model_usage)")}
        with self.db:
            if "grant_holds_json" not in usage_columns:
                self.db.execute(
                    "ALTER TABLE model_usage ADD COLUMN grant_holds_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "permanent_reserved" not in usage_columns:
                self.db.execute(
                    "ALTER TABLE model_usage ADD COLUMN permanent_reserved INTEGER NOT NULL DEFAULT 0"
                )
            self.db.execute(
                "INSERT OR IGNORE INTO account_settings VALUES('device_secret',?)",
                (secrets.token_hex(32),),
            )
        self.costs = CostControl(self.db, cost_defaults)

    def device_secret(self) -> bytes:
        return bytes.fromhex(
            self.db.execute(
                "SELECT value FROM account_settings WHERE key='device_secret'"
            ).fetchone()[0]
        )

    def registration_wait(self, pair_hash: str, now: float) -> int:
        row = self.db.execute(
            "SELECT registered_at FROM registration_devices WHERE pair_hash=?", (pair_hash,)
        ).fetchone()
        return max(0, int(row[0] + REGISTRATION_WINDOW - now + 0.999)) if row else 0

    def token_limit(self, user_id: str) -> int | None:
        """The account allowance, or None for an explicitly exempt account."""
        if self.db.execute(
            "SELECT 1 FROM account_quota_unlimited WHERE user_id=?", (user_id,)
        ).fetchone():
            return None
        row = self.db.execute(
            "SELECT tokens FROM account_allowances WHERE user_id=?", (user_id,)
        ).fetchone()
        return (row[0] if row else FREE_TOKENS) + self.costs.control(user_id)["bonus_tokens"]

    def registration_allowance(self) -> int:
        value = self.costs._get("registration_free_tokens")
        return FREE_TOKENS if value is None else value

    def set_registration_allowance(self, tokens: int, admin: str) -> None:
        if type(tokens) is not int or not 0 <= tokens <= 1_000_000_000:
            raise ValueError("额度须为 0–1,000,000,000 的整数")
        with self.db:
            self.costs._put("registration_free_tokens", tokens)
            self.costs.audit(admin, "registration_allowance", {"tokens": tokens})

    def distribute_tokens(self, tokens: int, request_id: str, admin: str) -> dict:
        if type(tokens) is not int or not 1 <= tokens <= 1_000_000_000:
            raise ValueError("额度须为 1–1,000,000,000 的整数")
        request_id = str(uuid.UUID(request_id))
        try:
            self.db.execute("BEGIN IMMEDIATE")
            previous = self.db.execute(
                "SELECT tokens,recipients FROM quota_distributions WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if previous:
                if previous[0] != tokens:
                    raise AccountError(
                        "distribution_conflict", "该次发放已完成，请刷新后重新发放。"
                    )
                self.db.commit()
                return {"tokens": tokens, "recipients": previous[1], "replayed": True}
            users = self.db.execute(
                "SELECT user_id FROM accounts WHERE user_id NOT IN (SELECT user_id FROM account_quota_unlimited)"
            ).fetchall()
            for row in users:
                self.costs._ensure(row[0])
                self.db.execute(
                    "UPDATE account_controls SET bonus_tokens=bonus_tokens+? WHERE user_id=?",
                    (tokens, row[0]),
                )
            self.db.execute(
                "INSERT INTO quota_distributions VALUES(?,?,?,?)",
                (request_id, tokens, len(users), time.time()),
            )
            self.costs.audit(
                admin,
                "distribute_tokens",
                {"tokens": tokens, "recipients": len(users), "request_id": request_id},
            )
            self.db.commit()
            return {"tokens": tokens, "recipients": len(users), "replayed": False}
        except BaseException:
            self.db.rollback()
            raise

    def _active_grant_rows(self, user_id: str, now: float) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT grant_id,source,order_out_trade_no,plan_key,granted_tokens,used_tokens,"
            "held_tokens,starts_at,expires_at,created_at FROM account_token_grants "
            "WHERE user_id=? AND starts_at<=? AND expires_at>? "
            "ORDER BY expires_at ASC, created_at ASC, grant_id ASC",
            (user_id, now, now),
        ).fetchall()

    def _upcoming_grant_rows(self, user_id: str, now: float) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT grant_id,source,order_out_trade_no,plan_key,granted_tokens,used_tokens,"
            "held_tokens,starts_at,expires_at,created_at FROM account_token_grants "
            "WHERE user_id=? AND starts_at>? "
            "ORDER BY starts_at ASC, grant_id ASC",
            (user_id, now),
        ).fetchall()

    def add_subscription_grants(
        self,
        user_id: str,
        *,
        order_out_trade_no: str,
        plan_key: str,
        tokens_per_month: int,
        months: int,
        starts_at: float,
        source: str = "afdian",
        now: float | None = None,
    ) -> list[dict]:
        """Insert ``months`` consecutive rolling-month token grants. Idempotent per order."""
        if tokens_per_month <= 0 or months <= 0:
            return []
        created_at = time.time() if now is None else now
        created: list[dict] = []
        for idx in range(months):
            period_start = add_calendar_months(starts_at, idx)
            period_end = add_calendar_months(starts_at, idx + 1)
            grant_id = f"{source}-{order_out_trade_no}-{idx + 1}"
            self.db.execute(
                "INSERT OR IGNORE INTO account_token_grants"
                "(grant_id,user_id,source,order_out_trade_no,plan_key,granted_tokens,"
                "used_tokens,held_tokens,starts_at,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?,0,0,?,?,?)",
                (
                    grant_id,
                    user_id,
                    source,
                    order_out_trade_no,
                    plan_key,
                    tokens_per_month,
                    period_start,
                    period_end,
                    created_at,
                ),
            )
            created.append(
                {
                    "grant_id": grant_id,
                    "plan_key": plan_key,
                    "tokens": tokens_per_month,
                    "starts_at": period_start,
                    "expires_at": period_end,
                }
            )
        return created

    def quota(self, user_id: str, *, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        row = self.db.execute(
            "SELECT used_tokens,held_tokens FROM account_quota WHERE user_id=?", (user_id,)
        ).fetchone()
        perm_used, perm_held = (row[0], row[1]) if row else (0, 0)
        perm_limit = self.token_limit(user_id)
        grants = self._active_grant_rows(user_id, now)
        sub_granted = sum(g["granted_tokens"] for g in grants)
        sub_used = sum(g["used_tokens"] for g in grants)
        sub_held = sum(g["held_tokens"] for g in grants)
        sub_remaining = sum(
            max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"]) for g in grants
        )
        if perm_limit is None:
            return {
                "limit": None,
                "used": perm_used + sub_used,
                "reserved": perm_held + sub_held,
                "remaining": None,
            }
        perm_remaining = max(0, perm_limit - perm_used - perm_held)
        return {
            "limit": perm_limit + sub_granted,
            "used": perm_used + sub_used,
            "reserved": perm_held + sub_held,
            "remaining": perm_remaining + sub_remaining,
        }

    def quota_detail(self, user_id: str, *, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        row = self.db.execute(
            "SELECT used_tokens,held_tokens FROM account_quota WHERE user_id=?", (user_id,)
        ).fetchone()
        perm_used, perm_held = (row[0], row[1]) if row else (0, 0)
        perm_limit = self.token_limit(user_id)
        perm_remaining = None if perm_limit is None else max(0, perm_limit - perm_used - perm_held)
        active_rows = self._active_grant_rows(user_id, now)
        upcoming_rows = self._upcoming_grant_rows(user_id, now)

        def _fmt_grant(g: sqlite3.Row) -> dict:
            return {
                "grant_id": g["grant_id"],
                "plan_key": g["plan_key"],
                "granted": g["granted_tokens"],
                "used": g["used_tokens"],
                "reserved": g["held_tokens"],
                "remaining": max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"]),
                "starts_at": g["starts_at"],
                "expires_at": g["expires_at"],
            }

        active_grants = [_fmt_grant(g) for g in active_rows]
        upcoming_grants = [_fmt_grant(g) for g in upcoming_rows]
        sub_granted = sum(g["granted"] for g in active_grants)
        sub_used = sum(g["used"] for g in active_grants)
        sub_held = sum(g["reserved"] for g in active_grants)
        sub_remaining = sum(g["remaining"] for g in active_grants)
        total_limit = None if perm_limit is None else perm_limit + sub_granted
        total_remaining = None if perm_remaining is None else perm_remaining + sub_remaining
        return {
            "limit": total_limit,
            "used": perm_used + sub_used,
            "reserved": perm_held + sub_held,
            "remaining": total_remaining,
            "permanent": {
                "limit": perm_limit,
                "used": perm_used,
                "reserved": perm_held,
                "remaining": perm_remaining,
            },
            "subscription": {
                "limit": sub_granted,
                "used": sub_used,
                "reserved": sub_held,
                "remaining": sub_remaining,
                "active_grants": active_grants,
                "upcoming_grants": upcoming_grants,
                "earliest_expires_at": active_grants[0]["expires_at"] if active_grants else None,
                "latest_expires_at": (
                    max(g["expires_at"] for g in active_grants) if active_grants else None
                ),
            },
        }

    def reserve_tokens(
        self,
        user_id: str,
        input_bound: int,
        output_limit: int,
        *,
        model: str | None = None,
        now: float | None = None,
    ) -> tuple[str, int]:
        from harness.metering import QuotaExceeded, SiteBudgetExhausted

        try:
            self.db.execute("BEGIN IMMEDIATE")
            now = time.time() if now is None else now
            self.costs.gatekeep(user_id, now)
            row = self.db.execute(
                "SELECT used_tokens,held_tokens FROM account_quota WHERE user_id=?", (user_id,)
            ).fetchone()
            if row is None:
                raise QuotaExceeded()
            perm_limit = self.token_limit(user_id)
            grants: list[sqlite3.Row] = []
            if perm_limit is None:
                output = output_limit
            else:
                grants = self._active_grant_rows(user_id, now)
                sub_avail = sum(
                    max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"])
                    for g in grants
                )
                perm_avail = max(0, perm_limit - row[0] - row[1])
                output = min(output_limit, sub_avail + perm_avail - input_bound)
            if output < min(256, output_limit):
                raise QuotaExceeded()
            room = self.costs.budget_room(now)
            if room is not None:
                output = min(output, room - input_bound)
                if output < min(256, output_limit):
                    self.costs.budget_exhausted(now, input_bound + min(256, output_limit))
                    raise SiteBudgetExhausted()
            reservation = input_bound + output
            refusal = self.costs.trip(user_id, reservation, now)
            if refusal is not None:
                raise refusal
            call_id = uuid.uuid4().hex
            grant_holds: list[dict] = []
            remaining_to_hold = reservation
            if perm_limit is not None:
                for g in grants:
                    if remaining_to_hold <= 0:
                        break
                    avail = max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"])
                    take = min(avail, remaining_to_hold)
                    if take > 0:
                        self.db.execute(
                            "UPDATE account_token_grants SET held_tokens=held_tokens+? WHERE grant_id=?",
                            (take, g["grant_id"]),
                        )
                        grant_holds.append({"grant_id": g["grant_id"], "tokens": take})
                        remaining_to_hold -= take
            permanent_reserved = remaining_to_hold
            if permanent_reserved > 0:
                self.db.execute(
                    "UPDATE account_quota SET held_tokens=held_tokens+? WHERE user_id=?",
                    (permanent_reserved, user_id),
                )
            self.db.execute(
                "INSERT INTO model_usage VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    call_id,
                    user_id,
                    reservation,
                    None,
                    None,
                    "reserved",
                    now,
                    json.dumps(grant_holds),
                    permanent_reserved,
                ),
            )
            self.costs.reserve(call_id, user_id, model, reservation, now)
            self.db.commit()
            return call_id, output
        except QuotaExceeded:
            # A refusal keeps what it recorded: an auto-pause, a suspension, an event.
            self.db.commit()
            raise
        except BaseException:
            self.db.rollback()
            raise

    def settle_tokens(
        self,
        call_id: str,
        input_tokens: int | None,
        output_tokens: int | None,
        *,
        rejected: bool = False,
        error: str | None = None,
    ) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT * FROM model_usage WHERE call_id=?", (call_id,)
            ).fetchone()
            if row is None or row["status"] != "reserved":
                self.db.commit()
                return
            known = (
                isinstance(input_tokens, int)
                and input_tokens >= 0
                and isinstance(output_tokens, int)
                and output_tokens >= 0
            )
            used = (
                0 if rejected else input_tokens + output_tokens if known else row["reserved_tokens"]
            )
            status = "rejected" if rejected else "settled" if known else "uncertain"
            grant_holds = json.loads(row["grant_holds_json"] or "[]")
            perm_held_release = int(row["permanent_reserved"] or 0)
            if not grant_holds and perm_held_release == 0:
                # Backward compatibility with reservations created prior to dual-pool migration.
                perm_held_release = int(row["reserved_tokens"])
            remaining_used = used
            for entry in grant_holds:
                gid = entry["grant_id"]
                held_amt = int(entry["tokens"])
                charge = min(held_amt, remaining_used)
                remaining_used -= charge
                self.db.execute(
                    "UPDATE account_token_grants "
                    "SET held_tokens=MAX(0,held_tokens-?), used_tokens=used_tokens+? "
                    "WHERE grant_id=?",
                    (held_amt, charge, gid),
                )
            if remaining_used > 0 and grant_holds:
                for entry in grant_holds:
                    if remaining_used <= 0:
                        break
                    gid = entry["grant_id"]
                    g = self.db.execute(
                        "SELECT granted_tokens,used_tokens,held_tokens FROM account_token_grants "
                        "WHERE grant_id=?",
                        (gid,),
                    ).fetchone()
                    if g is None:
                        continue
                    headroom = max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"])
                    extra = min(headroom, remaining_used)
                    if extra > 0:
                        self.db.execute(
                            "UPDATE account_token_grants SET used_tokens=used_tokens+? WHERE grant_id=?",
                            (extra, gid),
                        )
                        remaining_used -= extra
            self.db.execute(
                "UPDATE account_quota SET held_tokens=MAX(0,held_tokens-?),used_tokens=used_tokens+? "
                "WHERE user_id=?",
                (perm_held_release, remaining_used, row["user_id"]),
            )
            self.db.execute(
                "UPDATE model_usage SET input_tokens=?,output_tokens=?,status=? WHERE call_id=?",
                (input_tokens, output_tokens, status, call_id),
            )
            self.costs.settle(call_id, input_tokens, output_tokens, status, error, time.time())
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    @staticmethod
    def public(row) -> dict:
        return {
            "user_id": row["user_id"],
            "email": row["username"],
            "created_at": row["created_at"],
            "privacy_version": row["privacy_version"],
            "privacy_accepted_at": row["privacy_accepted_at"],
        }

    def create(
        self,
        email: str,
        password_hash: str,
        *,
        pair_hash: str | None = None,
        registered_at: float | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        user_id = "acct-" + uuid.uuid4().hex
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if pair_hash:
                registered_at = time.time() if registered_at is None else registered_at
                if self.registration_wait(pair_hash, registered_at):
                    raise AccountError(
                        "registration_limited",
                        "同一 IP 下的此设备，7 天内只能注册一个账号，请登录已有账号。",
                    )
            with self.db:
                self.db.execute(
                    "INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?)",
                    (
                        user_id,
                        email,
                        email_key(email),
                        password_hash,
                        PRIVACY_VERSION,
                        now,
                        now,
                        now,
                    ),
                )
                self.db.execute("INSERT INTO account_quota(user_id) VALUES(?)", (user_id,))
                self.db.execute(
                    "INSERT INTO account_allowances VALUES(?,?)",
                    (user_id, self.registration_allowance()),
                )
                if pair_hash:
                    self.db.execute(
                        "INSERT OR REPLACE INTO registration_devices VALUES(?,?,?)",
                        (pair_hash, user_id, registered_at),
                    )
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise AccountError("email_taken", "该邮箱已被注册，请直接登录或换一个邮箱。") from exc
        except BaseException:
            self.db.rollback()
            raise
        return self.get(user_id)

    # ---------- administration ----------

    def list_accounts(self, query: str = "", offset: int = 0, limit: int = 50, since: float = 0):
        """Accounts with their credit, control state and spend since ``since``; newest first."""
        pattern = (
            "%"
            + username_key(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        where = "WHERE a.username_key LIKE ? ESCAPE '\\'"
        total = self.db.execute(f"SELECT COUNT(*) FROM accounts a {where}", (pattern,)).fetchone()[
            0
        ]
        rows = self.db.execute(
            "SELECT a.user_id,a.username,a.created_at,q.used_tokens,q.held_tokens,"
            "c.bonus_tokens,c.suspended_reason,c.suspended_at,c.suspended_by,"
            "(SELECT COUNT(*) FROM account_sessions s WHERE s.user_id=a.user_id),"
            "(SELECT COALESCE(SUM(CASE u.status WHEN 'settled' THEN u.input_tokens+u.output_tokens"
            " WHEN 'rejected' THEN 0 ELSE u.reserved_tokens END),0) FROM site_usage u"
            " WHERE u.user_id=a.user_id AND u.created_at>=?),"
            "EXISTS(SELECT 1 FROM account_quota_unlimited x WHERE x.user_id=a.user_id),"
            "(SELECT tokens FROM account_allowances b WHERE b.user_id=a.user_id) "
            "FROM accounts a LEFT JOIN account_quota q ON q.user_id=a.user_id "
            f"LEFT JOIN account_controls c ON c.user_id=a.user_id {where} "
            "ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
            (since, pattern, limit, offset),
        ).fetchall()
        now = time.time()
        items = []
        for row in rows:
            perm_limit = (
                None
                if row[11]
                else (row[12] if row[12] is not None else FREE_TOKENS) + (row[5] or 0)
            )
            perm_used, perm_held = row[3] or 0, row[4] or 0
            grants = self._active_grant_rows(row[0], now)
            sub_granted = sum(g["granted_tokens"] for g in grants)
            sub_used = sum(g["used_tokens"] for g in grants)
            sub_held = sum(g["held_tokens"] for g in grants)
            sub_remaining = sum(
                max(0, g["granted_tokens"] - g["used_tokens"] - g["held_tokens"]) for g in grants
            )
            limit_tokens = None if perm_limit is None else perm_limit + sub_granted
            remaining = (
                None
                if perm_limit is None
                else max(0, perm_limit - perm_used - perm_held) + sub_remaining
            )
            items.append(
                {
                    "user_id": row[0],
                    "email": row[1],
                    "created_at": row[2],
                    "quota": {
                        "limit": limit_tokens,
                        "used": perm_used + sub_used,
                        "reserved": perm_held + sub_held,
                        "remaining": remaining,
                        "bonus": row[5] or 0,
                        "subscription_limit": sub_granted,
                        "subscription_remaining": sub_remaining,
                        "subscription_expires_at": (
                            max(g["expires_at"] for g in grants) if grants else None
                        ),
                    },
                    "suspended": (
                        {"reason": row[6], "at": row[7], "by": row[8]}
                        if row[7] is not None
                        else None
                    ),
                    "logins": row[9],
                    "tokens_today": int(row[10]),
                }
            )
        return items, total

    def set_unlimited_quota(self, user_id: str, enabled: bool, admin: str) -> None:
        """Exempt an account from its own quota, retaining site budgets and usage metering."""
        if self.get(user_id) is None:
            raise AccountError("account_not_found", "找不到该账号。")
        with self.db:
            if enabled:
                self.db.execute(
                    "INSERT OR IGNORE INTO account_quota_unlimited VALUES(?)", (user_id,)
                )
            else:
                self.db.execute("DELETE FROM account_quota_unlimited WHERE user_id=?", (user_id,))
            self.costs.audit(admin, "set_unlimited_quota", {"user_id": user_id, "enabled": enabled})

    def set_suspended(self, user_id: str, reason: str | None, admin: str) -> None:
        with self.db:
            if reason is None:
                self.costs.unsuspend(user_id, admin)
            else:
                self.costs.suspend(user_id, reason, admin)

    def grant_tokens(self, user_id: str, tokens: int, admin: str) -> None:
        with self.db:
            self.costs.grant(user_id, tokens, admin)

    def revoke_all(self, user_id: str, admin: str) -> list[str]:
        """End every login of an account; returns the ended token hashes."""
        rows = self.db.execute(
            "SELECT token_hash FROM account_sessions WHERE user_id=?", (user_id,)
        ).fetchall()
        with self.db:
            self.db.execute("DELETE FROM account_sessions WHERE user_id=?", (user_id,))
            self.costs.audit(admin, "revoke_logins", {"user_id": user_id, "count": len(rows)})
        return [row[0] for row in rows]

    def undo_registration(self, user_id: str) -> None:
        """A failed guest hand-over must not consume this device's registration opportunity."""
        with self.db:
            self.db.execute("DELETE FROM registration_devices WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))

    def get(self, user_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)).fetchone()
        return self.public(row) if row else None

    def credentials(self, identifier: str) -> tuple[dict, str] | None:
        row = self.db.execute(
            "SELECT * FROM accounts WHERE username_key=?", (email_key(identifier),)
        ).fetchone()
        return (self.public(row), row["password_hash"]) if row else None

    def password_hash(self, user_id: str) -> str | None:
        row = self.db.execute(
            "SELECT password_hash FROM accounts WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else None

    def set_password(self, user_id: str, password_hash: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE accounts SET password_hash=?, password_changed_at=? WHERE user_id=?",
                (password_hash, datetime.now(UTC).isoformat(), user_id),
            )

    def delete(self, user_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM account_sessions WHERE user_id=?", (user_id,))
            self.db.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))
            self.costs.forget_user(user_id)

    def open_session(self, user_id: str, now: float, expires_at: float) -> str:
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute(
                "INSERT INTO account_sessions VALUES(?,?,?,?)",
                (token_digest(token), user_id, now, expires_at),
            )
        return token

    def session_user(self, token: str, now: float) -> str | None:
        row = self.db.execute(
            "SELECT user_id FROM account_sessions WHERE token_hash=? AND expires_at>?",
            (token_digest(token), now),
        ).fetchone()
        return row[0] if row else None

    def extend_session(self, token: str, expires_at: float) -> None:
        with self.db:
            self.db.execute(
                "UPDATE account_sessions SET expires_at=MAX(expires_at,?) WHERE token_hash=?",
                (expires_at, token_digest(token)),
            )

    def revoke(self, token: str) -> None:
        with self.db:
            self.db.execute(
                "DELETE FROM account_sessions WHERE token_hash=?", (token_digest(token),)
            )

    def revoke_others(self, user_id: str, keep: str) -> list[str]:
        """End every other login of the account; returns the ended token hashes."""
        rows = self.db.execute(
            "SELECT token_hash FROM account_sessions WHERE user_id=? AND token_hash<>?",
            (user_id, token_digest(keep)),
        ).fetchall()
        with self.db:
            self.db.execute(
                "DELETE FROM account_sessions WHERE user_id=? AND token_hash<>?",
                (user_id, token_digest(keep)),
            )
        return [row[0] for row in rows]

    def purge_sessions(self, now: float) -> list[str]:
        with self.db:
            self.db.execute(
                "DELETE FROM registration_devices WHERE registered_at<=?",
                (now - REGISTRATION_WINDOW,),
            )
            self.costs.prune(now)
        rows = self.db.execute(
            "SELECT token_hash FROM account_sessions WHERE expires_at<=?", (now,)
        ).fetchall()
        if rows:
            with self.db:
                self.db.execute("DELETE FROM account_sessions WHERE expires_at<=?", (now,))
        return [row[0] for row in rows]

    def close(self) -> None:
        self.db.close()
