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
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Bump when the privacy notice (web_static/privacy.html) changes in substance.
PRIVACY_VERSION = "2026-10-29"
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
    def __init__(self, path: Path):
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
        """)

    @staticmethod
    def public(row) -> dict:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "created_at": row["created_at"],
            "privacy_version": row["privacy_version"],
            "privacy_accepted_at": row["privacy_accepted_at"],
        }

    def create(self, username: str, password_hash: str) -> dict:
        now = datetime.now(UTC).isoformat()
        user_id = "acct-" + uuid.uuid4().hex
        try:
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
        except sqlite3.IntegrityError as exc:
            raise AccountError("username_taken", "该账号名已被使用，请换一个。") from exc
        return self.get(user_id)

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
        rows = self.db.execute(
            "SELECT token_hash FROM account_sessions WHERE expires_at<=?", (now,)
        ).fetchall()
        if rows:
            with self.db:
                self.db.execute("DELETE FROM account_sessions WHERE expires_at<=?", (now,))
        return [row[0] for row in rows]

    def close(self) -> None:
        self.db.close()
