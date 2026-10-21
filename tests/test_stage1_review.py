"""Stage 1 / B2: three review levels, the model-review ledger and the confidence cap."""

import json
import shutil
import sqlite3

import pytest
import yaml

from app import create_runtime
from common.output_policy import mark_unreviewed
from common.schemas import Confidence
from knowledge import checks
from knowledge.build import build
from knowledge.kb import KnowledgeBase
from knowledge.review import approval, content_hash, load_ledgers, review_status, write_ledger
from knowledge.schema import Entry
from plugins.base import Signal
from plugins.dream.match import DreamMatcher
from signals.merge import merge_signals
from tests.test_week5 import sig
from tests.test_week6 import daily, with_birth
from tests.test_week23_integration import invoke

REVIEWERS = [
    dict(vendor="vendor-a", model="model-a", returned_model="model-a-1", verdict="pass"),
    dict(vendor="vendor-b", model="model-b", returned_model="model-b-1", verdict="pass"),
]
REPORT = "docs/verification/kb-model-review/test/report.md"


def source_entries(project, system="tarot"):
    path = project / (
        "sources/tarot/cards.yaml" if system == "tarot" else f"sources/{system}/entries.yaml"
    )
    return path, yaml.safe_load(path.read_text(encoding="utf-8"))


def rebuild(project):
    return build(
        project / "sources", project / "data/kb.sqlite", project / "rules", project / "reviews"
    )


def approve(project, system="tarot", keep=None):
    _, source = source_entries(project, system)
    records = [
        approval(e, REVIEWERS, "2026-10-21", REPORT)
        for e in source["entries"]
        if keep is None or keep(e)
    ]
    write_ledger(project / "reviews", system, records)
    return records


def lookup(project, key, system="tarot", kind="card"):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        return kb.lookup(system, kind, key)
    finally:
        kb.close()


def test_ledger_approval_gives_model_reviewed_and_human_rate_stays_zero(project):
    before = rebuild(project)
    approve(project, keep=lambda e: e["key"] == "the_fool:upright")
    report = rebuild(project)
    assert report["kb_version"] != before["kb_version"]  # the ledger is part of the version
    assert report["reviewed_rate"] == 0 and report["reviewed_count"] == 0
    tarot = report["partitions"]["tarot"]["review_status"]["counts"]
    assert tarot == {"draft": 162, "model_reviewed": 1, "human_reviewed": 0}
    assert report["review_status"]["counts"]["model_reviewed"] == 1
    assert report["review_ledger"] == {"current": 1, "stale": 0, "orphan": 0}
    entry = lookup(project, "the_fool:upright")
    assert entry["review_status"] == "model_reviewed" and entry["reviewed"] is False
    assert {r["vendor"] for r in entry["model_review"]["reviewers"]} == {"vendor-a", "vendor-b"}
    assert lookup(project, "the_fool:reversed")["review_status"] == "draft"


def test_editing_an_entry_voids_its_approval(project):
    approve(project, keep=lambda e: e["key"] == "the_fool:upright")
    path, source = source_entries(project)
    source["entries"][0]["theme_map"]["self"] = -0.3  # numbers are content too
    path.write_text(yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = rebuild(project)
    assert lookup(project, "the_fool:upright")["review_status"] == "draft"
    assert report["review_ledger"] == {"current": 0, "stale": 1, "orphan": 0}


def test_regenerated_drafts_keep_approvals(tmp_path):
    """An unchanged authoring rerun keeps the content bytes bound to an approval."""
    from scripts.draft_sources import write_drafts
    from scripts.draft_week6 import daily_entries

    path = tmp_path / "daily.yaml"
    write_drafts(path, daily_entries())
    source = yaml.safe_load(path.read_text(encoding="utf-8"))
    current = {e["id"]: content_hash(e) for e in source["entries"]}
    records = [approval(e, REVIEWERS, "2026-10-21", REPORT) for e in source["entries"]]
    before = path.read_bytes()
    write_drafts(path, daily_entries())
    assert path.read_bytes() == before
    assert {r["id"]: r["content_sha256"] for r in records} == current


@pytest.mark.parametrize("field", ["review_status", "model_review"])
def test_sources_cannot_author_review_state(project, field):
    path, source = source_entries(project)
    source["entries"][0][field] = "model_reviewed" if field == "review_status" else {}
    path.write_text(yaml.safe_dump(source, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="审核账本"):
        rebuild(project)


def test_reviewed_means_human_review_only():
    base = dict(
        id="kb:tarot:card:x:upright",
        system="tarot",
        kind="card",
        key="x:upright",
        keywords=["x"],
        theme_map={},
        text="一段足够长的测试释义文字。",
        source="test",
        license="本项目自写",
        version=1,
    )
    with pytest.raises(ValueError):
        Entry.model_validate(dict(base, reviewed=True, review_status="model_reviewed"))
    with pytest.raises(ValueError):
        Entry.model_validate(dict(base, reviewed=False, review_status="human_reviewed"))
    with pytest.raises(ValueError):  # model_reviewed needs its review record
        Entry.model_validate(dict(base, reviewed=False, review_status="model_reviewed"))
    assert Entry.model_validate(dict(base, reviewed=True, review_status="human_reviewed"))


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r["reviewers"][1].update(vendor="Vendor-A"),
        lambda r: r["reviewers"][1].update(verdict="revise"),
        lambda r: r["reviewers"].pop(),
        lambda r: r.update(content_sha256="x"),
    ],
)
def test_ledger_needs_two_vendors_that_both_pass(project, change):
    (record,) = approve(project, keep=lambda e: e["key"] == "the_fool:upright")
    change(record)
    (project / "reviews/tarot.yaml").write_text(
        yaml.safe_dump(dict(schema_version=1, system="tarot", records=[record])), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_ledgers(project / "reviews")


def test_old_edition_without_review_fields_reads_as_draft(project):
    """Editions built before stage 1 store ``reviewed`` only; readers derive the level."""
    report = rebuild(project)
    current = project / f"data/kb_versions/{report['kb_version']}.sqlite"
    old_version = "v1-0123456789abcdef"
    old = current.with_name(f"{old_version}.sqlite")
    shutil.copyfile(current, old)
    with sqlite3.connect(old) as db:
        rows = db.execute("SELECT id, entry_json FROM entries").fetchall()
        for entry_id, raw in rows:
            entry = json.loads(raw)
            entry.pop("review_status"), entry.pop("model_review")
            db.execute("UPDATE entries SET entry_json=? WHERE id=?", (json.dumps(entry), entry_id))
        db.execute("UPDATE meta SET value=? WHERE key='kb_version'", (old_version,))
    db.close()
    kb = KnowledgeBase(project / "data/kb.sqlite", old_version)
    try:
        assert kb.lookup("tarot", "card", "the_fool:upright")["review_status"] == "draft"
        matcher = DreamMatcher(kb.db, kb.version)
        assert {e["review_status"] for e in matcher.entries.values()} == {"draft"}
    finally:
        kb.close()


def test_signal_reads_legacy_reviewed_values():
    legacy = sig("astro", "career", 0.2, 0.5)
    assert Signal.model_validate(legacy).review_status == "draft"
    assert Signal.model_validate(dict(legacy, reviewed=True)).review_status == "human_reviewed"
    dumped = Signal.model_validate(legacy).model_dump(mode="json")
    assert "reviewed" not in dumped and dumped["review_status"] == "draft"
    with pytest.raises(ValueError):
        Signal.model_validate({**dumped, "review_status": "reviewed"})


@pytest.mark.parametrize(
    "levels, expected",
    [
        (["human_reviewed", "model_reviewed"], "model_reviewed"),
        (["model_reviewed", "draft"], "draft"),
        (["human_reviewed", "human_reviewed"], "human_reviewed"),
    ],
)
def test_merge_side_takes_the_lowest_level(levels, expected):
    signals = [
        dict(sig("astro", "career", 0.3, 0.6, ref=f"a{i}"), review_status=level)
        for i, level in enumerate(levels)
    ]
    signals.append(dict(sig("bazi", "career", -0.3, 0.6, ref="b"), review_status="human_reviewed"))
    (tension,) = merge_signals(signals)["tensions"]
    sides = {s["system"]: s for s in tension["windows"][0]["sides"]}
    assert sides["astro"]["review_status"] == expected
    assert sides["bazi"]["review_status"] == "human_reviewed"


@pytest.mark.parametrize(
    "level, reason, signals, expected_level, expected_reason",
    [
        ("high", "", [{"reviewed": False}], "low", "释义未经审核。"),
        # A draft statement already there is kept verbatim (the prompt asks for it).
        ("high", "释义为未经人工审核的草稿。\n保留来源说明。", [{"reviewed": False}], "low",
         "释义为未经人工审核的草稿。\n保留来源说明。"),
        # A false human-review claim is removed, other clauses kept.
        ("medium", "牌面清楚，释义已经人工审核，可以参考。", [{"review_status": "draft"}], "low",
         "牌面清楚，可以参考；释义未经审核。"),
        ("high", "牌面清楚", [{"review_status": "model_reviewed"}], "medium",
         "牌面清楚；释义经模型交叉审核，未经人工审核。"),
        # "Not human-reviewed" alone hides the model review: replaced by the full fact.
        ("high", "释义未人工审核", [{"review_status": "model_reviewed"}], "medium",
         "释义经模型交叉审核，未经人工审核。"),
        ("low", "释义经模型交叉审核，未经人工审核。", [{"review_status": "model_reviewed"}], "low",
         "释义经模型交叉审核，未经人工审核。"),
        ("high", "牌面清楚", [{"review_status": "model_reviewed"}, {"reviewed": True}], "medium",
         "牌面清楚；释义经模型交叉审核，未经人工审核。"),
        ("high", "牌面清楚", [{"review_status": "human_reviewed"}], "high", "牌面清楚"),
        ("high", "牌面清楚", [], "high", "牌面清楚"),
    ],
)  # fmt: skip
def test_confidence_cap_by_lowest_review_level(
    level, reason, signals, expected_level, expected_reason
):
    confidence = Confidence(level=level, reason=reason)
    mark_unreviewed(confidence, signals)
    assert (confidence.level, confidence.reason) == (expected_level, expected_reason)


async def test_model_reviewed_tarot_reading_states_model_review(project):
    approve(project)
    rebuild(project)
    runtime = create_runtime(root=project, user_id="stage1-model", seed=42)
    try:
        out = await runtime.turn("近期状态")
        assert out.status == "submit_reading"
        signals = runtime.session.state["signals"]
        assert signals and {s["review_status"] for s in signals} == {"model_reviewed"}
        reason = out.data["reading"]["confidence"]["reason"]
        assert reason.endswith("释义经模型交叉审核，未经人工审核。")
        assert "未人工审核的自写草稿" not in reason
        card = runtime.session.state["tarot_result"]["cards"][0]
        assert card["meaning"]["review_status"] == "model_reviewed"
        assert card["meaning"]["reviewed"] is False
        found = await invoke(
            runtime, "lookup_meaning", dict(system="tarot", kind="card", key=card["meaning_key"])
        )
        assert found.data["entry"]["review_status"] == "model_reviewed"
        assert "model_review" not in found.data["entry"]  # reviewers are not shown to the model
    finally:
        runtime.close()


async def test_saved_reading_with_legacy_signals_still_follows_up(runtime):
    out = await runtime.turn("近期状态")
    reading_id = out.data["reading_id"]
    db = runtime.store.db
    raw = db.execute("SELECT signals_json FROM readings WHERE reading_id=?", (reading_id,))
    legacy = []
    for signal in json.loads(raw.fetchone()[0]):
        signal.pop("review_status")
        legacy.append(dict(signal, reviewed=False))
    with db:
        db.execute(
            "UPDATE readings SET signals_json=? WHERE reading_id=?",
            (json.dumps(legacy, ensure_ascii=False), reading_id),
        )
    runtime.session.append_user("第二张牌什么意思？")
    restored = await invoke(runtime, "read_reading", dict(reading_id=reading_id))
    assert restored.ok
    assert {review_status(s) for s in runtime.session.state["signals"]} == {"draft"}
    followup = dict(out.data["reading"], confidence=dict(level="high", reason="牌面清楚"))
    submitted = await invoke(runtime, "submit_reading", followup)
    assert submitted.ok, submitted.error
    assert submitted.data["response_id"]  # saved as a follow-up of the legacy reading
    confidence = submitted.data["reading"]["confidence"]
    assert confidence == dict(level="low", reason="牌面清楚；释义未经审核。")


async def test_daily_cache_from_before_stage1_is_reused(project):
    runtime = create_runtime(root=project, user_id="daily-legacy", seed=1)
    try:
        with_birth(runtime)
        first = await daily(runtime)
        day = first.data["date"]
    finally:
        runtime.close()
    db = sqlite3.connect(project / "data/app.db")
    (raw,) = db.execute("SELECT result_json FROM daily WHERE user_id='daily-legacy'").fetchone()
    result = json.loads(raw)
    for signal in result["signals"]:
        signal["reviewed"] = signal.pop("review_status") == "human_reviewed"
    for item in result["interpretations"]:
        item["meaning"].pop("review_status")
    with db:
        db.execute("UPDATE daily SET result_json=?", (json.dumps(result, ensure_ascii=False),))
    db.close()
    runtime = create_runtime(root=project, user_id="daily-legacy", seed=2)
    try:
        again = await daily(runtime)
        assert again.ok and again.data["cache_reused"] is True and again.data["date"] == day
        shown = runtime.registry.tools["daily_fortune"].model_result(again.data)
        assert {i["meaning"]["review_status"] for i in shown["interpretations"]} == {"draft"}
        assert {s["review_status"] for s in runtime.session.state["signals"]} == {"draft"}
    finally:
        runtime.close()


def test_code_checks_skip_negated_disclaimers_and_flag_claims():
    def entry(key, text, theme_map=None, system="dream", kind="symbol"):
        return dict(
            id=f"kb:{system}:{kind}:{key}", system=system, kind=kind, key=key, text=text,
            theme_map=theme_map or {},
        )  # fmt: skip

    found = checks.findings(
        [
            entry("a", "这是象征性反思线索，不代表事件必然发生。"),
            entry("b", "这是象征性反思主题，不表示现实事件必然发生。"),
            entry("c", "梦见此物，今年必然破财。"),
            entry("d", "不代表事件必然发生，但你注定成功。"),
            entry("x:upright", "正位。", {"self": -0.2, "career": 0.1}, "tarot", "card"),
            entry("x:reversed", "逆位。", {"self": -0.4, "career": -0.1}, "tarot", "card"),
        ]
    )
    assert [(f["id"].split(":")[-1], f["check"]) for f in found] == [
        ("c", "certainty"),
        ("d", "certainty"),
        ("upright", "tarot_same_direction"),
    ]
    assert "注定" in found[1]["detail"] and "self" in found[2]["detail"]


def test_build_reports_checks_without_failing(project):
    report = rebuild(project)
    assert report["checks"] == {"count": 17, "by_check": {"tarot_same_direction": 17}}
    saved = json.loads((project / "data/kb.checks.json").read_text(encoding="utf-8"))
    assert saved["kb_version"] == report["kb_version"] and len(saved["findings"]) == 17
