import json
import sqlite3

import pytest
import yaml

from knowledge.build import build
from knowledge.kb import KnowledgeBase


def edit_source(project, change):
    path = project / "sources/tarot/cards.yaml"
    source = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(source["entries"])
    path.write_text(yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8")


def rebuild(project):
    return build(
        project / "sources", project / "data/kb.sqlite", project / "rules", project / "reviews"
    )


def test_build_coverage_and_repeatability(project):
    first = rebuild(project)
    assert first == rebuild(project)
    assert first["partitions"]["tarot"]["entries"] == 163
    assert first["entries"] == sum(p["entries"] for p in first["partitions"].values())
    assert first["coverage"] == 1
    assert first["reviewed_rate"] == 0


def test_exact_alias_and_no_fuzzy_lookup(runtime):
    direct = runtime.kb.lookup("tarot", "card", "the_tower:upright")
    alias = runtime.kb.lookup("tarot", "card", "高塔:正位")
    assert direct == alias
    assert runtime.kb.lookup("tarot", "card", "高塔") is None
    assert runtime.kb.lookup("bazi", "card", "the_tower:upright") is None
    with pytest.raises(sqlite3.OperationalError):
        runtime.kb.db.execute("DELETE FROM entries")


@pytest.mark.parametrize(
    "issue", ["duplicate", "missing", "license", "valence", "wrong_id", "duplicate_alias"]
)
def test_build_rejects_invalid_sources(project, issue):
    def change(entries):
        if issue == "duplicate":
            entries.append(entries[0].copy())
        elif issue == "missing":
            entries.pop(0)
        elif issue == "license":
            entries[0]["license"] = "未经核实的网站文案"
        elif issue == "valence":
            entries[0]["theme_map"]["self"] = 2
        elif issue == "wrong_id":
            entries[0]["id"] = "kb:tarot:card:wrong"
        else:
            entries[1]["synonyms"] = entries[0]["synonyms"]

    edit_source(project, change)
    with pytest.raises(ValueError):
        rebuild(project)


def test_old_edition_survives_rebuild(project):
    first = rebuild(project)
    old_kb = KnowledgeBase(project / "data/kb.sqlite", first["kb_version"])
    old_entry = old_kb.lookup("tarot", "card", "the_fool:upright")
    old_kb.close()
    edit_source(
        project,
        lambda entries: entries[0].update(
            text="第二版独立测试释义，不应覆盖已经保存的历史版本。", version=2
        ),
    )
    second = rebuild(project)
    assert first["kb_version"] != second["kb_version"]
    current = KnowledgeBase(project / "data/kb.sqlite")
    archived = KnowledgeBase(project / "data/kb.sqlite", first["kb_version"])
    try:
        assert archived.lookup("tarot", "card", "the_fool:upright") == old_entry
        assert current.lookup("tarot", "card", "the_fool:upright")["text"] != old_entry["text"]
    finally:
        current.close()
        archived.close()


def test_rule_change_changes_version(project):
    first = rebuild(project)
    path = project / "rules/tarot.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules["version"] = 2
    rules["position_strength"]["single"] = [0.2]
    path.write_text(yaml.safe_dump(rules), encoding="utf-8")
    assert rebuild(project)["kb_version"] != first["kb_version"]


def test_rebuild_while_current_reader_is_open(project):
    reader = KnowledgeBase(project / "data/kb.sqlite")
    old = reader.lookup("tarot", "card", "the_fool:upright")
    try:
        edit_source(
            project,
            lambda entries: entries[0].update(
                text="新版草稿内容用于检查在读版本不会被替换。", version=2
            ),
        )
        newer = rebuild(project)
        assert newer["kb_version"] != reader.version
        assert reader.lookup("tarot", "card", "the_fool:upright") == old
    finally:
        reader.close()


def test_coverage_report_on_disk(project):
    report = json.loads((project / "data/kb.coverage.json").read_text(encoding="utf-8"))
    assert report["missing"] == []


def test_line_endings_do_not_change_version(project):
    initial = rebuild(project)["kb_version"]
    paths = [project / "sources/tarot/cards.yaml", project / "rules/tarot.yaml"]
    for path in paths:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    assert rebuild(project)["kb_version"] == initial
    for path in paths:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert rebuild(project)["kb_version"] == initial
