from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from knowledge.review import normalize_entry


class KnowledgeBase:
    def __init__(self, path: Path, version: str | None = None):
        canonical_path = path
        if version:
            # Versions are identifiers, never user-controlled filesystem paths.
            if (
                not version.startswith("v1-")
                or len(version) != 19
                or any(c not in "0123456789abcdef" for c in version[3:])
            ):
                raise ValueError("Invalid knowledge version")
            folder = (
                path.parent if path.parent.name == "kb_versions" else path.parent / "kb_versions"
            )
            path = folder / f"{version}.sqlite"
        if not path.is_file():
            raise FileNotFoundError("知识库不存在，请先运行 python -m knowledge.build")
        self.path = canonical_path
        if version is None:
            # Hold immutable editions, not the replaceable current pointer.
            probe = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                edition = probe.execute("SELECT value FROM meta WHERE key='kb_version'").fetchone()[
                    0
                ]
            finally:
                probe.close()
            archive = path.parent / "kb_versions" / f"{edition}.sqlite"
            if archive.is_file():
                path = archive
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        self.version = self.db.execute("SELECT value FROM meta WHERE key='kb_version'").fetchone()[
            0
        ]

    def lookup(self, system: str, kind: str, key: str) -> dict | None:
        row = self.db.execute(
            "SELECT entry_json FROM entries WHERE system=? AND kind=? AND key=?",
            (system, kind, key),
        ).fetchone()
        if not row:
            row = self.db.execute(
                """SELECT e.entry_json FROM entries e JOIN synonyms s ON e.id=s.entry_id
              WHERE s.system=? AND s.kind=? AND s.alias=?""",
                (system, kind, key),
            ).fetchone()
        if not row:
            return None
        # Editions built before the three review levels carry ``reviewed`` only.
        entry = normalize_entry(json.loads(row[0]))
        entry["ref_id"] = f"{entry['id']}@{self.version}"
        return entry

    def rules(self, system: str) -> dict:
        row = self.db.execute("SELECT rule_json FROM rules WHERE system=?", (system,)).fetchone()
        if row is None:
            raise ValueError("缺少规则")
        return json.loads(row[0])

    def close(self) -> None:
        self.db.close()
