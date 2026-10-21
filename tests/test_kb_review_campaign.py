"""System acceptance keeps failures, incomplete work, and content identity visible."""

import copy
import random

import pytest

from knowledge.review import content_hash, load_ledgers
from scripts import kb_review_campaign as campaign
from scripts import model_review_kb as review
from tests.knowledge_fixture import copy_draft_knowledge
from tests.test_model_review_kb import ROLES, Reviewer, complete_run, real_entries
from tests.test_pr15_review_fixes import TARGET, tower_run


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
    monkeypatch.setattr("tests.test_model_review_kb.DOUBTFUL", set())
    reviewers = {role: Reviewer(real_entries(work), role) for role in review.REVIEWERS}
    _, run, _, _, _ = await complete_run(
        work, config, tmp_path / "unanimous", reviewers, plant_rate=0
    )
    summary, _, _ = campaign.summarize(work, [run.path], "tarot")
    assert summary["metrics"]["kappa"] is None
    assert not summary["gates"]["kappa"]
    assert not summary["calibrated"]


def test_foreign_text_contains_donor_identity(workspace):
    work, _ = workspace
    entries = review.load_entries(work.sources, "tarot")
    by_id = {e["id"]: e for e in entries}
    target = entries[0]
    mutated = review.mutations(target, by_id, random.Random(1))["foreign_text"]
    donors = [e for e in entries if e["text"] in mutated["text"]]
    assert any(
        e["id"] != target["id"] and f"（{e['key']}）的释义：" in mutated["text"] for e in donors
    )
    assert mutated["key"] == target["key"]


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
