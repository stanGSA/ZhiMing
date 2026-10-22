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
        CREATE TABLE IF NOT EXISTS web_identities(user_id TEXT PRIMARY KEY,expires_at REAL NOT NULL);
        PRAGMA user_version=2;
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(readings)")}
        with self.db:
            for name, definition in (
                ("chart_id", "TEXT"),
                ("bazi_id", "TEXT"),
                ("calculations_json", "TEXT NOT NULL DEFAULT '{}'"),
                # Week 5: the cross-system table as computed when the reading was saved, so a
                # later weight or rule change never rewrites what an old reading said.
                ("merge_json", "TEXT NOT NULL DEFAULT '{}'"),
            ):
                if name not in columns:
                    self.db.execute(f"ALTER TABLE readings ADD COLUMN {name} {definition}")
            self.db.execute("PRAGMA user_version=4")

    def cached_calculation(self, system, user_id, inputs, calculate):
        import hashlib
        import uuid

        table, id_field = (
            ("charts", "chart_id") if system == "astro" else ("bazi_charts", "bazi_id")
        )
        # Data hashes and implementation revision invalidate stale computation caches.
        manifest = Path(__file__).resolve().parents[1] / "scripts/data_manifest.yaml"
        implementation = Path(__file__).resolve().parents[1] / f"plugins/{system}/calculator.py"
        key = hashlib.sha256(
            (
                "week23-calc-v1:"
                + hashlib.sha256(implementation.read_bytes()).hexdigest()
                + manifest.read_text(encoding="utf-8")
                + json.dumps(inputs, sort_keys=True, ensure_ascii=False)
            ).encode()
        ).hexdigest()
        row = self.db.execute(
            f"SELECT result_json FROM {table} WHERE user_id=? AND input_hash=?", (user_id, key)
        ).fetchone()
        if row:
            return json.loads(row[0]), True
        result = calculate()
        result[id_field] = uuid.uuid4().hex
        with self.db:
            self.db.execute(
                f"INSERT INTO {table} VALUES(?,?,?,?)",
                (result[id_field], user_id, key, json.dumps(result, ensure_ascii=False)),
            )
        return result, False

    def get_calculation(self, system, user_id, identity):
        table, id_field = (
            ("charts", "chart_id") if system == "astro" else ("bazi_charts", "bazi_id")
        )
        row = self.db.execute(
            f"SELECT result_json FROM {table} WHERE user_id=? AND {id_field}=?", (user_id, identity)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def get_daily(self, user_id: str, day: str) -> dict | None:
        row = self.db.execute(
            "SELECT result_json, kb_version FROM daily WHERE user_id=? AND date=?", (user_id, day)
        ).fetchone()
        if not row:
            return None
        return {"result": json.loads(row["result_json"]), "kb_version": row["kb_version"]}

    def save_daily(self, user_id: str, day: str, result: dict, kb_version: str) -> None:
        # One row per (user, date): the same day always reads back the same result. A row is
        # replaced only when the birth data it was computed from has changed.
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO daily VALUES(?,?,?,?)",
                (user_id, day, json.dumps(result, ensure_ascii=False), kb_version),
            )

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

    def save_reading(
        self,
        session,
        output: dict,
        mode: str = "single",
        reports: dict | None = None,
        merge: dict | None = None,
        reviews: list[dict] | None = None,
    ) -> None:
        state = session.state
        with self.db:
            self.db.execute(
                "INSERT INTO readings(reading_id,user_id,session_id,parent_reading_id,question,question_type,systems_used,tarot_json,signals_json,output_json,kb_version,profile_version,mode,created_at,chart_id,bazi_id,calculations_json,merge_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    mode,
                    datetime.now(UTC).isoformat(),
                    state.get("chart_id"),
                    state.get("bazi_id"),
                    json.dumps(state.get("calculations", {}), ensure_ascii=False),
                    json.dumps(merge or {}, ensure_ascii=False, default=str),
                ),
            )
            # Reviews happen before the reading exists; they are written in the same
            # transaction so a released reading always carries its review history.
            for review in reviews or []:
                details = {k: v for k, v in review.items() if k not in ("round", "verdict")}
                self.db.execute(
                    "INSERT INTO review_notes VALUES(?,?,?,?)",
                    (
                        state["active_reading_id"],
                        review["round"],
                        review["verdict"],
                        json.dumps(details, ensure_ascii=False),
                    ),
                )
            # Signals already live in readings.signals_json; keep only their references here.
            for system, report in (reports or {}).items():
                stored = {k: v for k, v in report.items() if k != "signals"}
                stored["signal_refs"] = sorted({s["ref_id"] for s in report.get("signals", [])})
                self.db.execute(
                    "INSERT OR REPLACE INTO specialist_reports VALUES(?,?,?,?,?)",
                    (
                        state["active_reading_id"],
                        system,
                        json.dumps(stored, ensure_ascii=False),
                        report.get("latency_ms"),
                        report.get("tokens"),
                    ),
                )

    def specialist_reports(self, user_id: str, reading_id: str) -> dict:
        rows = self.db.execute(
            "SELECT s.system, s.report_json FROM specialist_reports s "
            "JOIN readings r ON r.reading_id = s.reading_id WHERE r.user_id=? AND s.reading_id=?",
            (user_id, reading_id),
        ).fetchall()
        return {row["system"]: json.loads(row["report_json"]) for row in rows}

    def get_reading(self, user_id: str, reading_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM readings WHERE user_id=? AND reading_id=?", (user_id, reading_id)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        for field in (
            "systems_used",
            "tarot_json",
            "signals_json",
            "output_json",
            "calculations_json",
            "merge_json",
        ):
            if field in result:
                result[field] = json.loads(result[field]) if result[field] else None
        return result

    def review_notes(self, user_id: str, reading_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT n.round, n.verdict, n.issues_json FROM review_notes n "
            "JOIN readings r ON r.reading_id = n.reading_id WHERE r.user_id=? AND n.reading_id=? "
            "ORDER BY n.round",
            (user_id, reading_id),
        ).fetchall()
        return [
            {"round": row["round"], "verdict": row["verdict"], **json.loads(row["issues_json"])}
            for row in rows
        ]

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

    def reading_history(self, user_id: str, limit: int = 30) -> list[dict]:
        """Browser footprints: recent readings plus the systems and time shown in the list."""
        rows = self.db.execute(
            "SELECT reading_id,question,output_json,kb_version,systems_used,created_at "
            "FROM readings WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "reading_id": row["reading_id"],
                "question": row["question"],
                "summary": json.loads(row["output_json"])["summary"],
                "kb_version": row["kb_version"],
                "systems_used": json.loads(row["systems_used"]),
                "created_at": row["created_at"],
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

    def touch_web_identity(self, user_id: str, expires_at: float) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO web_identities VALUES(?,?) ON CONFLICT(user_id) "
                "DO UPDATE SET expires_at=excluded.expires_at",
                (user_id, expires_at),
            )

    def adopt_web_identities(self, expires_at: float) -> None:
        """Give pre-lease browser records one idle period before orphan cleanup."""
        with self.db:
            for table in (
                "profiles",
                "profile_history",
                "readings",
                "daily",
                "charts",
                "bazi_charts",
            ):
                self.db.execute(
                    f"INSERT OR IGNORE INTO web_identities SELECT DISTINCT user_id,? FROM {table} "
                    "WHERE user_id LIKE 'web-%'",
                    (expires_at,),
                )

    def expired_web_identities(self, now: float) -> list[str]:
        return [
            row[0]
            for row in self.db.execute(
                "SELECT user_id FROM web_identities WHERE expires_at<=?", (now,)
            )
        ]

    def forget(self, user_id: str) -> None:
        with self.db:
            for table in (
                "profiles",
                "profile_history",
                "readings",
                "daily",
                "charts",
                "bazi_charts",
                "web_identities",
            ):
                self.db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        # Clear SQLite free pages; do not promise forensic erasure of filesystem backups.
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.execute("VACUUM")

    def close(self):
        self.db.close()
