from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(user_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL,
          version INTEGER NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profile_history(user_id TEXT NOT NULL,version INTEGER NOT NULL,
          profile_json TEXT NOT NULL,evidence TEXT NOT NULL,updated_at TEXT NOT NULL,
          PRIMARY KEY(user_id,version));
        CREATE TABLE IF NOT EXISTS readings(reading_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,
          session_id TEXT NOT NULL,parent_reading_id TEXT,question TEXT NOT NULL,question_type TEXT NOT NULL,
          systems_used TEXT NOT NULL,tarot_json TEXT,signals_json TEXT NOT NULL,output_json TEXT NOT NULL,
          kb_version TEXT NOT NULL,profile_version INTEGER NOT NULL,mode TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS readings_user ON readings(user_id,created_at);
        CREATE TABLE IF NOT EXISTS reading_responses(response_id TEXT PRIMARY KEY,
          reading_id TEXT NOT NULL,user_id TEXT NOT NULL,session_id TEXT NOT NULL,
          question TEXT NOT NULL,output_json TEXT NOT NULL,created_at TEXT NOT NULL,
          FOREIGN KEY(reading_id) REFERENCES readings(reading_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS specialist_reports(reading_id TEXT NOT NULL,system TEXT NOT NULL,
          report_json TEXT NOT NULL,latency_ms REAL,tokens INTEGER,PRIMARY KEY(reading_id,system),
          FOREIGN KEY(reading_id) REFERENCES readings(reading_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS review_notes(reading_id TEXT NOT NULL,round INTEGER NOT NULL,
          verdict TEXT NOT NULL,issues_json TEXT NOT NULL,PRIMARY KEY(reading_id,round),
          FOREIGN KEY(reading_id) REFERENCES readings(reading_id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS daily(user_id TEXT NOT NULL,date TEXT NOT NULL,result_json TEXT NOT NULL,
          kb_version TEXT NOT NULL,PRIMARY KEY(user_id,date));
        CREATE TABLE IF NOT EXISTS charts(chart_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,
          input_hash TEXT NOT NULL,result_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bazi_charts(bazi_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,
          input_hash TEXT NOT NULL,result_json TEXT NOT NULL);
        PRAGMA user_version=2;
        """)

    def get_profile(self, user_id: str) -> dict:
        row = self.db.execute(
            "SELECT profile_json,version FROM profiles WHERE user_id=?", (user_id,)
        ).fetchone()
        return (
            {**json.loads(row["profile_json"]), "version": row["version"]}
            if row
            else {"version": 0}
        )

    def update_profile(self, user_id: str, field: str, value, evidence: str) -> dict:
        profile = self.get_profile(user_id)
        version = profile.pop("version") + 1
        profile[field] = value
        encoded = json.dumps(profile, ensure_ascii=False)
        now = datetime.now(UTC).isoformat()
        with self.db:
            self.db.execute(
                "INSERT INTO profiles VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                "profile_json=excluded.profile_json,version=excluded.version,updated_at=excluded.updated_at",
                (user_id, encoded, version, now),
            )
            self.db.execute(
                "INSERT INTO profile_history VALUES(?,?,?,?,?)",
                (user_id, version, encoded, evidence, now),
            )
        return {**profile, "version": version}

    def save_reading(self, session, output: dict) -> None:
        state = session.state
        with self.db:
            self.db.execute(
                "INSERT INTO readings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    state["active_reading_id"],
                    session.user_id,
                    session.id,
                    state.get("parent_reading_id"),
                    state["question"],
                    output["question_type"],
                    json.dumps(output["systems_used"]),
                    json.dumps(state.get("tarot_result"), ensure_ascii=False),
                    json.dumps(state["signals"], ensure_ascii=False),
                    json.dumps(output, ensure_ascii=False),
                    state["kb_version"],
                    session.profile.get("version", 0),
                    "single",
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_reading(self, user_id: str, reading_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM readings WHERE user_id=? AND reading_id=?", (user_id, reading_id)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        for field in ("systems_used", "tarot_json", "signals_json", "output_json"):
            result[field] = json.loads(result[field]) if result[field] else None
        return result

    def recent_readings(self, user_id: str, limit: int = 3) -> list[dict]:
        rows = self.db.execute(
            "SELECT reading_id,question,output_json,kb_version FROM readings "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "reading_id": row["reading_id"],
                "question": row["question"],
                "summary": json.loads(row["output_json"])["summary"],
                "kb_version": row["kb_version"],
            }
            for row in rows
        ]

    def save_response(self, session, output: dict) -> str:
        import uuid

        response_id = uuid.uuid4().hex
        if not self.get_reading(session.user_id, session.state["active_reading_id"]):
            raise ValueError("记录不属于当前用户")
        with self.db:
            self.db.execute(
                "INSERT INTO reading_responses VALUES(?,?,?,?,?,?,?)",
                (
                    response_id,
                    session.state["active_reading_id"],
                    session.user_id,
                    session.id,
                    session.user_messages[-1],
                    json.dumps(output, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return response_id

    def get_response(self, user_id: str, response_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM reading_responses WHERE user_id=? AND response_id=?",
            (user_id, response_id),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["output_json"] = json.loads(result["output_json"])
        return result

    def forget(self, user_id: str) -> None:
        with self.db:
            for table in (
                "profiles",
                "profile_history",
                "readings",
                "daily",
                "charts",
                "bazi_charts",
            ):
                self.db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        # Clear SQLite free pages; do not promise forensic erasure of filesystem backups.
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute("VACUUM")

    def close(self):
        self.db.close()
