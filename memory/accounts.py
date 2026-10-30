"""Browser accounts: registration, password hashes and login tokens.

Passwords are kept only as salted scrypt hashes. A login token is random; the database keeps
its SHA-256, so a copy of the database cannot be replayed as a browser cookie. Records that
belong to an account live in the ordinary business tables (memory/store.py) under its user id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path

from memory.costs import CostControl

# Bump when the privacy notice (web_static/privacy.html) changes in substance.
PRIVACY_VERSION = "2026-10-30"
FREE_TOKENS = 250_000
REGISTRATION_WINDOW = 7 * 24 * 3600
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
USERNAME = re.compile(r"[0-9A-Za-z_\-\u4e00-\u9fff]{2,32}")


class AccountError(ValueError):
    """A refusal the browser can show as is."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def username_key(value: str) -> str:
    """Account names are unique regardless of case and full/half width."""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def check_username(value: str) -> str:
    name = unicodedata.normalize("NFKC", value).strip()
    if not USERNAME.fullmatch(name):
        raise AccountError(
            "invalid_username",
            "账号名需为 2–32 个字符，只能包含汉字、字母、数字、下划线或连字符。",
        )
    return name


def check_password(password: str, username: str = "") -> None:
    if len(password) < 8:
        raise AccountError("weak_password", "密码至少需要 8 个字符。")
    if len(password) > 128:
        raise AccountError("weak_password", "密码不能超过 128 个字符。")
    kinds = sum(bool(re.search(p, password)) for p in (r"[A-Za-z]", r"\d", r"[^A-Za-z\d]"))
    if kinds < 2:
        raise AccountError("weak_password", "密码需包含字母、数字、符号中的至少两类。")
    if username and username_key(password) == username_key(username):
        raise AccountError("weak_password", "密码不能与账号名相同。")


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
        CREATE TABLE IF NOT EXISTS model_usage(call_id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES accounts(user_id) ON DELETE CASCADE,
          reserved_tokens INTEGER NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
          status TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS model_usage_user ON model_usage(user_id);
        CREATE TABLE IF NOT EXISTS registration_devices(pair_hash TEXT PRIMARY KEY,
          user_id TEXT NOT NULL, registered_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS account_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO account_quota(user_id) SELECT user_id FROM accounts;
        """)
        with self.db:
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
        return FREE_TOKENS + self.costs.control(user_id)["bonus_tokens"]

    def quota(self, user_id: str) -> dict:
        row = self.db.execute(
            "SELECT used_tokens,held_tokens FROM account_quota WHERE user_id=?", (user_id,)
        ).fetchone()
        used, held = (row[0], row[1]) if row else (0, 0)
        limit = self.token_limit(user_id)
        return {
            "limit": limit,
            "used": used,
            "reserved": held,
            "remaining": None if limit is None else max(0, limit - used - held),
        }

    def reserve_tokens(
        self, user_id: str, input_bound: int, output_limit: int, *, model: str | None = None
    ) -> tuple[str, int]:
        from harness.metering import QuotaExceeded, SiteBudgetExhausted

        try:
            self.db.execute("BEGIN IMMEDIATE")
            now = time.time()
            self.costs.gatekeep(user_id, now)
            row = self.db.execute(
                "SELECT used_tokens,held_tokens FROM account_quota WHERE user_id=?", (user_id,)
            ).fetchone()
            if row is None:
                raise QuotaExceeded()
            limit = self.token_limit(user_id)
            output = (
                output_limit
                if limit is None
                else min(output_limit, limit - row[0] - row[1] - input_bound)
            )
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
            self.db.execute(
                "UPDATE account_quota SET held_tokens=held_tokens+? WHERE user_id=?",
                (reservation, user_id),
            )
            self.db.execute(
                "INSERT INTO model_usage VALUES(?,?,?,?,?,?,?)",
                (call_id, user_id, reservation, None, None, "reserved", now),
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
            self.db.execute(
                "UPDATE account_quota SET held_tokens=held_tokens-?,used_tokens=used_tokens+? WHERE user_id=?",
                (row["reserved_tokens"], used, row["user_id"]),
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
            "username": row["username"],
            "created_at": row["created_at"],
            "privacy_version": row["privacy_version"],
            "privacy_accepted_at": row["privacy_accepted_at"],
        }

    def create(
        self,
        username: str,
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
                        username,
                        username_key(username),
                        password_hash,
                        PRIVACY_VERSION,
                        now,
                        now,
                        now,
                    ),
                )
                self.db.execute("INSERT INTO account_quota(user_id) VALUES(?)", (user_id,))
                if pair_hash:
                    self.db.execute(
                        "INSERT OR REPLACE INTO registration_devices VALUES(?,?,?)",
                        (pair_hash, user_id, registered_at),
                    )
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise AccountError("username_taken", "该账号名已被使用，请换一个。") from exc
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
            "EXISTS(SELECT 1 FROM account_quota_unlimited x WHERE x.user_id=a.user_id) "
            "FROM accounts a LEFT JOIN account_quota q ON q.user_id=a.user_id "
            f"LEFT JOIN account_controls c ON c.user_id=a.user_id {where} "
            "ORDER BY a.created_at DESC LIMIT ? OFFSET ?",
            (since, pattern, limit, offset),
        ).fetchall()
        items = []
        for row in rows:
            limit_tokens = None if row[11] else FREE_TOKENS + (row[5] or 0)
            used, held = row[3] or 0, row[4] or 0
            items.append(
                {
                    "user_id": row[0],
                    "username": row[1],
                    "created_at": row[2],
                    "quota": {
                        "limit": limit_tokens,
                        "used": used,
                        "reserved": held,
                        "remaining": (
                            None if limit_tokens is None else max(0, limit_tokens - used - held)
                        ),
                        "bonus": row[5] or 0,
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

    def credentials(self, username: str) -> tuple[dict, str] | None:
        row = self.db.execute(
            "SELECT * FROM accounts WHERE username_key=?", (username_key(username),)
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
