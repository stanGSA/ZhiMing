from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.session import Session


class Tracer:
    def __init__(self, root: Path):
        self.root = root

    def user_dir(self, user_id: str) -> Path:
        return self.root / hashlib.sha256(user_id.encode()).hexdigest()[:24]

    def log(self, session: Session, event: str, **payload: Any) -> None:
        directory = self.user_dir(session.user_id)
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "session_id": session.id,
            "parent_session_id": session.parent_id,
            "reading_id": session.state.get("active_reading_id"),
            "role": session.role,
            **payload,
        }
        with (directory / f"{session.id}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def clock() -> float:
        return time.perf_counter()
