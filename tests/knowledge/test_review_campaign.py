"""System acceptance keeps failures, incomplete work, and content identity visible."""

import copy
import json
import random
from pathlib import Path

import pytest

from knowledge.review import content_hash, load_ledgers
from scripts import kb_review_campaign as campaign
from scripts import model_review_kb as review
from tests.knowledge.test_model_review import ROLES, Reviewer, complete_run, real_entries
from tests.knowledge.test_review_revocation import TARGET, tower_run
from tests.knowledge_fixture import copy_draft_knowledge


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    copy_draft_knowledge(review.ROOT / "knowledge", tmp_path / "knowledge")
    config = review.load_config(review.ROOT)
    config["kb_review"] = dict(roles=copy.deepcopy(ROLES))
    for spec in ROLES.values():
        monkeypatch.setenv(spec["api_key_env"], "offline-placeholder")
    return review.Workspace(tmp_path), config


async def test_all_batch_failures_remain_in_campaign(workspace, tmp_path):
    work, config = workspace
    _, first, _ = await tower_run(work, config, tmp_path / "initial", "revise")
    _, second, _ = await tower_run(work, config, tmp_path / "rereview", "pass")
    summary, outcomes, entries = campaign.summarize(work, [first.path, second.path], "tarot")
    assert summary["samples"]["kappa_real_pairs"] == 40  # both versions, not just latest
    assert summary["samples"]["kappa_pairs"] == 50  # all blind control samples too
    assert summary["samples"]["verdict_pairs_real"]["revise/revise"] == 3
    assert len(summary["batches"]) == 2
    assert (
        summary["batches"][0]["metrics"]["pass_rate"]
        < summary["batches"][1]["metrics"]["pass_rate"]
    )
    assert outcomes[TARGET]["approved"]
    assert summary["calibrated"]
    campaign.record(work, summary, outcomes, entries, tmp_path / "report.md", tmp_path)
    assert load_ledgers(work.reviews)[TARGET].content_sha256 == content_hash(entries[TARGET])


async def test_incomplete_rejection_revokes_same_hash_approval(workspace, tmp_path):
    work, config = workspace
    _, first, _ = await tower_run(work, config, tmp_path / "first", "pass")
    summary, outcomes, entries = campaign.summarize(work, [first.path], "tarot")
    campaign.record(work, summary, outcomes, entries, tmp_path / "report.md", tmp_path)
    assert TARGET in load_ledgers(work.reviews)
    _, later, _ = await tower_run(work, config, tmp_path / "later", "reject", passes=1)
    summary, outcomes, entries = campaign.summarize(work, [first.path, later.path], "tarot")
    assert not summary["gates"]["complete"]
    assert not summary["calibrated"]
    assert not outcomes[TARGET]["approved"]
    campaign.record(work, summary, outcomes, entries, tmp_path / "report.md", tmp_path)
    assert TARGET not in load_ledgers(work.reviews)


async def test_uncalibrated_system_revokes_approvals_written_batch_by_batch(workspace, tmp_path):
    """A calibrated batch written with `model_review_kb ledger` (as bazi-rereview-1 could be)
    must not outlive a failed system gate."""
    work, config = workspace
    _, first, _ = await tower_run(work, config, tmp_path / "root/first", "pass")
    review.record_ledger(work, [first.path], root=tmp_path)
    approved = set(load_ledgers(work.reviews))
    assert approved
    _, later, _ = await tower_run(work, config, tmp_path / "root/later", "pass", passes=1)
    summary, outcomes, entries = campaign.summarize(work, [first.path, later.path], "tarot")
    assert not summary["calibrated"]
    assert all(outcomes[ref]["approved"] for ref in approved)
    report = tmp_path / "campaign/tarot/report.md"
    changes = campaign.record(work, summary, outcomes, entries, report, tmp_path)
    assert not load_ledgers(work.reviews)
    assert changes["revoked"] == sorted(approved)
    events = (report.parent / "ledger-events.jsonl").read_text(encoding="utf-8").splitlines()
    assert {json.loads(line)["reason"] for line in events} == {"体系校准未达标"}


async def test_campaign_run_root_refuses_per_batch_ledger(workspace, tmp_path):
    work, config = workspace
    _, run, _ = await tower_run(work, config, tmp_path / "root/first", "pass")
    campaign.bind(tmp_path / "root", tmp_path / "root/campaign")
    with pytest.raises(ValueError, match="按体系汇总验收"):
        review.record_ledger(work, [run.path], root=tmp_path)
    assert not load_ledgers(work.reviews)


def test_report_reference_is_posix_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A relative --output was once written with Windows separators into every record.
    assert review.report_reference(Path("campaign") / "report.md", tmp_path) == (
        "campaign/report.md"
    )
    assert review.report_reference(tmp_path / "a" / "report.md", tmp_path) == "a/report.md"


def test_committed_ledgers_cite_posix_reports():
    records = load_ledgers(review.ROOT / "knowledge/reviews").values()
    assert records and all("\\" not in r.report for r in records)
    assert all((review.ROOT / r.report).is_file() for r in records)


async def test_changed_content_cannot_reuse_approval(workspace, tmp_path, monkeypatch):
    work, config = workspace
    _, run, _ = await tower_run(work, config, tmp_path / "first", "pass")
    entries = review.load_entries(work.sources, "tarot")
    next(e for e in entries if e["id"] == TARGET)["text"] += "修改后的新内容。"
    monkeypatch.setattr(review, "load_entries", lambda *_: entries)
    summary, outcomes, _ = campaign.summarize(work, [run.path], "tarot")
    assert TARGET not in outcomes
    assert summary["candidate_count"] == 18


async def test_missing_call_or_item_cannot_calibrate(workspace, tmp_path):
    work, config = workspace
    _, run, _ = await tower_run(work, config, tmp_path / "first", "pass")
    file = next((run.path / "calls").glob("*.json"))
    saved = file.read_bytes()
    call = review.read_json(file)
    del call["verdicts"][next(iter(call["verdicts"]))]
    review.write_json(file, call)
    assert not campaign.summarize(work, [run.path], "tarot")[0]["gates"]["complete"]
    file.write_bytes(saved)
    file.unlink()
    assert not campaign.summarize(work, [run.path], "tarot")[0]["gates"]["complete"]


async def test_unanimous_single_category_kappa_is_not_accepted(workspace, tmp_path, monkeypatch):
    work, config = workspace
    monkeypatch.setattr("tests.knowledge.test_model_review.DOUBTFUL", set())
    reviewers = {role: Reviewer(real_entries(work), role) for role in review.REVIEWERS}
    _, run, _, _, _ = await complete_run(
        work, config, tmp_path / "unanimous", reviewers, plant_rate=0
    )
    summary, _, _ = campaign.summarize(work, [run.path], "tarot")
    assert summary["metrics"]["kappa"] is None
    assert not summary["gates"]["kappa"]
    assert not summary["calibrated"]


@pytest.mark.parametrize("system", ["tarot", "astro", "dream", "name"])
def test_foreign_text_is_a_self_named_donor_without_a_wrapper(workspace, system):
    work, _ = workspace
    entries = review.load_entries(work.sources, system)
    by_id = {e["id"]: e for e in entries}
    for seed, target in enumerate(entries[::25]):
        mutated = review.mutations(target, by_id, random.Random(seed))["foreign_text"]
        # Exactly a real entry's text: no wrapper the real entries never carry.
        donor = next(e for e in entries if e["text"] == mutated["text"])
        assert donor["id"] != target["id"] and mutated["key"] == target["key"]
        peers = [e for e in entries if e["kind"] == target["kind"] and e["text"] != target["text"]]
        if any(review.names_itself(e) for e in peers):
            assert review.names_itself(donor)


async def test_binary_kappa_retains_control_verdict_disagreements(workspace, tmp_path):
    work, config = workspace
    reviewers = {role: Reviewer(real_entries(work), role) for role in review.REVIEWERS}
    plan, run, _, _, _ = await complete_run(work, config, tmp_path / "controls", reviewers)
    controls = {p["ref"] for p in plan["planted"]}
    refs = {(b["batch"], i["item"]): i["ref"] for b in plan["batches"] for i in b["items"]}
    for file in (run.path / "calls").glob("*.reviewer_b.*.json"):
        call = review.read_json(file)
        for item, verdict in call["verdicts"].items():
            if refs[(call["batch"], item)] in controls:
                verdict["verdict"] = "reject" if verdict["verdict"] == "revise" else "revise"
        review.write_json(file, call)
    summary, _, _ = campaign.summarize(work, [run.path], "tarot")
    assert summary["samples"]["kappa_pairs"] == 25
    assert summary["metrics"]["kappa"] == 1
    assert summary["metrics"]["kappa_all_three_class"] < 1
    assert summary["samples"]["verdict_pairs"].get("revise/reject", 0) > 0
