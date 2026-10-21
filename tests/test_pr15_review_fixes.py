"""PR #15: sparse re-reviews, approval revocation, and historical reviewer identity."""

import copy
import json
import shutil

import pytest
import yaml

from harness.models import ModelResponse
from knowledge.build import build
from knowledge.kb import KnowledgeBase
from knowledge.review import approval, load_ledgers, write_ledger
from scripts import model_review_kb as review
from tests.test_model_review_kb import (
    IDS,
    ROLES,
    Reviewer,
    complete_run,
    real_entries,
)

TARGET = "kb:tarot:card:the_tower:upright"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    shutil.copytree(review.ROOT / "knowledge", tmp_path / "knowledge")
    config = review.load_config(review.ROOT)
    config["kb_review"] = dict(timeout_s=10, roles=copy.deepcopy(ROLES))
    for spec in ROLES.values():
        monkeypatch.setenv(spec["api_key_env"], "offline-placeholder")
    return review.Workspace(tmp_path), config


@pytest.mark.parametrize("include_convention", [False, True])
def test_single_dream_symbol_re_review(workspace, include_convention):
    workspace, config = workspace
    entries = review.load_entries(workspace.sources, "dream")
    ids = [next(e["id"] for e in entries if e["kind"] == "symbol")]
    if include_convention:
        ids.append(next(e["id"] for e in entries if e["kind"] == "convention"))
    plan = review.prepare(workspace, config, "dream", only_ids=ids)
    assert len(plan["planted"]) == len(ids)
    originals = {p["ref"]: p["original"] for p in plan["planted"]}
    for batch in plan["batches"]:
        refs = {i["ref"] for i in batch["items"]}
        assert not any(originals[r] in refs for r in refs if r in originals)


class TowerReviewer(Reviewer):
    def __init__(self, entries, verdict):
        super().__init__(entries, "offline")
        self.tower_verdict = verdict

    def verdicts(self, payload, planted_keys):
        result = super().verdicts(payload, planted_keys)
        for item, verdict in zip(payload["items"], result["items"], strict=True):
            real = self.entries[item["key"]]
            if item["key"] == "the_tower:upright" and all(
                item[f] == real[f] for f in ("text", "theme_map", "synonyms")
            ):
                verdict.update(
                    verdict=self.tower_verdict,
                    issues=[] if self.tower_verdict == "pass" else [dict(detail="需要修改")],
                )
        return result


async def tower_run(workspace, config, path, verdict, **options):
    entries = real_entries(workspace)
    reviewers = {role: TowerReviewer(entries, verdict) for role in review.REVIEWERS}
    plan, run, roles, _, _ = await complete_run(workspace, config, path, reviewers, **options)
    review.merge(run, plan, roles)
    return plan, run, roles


@pytest.mark.parametrize("verdict", ["revise", "reject"])
@pytest.mark.parametrize("only_rejected", [False, True])
async def test_later_rejection_revokes_approval(workspace, tmp_path, verdict, only_rejected):
    workspace, config = workspace
    _, old, _ = await tower_run(workspace, config, tmp_path / "old", "pass")
    review.record_ledger(workspace, [old.path], root=tmp_path)
    assert TARGET in load_ledgers(workspace.reviews)
    options = dict(only_ids=[TARGET], calibrated_by="old", plant_rate=0.1) if only_rejected else {}
    _, new, _ = await tower_run(workspace, config, tmp_path / "new", verdict, **options)
    if only_rejected:
        assert review.read_json(new.path / "merged.json")["approved_ids"] == []
    review.record_ledger(workspace, [new.path], root=tmp_path)
    records = load_ledgers(workspace.reviews)
    assert TARGET not in records
    assert IDS[0] in records  # approvals outside the rejection survive
    build(workspace.sources, tmp_path / "data/kb.sqlite", workspace.rules, workspace.reviews)
    kb = KnowledgeBase(tmp_path / "data/kb.sqlite")
    try:
        assert kb.lookup("tarot", "card", "the_tower:upright")["review_status"] == "draft"
        assert kb.lookup("tarot", "card", "the_fool:upright")["review_status"] == "model_reviewed"
    finally:
        kb.close()


async def test_rejection_preserves_approval_of_other_content(workspace, tmp_path):
    workspace, config = workspace
    _, run, _ = await tower_run(workspace, config, tmp_path / "run", "reject")
    entry = copy.deepcopy(real_entries(workspace)["the_tower:upright"])
    entry["text"] += "新版本补充说明。"
    entry["version"] += 1
    reviewers = [
        dict(vendor=s["vendor"], model=s["model"], verdict="pass") for s in ROLES.values()
    ][:2]
    record = approval(entry, reviewers, "2026-10-21", "new-content/report.md")
    write_ledger(workspace.reviews, "tarot", [record])
    review.record_ledger(workspace, [run.path], root=tmp_path)
    assert load_ledgers(workspace.reviews)[TARGET].model_dump() == record


@pytest.mark.parametrize("vendor", ["vendor-a", " Vendor-B ", "vendor-c"])
def test_reviser_uses_historical_reviewers(workspace, tmp_path, monkeypatch, vendor):
    workspace, config = workspace
    plan = review.prepare(workspace, config, "tarot", only_ids=[TARGET])
    run = review.open_run(tmp_path / "run", plan)
    review.write_json(
        run.path / "revision_queue.json", [dict(id=TARGET, verdicts={}, code_findings=[])]
    )
    changed = copy.deepcopy(config)
    # The current review roles may be removed; only the archived run's reviewers matter.
    changed["kb_review"]["roles"].update(reviewer_a=None, reviewer_b=None)
    changed["kb_review"]["roles"]["reviser"]["vendor"] = vendor
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(changed), encoding="utf-8")
    monkeypatch.setattr(review, "ROOT", tmp_path)
    requested = []

    class OfflineReviser:
        async def chat(self, messages, tools):
            return ModelResponse(
                model="offline-model",
                text=json.dumps(
                    dict(
                        text="高塔正位提示结构需要调整，先检查最脆弱的环节。",
                        theme_map={"self": -0.4},
                        synonyms=[],
                        keywords=["变动"],
                        note="调整",
                    )
                ),
            )

    def make_model(spec, timeout):
        requested.append(spec.vendor)
        return OfflineReviser()

    monkeypatch.setattr(review, "role_model", make_model)
    if vendor.strip().lower() in ("vendor-a", "vendor-b"):
        with pytest.raises(ValueError, match="本批审核模型同一厂商"):
            review.main(["revise", "--run-dir", str(run.path)])
        assert not requested
        assert not (run.path / "revisions.json").exists()
    else:
        proposals = review.main(["revise", "--run-dir", str(run.path)])
        assert requested == [vendor] and proposals[0]["invalid"] is None
