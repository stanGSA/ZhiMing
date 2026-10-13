from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import yaml

from knowledge.catalogues import expected_keys
from knowledge.schema import Entry
from plugins.dream.match import fts_tokens
from plugins.tarot.catalogue import DECK, SPREADS

ROOT = Path(__file__).resolve().parents[1]


def build(
    source_dir: Path | None = None, output: Path | None = None, rules_dir: Path | None = None
) -> dict:
    source_dir = source_dir or ROOT / "knowledge/sources"
    output = output or ROOT / "data/kb.sqlite"
    rules_dir = rules_dir or ROOT / "knowledge/rules"
    entries = []
    digest = hashlib.sha256()
    files = sorted(source_dir.rglob("*.yaml"))
    if not files:
        raise ValueError("知识库源文件为空")
    for path in files:
        raw = path.read_bytes()
        digest.update(path.relative_to(source_dir).as_posix().encode())
        digest.update(raw.replace(b"\r\n", b"\n"))
        content = yaml.safe_load(raw)
        entries.extend(Entry.model_validate(e) for e in content["entries"])
    rules = {}
    for path in sorted(rules_dir.glob("*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        rule = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(rule.get("version"), int) or rule["version"] < 1:
            raise ValueError("规则必须带版本号")
        if rule["system"] in rules:
            raise ValueError("规则体系重复")
        rules[rule["system"]] = rule
    ids, keys, aliases = set(), set(), set()
    for entry in entries:
        key = (entry.system, entry.kind, entry.key)
        if entry.id in ids or key in keys:
            raise ValueError(f"条目 id 或 key 重复：{entry.id}")
        if entry.id != f"kb:{entry.system}:{entry.kind}:{entry.key}":
            raise ValueError(f"条目 id 与字段不一致：{entry.id}")
        if entry.license != "本项目自写":
            raise ValueError(f"不接受未确认授权的释义：{entry.id}")
        if any(not -1 <= value <= 1 for value in entry.theme_map.values()):
            raise ValueError("theme_map 数值超界")
        for alias in entry.synonyms:
            alias_key = (entry.system, entry.kind, alias)
            if alias_key in aliases:
                raise ValueError(f"同义词重复：{alias}")
            aliases.add(alias_key)
        ids.add(entry.id)
        keys.add(key)
    expected = {
        ("tarot", "card", f"{card_id}:{orientation}")
        for card_id, _ in DECK
        for orientation in ("upright", "reversed")
    }
    expected |= {
        ("tarot", "position", f"{spread}:{i + 1}")
        for spread, positions in SPREADS.items()
        for i in range(len(positions))
    }
    partitions = {e.system for e in entries}
    for system in ("astro", "bazi", "name", "dream", "daily"):
        if system in partitions:
            expected |= expected_keys(system)
            if system not in rules:
                raise ValueError(f"缺少{system}组合规则")
    symbols = sum(e.system == "dream" and e.kind == "symbol" for e in entries)
    if "dream" in partitions and symbols < 300:
        raise ValueError(f"解梦意象不足300条：{symbols}")
    missing = sorted(expected - keys)
    if missing:
        raise ValueError(f"释义覆盖不完整：{missing}")
    if "tarot" not in rules:
        raise ValueError("缺少塔罗规则")
    for spread, positions in SPREADS.items():
        strengths = rules["tarot"]["position_strength"].get(spread, [])
        if len(strengths) != len(positions) or any(not 0 <= v <= 1 for v in strengths):
            raise ValueError("牌位强度规则不完整或超界")
    version = f"v1-{digest.hexdigest()[:16]}"
    reviewed_count = sum(e.reviewed for e in entries)
    report = {
        "kb_version": version,
        "entries": len(entries),
        "card_states": 156,
        "positions": 7,
        "coverage": 1.0,
        "reviewed_count": reviewed_count,
        "reviewed_rate": reviewed_count / len(entries),
        "missing": missing,
        "partitions": {
            system: {
                "entries": sum(e.system == system for e in entries),
                "expected": sum(key[0] == system for key in expected),
                "coverage": 1.0,
                "reviewed_rate": sum(e.reviewed for e in entries if e.system == system)
                / sum(e.system == system for e in entries),
            }
            for system in sorted(partitions)
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    archive = output.parent / "kb_versions" / f"{version}.sqlite"
    archive.parent.mkdir(parents=True, exist_ok=True)
    # Preserve immutable editions for historical readings; current file is only a copy.
    if not archive.exists():
        temporary = archive.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        with sqlite3.connect(temporary) as db:
            db.executescript("""
            CREATE TABLE entries(id TEXT PRIMARY KEY, system TEXT NOT NULL, kind TEXT NOT NULL,
              key TEXT NOT NULL, entry_json TEXT NOT NULL, UNIQUE(system,kind,key));
            CREATE TABLE synonyms(system TEXT,kind TEXT,alias TEXT,entry_id TEXT,
              PRIMARY KEY(system,kind,alias));
            CREATE TABLE rules(system TEXT PRIMARY KEY, rule_json TEXT NOT NULL);
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE VIRTUAL TABLE entries_fts USING fts5(id UNINDEXED, keywords, text);
            CREATE VIRTUAL TABLE dream_fts USING fts5(id UNINDEXED, alias UNINDEXED, tokens);
            """)
            for entry in entries:
                db.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?)",
                    (entry.id, entry.system, entry.kind, entry.key, entry.model_dump_json()),
                )
                for alias in entry.synonyms:
                    db.execute(
                        "INSERT INTO synonyms VALUES(?,?,?,?)",
                        (entry.system, entry.kind, alias, entry.id),
                    )
                db.execute(
                    "INSERT INTO entries_fts VALUES(?,?,?)",
                    (entry.id, " ".join(entry.keywords), entry.text),
                )
                if entry.system == "dream" and entry.kind == "symbol":
                    # FTS5 does not segment Chinese: index character bigrams of every alias.
                    for alias in [entry.key, *entry.synonyms]:
                        db.execute(
                            "INSERT INTO dream_fts VALUES(?,?,?)",
                            (entry.id, alias, " ".join(fts_tokens(alias))),
                        )
            db.executemany(
                "INSERT INTO rules VALUES(?,?)", [(k, json.dumps(v)) for k, v in rules.items()]
            )
            db.executemany(
                "INSERT INTO meta VALUES(?,?)",
                [("kb_version", version), ("coverage", json.dumps(report))],
            )
        db.close()  # sqlite3 context manager commits, but does not close the Windows file handle.
        temporary.replace(archive)
    current_temp = output.with_suffix(".tmp")
    shutil.copyfile(archive, current_temp)
    current_temp.replace(output)
    output.with_suffix(".coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(output=args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
