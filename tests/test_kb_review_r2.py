"""Stage 1 second campaign: rubric anchors, the labelled calibration set, preregistration and
the end-to-end runner, all offline."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from lunar_python.util import LunarUtil

from harness.models import ModelResponse
from knowledge.review import content_hash, load_ledgers
from plugins.name.wuge import element
from scripts import kb_review_calibration as calibration_set
from scripts import kb_review_campaign as campaign
from scripts import kb_review_live as live
from scripts import model_review_kb as review
from scripts.kb_review_rubric import ANCHORS, RUBRIC, SYSTEM_RUBRIC, revise_prompt
from tests.knowledge_fixture import copy_draft_knowledge
from tests.test_model_review_kb import ROLES

DRAFT = review.ROOT / "docs/verification/kb-model-review/stage1-r2/calibration.yaml"
SYSTEM = "daily"
DOUBTFUL = "kb:daily:convention:moment_only"


# ---- rubric ------------------------------------------------------------------------------


def test_rubric_ten_gods_match_the_library_the_charts_use():
    stems = "甲乙丙丁戊己庚辛壬癸"
    generates = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    controls = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    names = dict(
        same=("比肩", "劫财"),
        produce=("食神", "伤官"),
        control=("偏财", "正财"),
        controlled=("七杀", "正官"),
        produced=("偏印", "正印"),
    )
    for me in stems:
        for other in stems:
            mine, theirs = LunarUtil.WU_XING_GAN[me], LunarUtil.WU_XING_GAN[other]
            relation = (
                "same"
                if mine == theirs
                else "produce"
                if generates[mine] == theirs
                else "control"
                if controls[mine] == theirs
                else "controlled"
                if controls[theirs] == mine
                else "produced"
            )
            alike = stems.index(me) % 2 == stems.index(other) % 2
            assert LunarUtil.SHI_SHEN[me + other] == names[relation][0 if alike else 1]
    text = SYSTEM_RUBRIC["bazi"]
    for phrase in ("同我者，阴阳相同为比肩", "我克者，同为偏财、异为正财", "生我者，同为偏印"):
        assert phrase in text


def test_rubric_quotes_the_project_tables():
    bazi, name = SYSTEM_RUBRIC["bazi"], SYSTEM_RUBRIC["name"]
    for branch, stems in LunarUtil.ZHI_HIDE_GAN.items():
        assert f"{branch}藏{'、'.join(stems)}" in bazi
    digits = {n % 10: element(n) for n in range(1, 11)}
    for low in (1, 3, 5, 7, 9):
        assert f"{low}、{(low + 1) % 10}{digits[low]}" in name
    assert digits[low] == digits[(low + 1) % 10]
    assert "申子辰（水）" in bazi and "第10宫职业与公共责任" in SYSTEM_RUBRIC["astro"]
    assert "圣杯作用于感情关系、自我状态" in SYSTEM_RUBRIC["tarot"]


def test_rubric_v2_is_a_new_identity_and_reaches_the_reviser():
    archived = review.read_json(
        review.ROOT / "docs/verification/kb-model-review/20261021-live/astro-initial/manifest.json"
    )
    assert archived["rubric_sha256"] != review.rubric_digest()
    assert "{system_rubric}" in RUBRIC
    rendered = RUBRIC.format(system_rubric=SYSTEM_RUBRIC["name"])
    assert "判定锚点" in rendered and "尾数定五行" in rendered
    assert ANCHORS in revise_prompt("name") and SYSTEM_RUBRIC["name"] in revise_prompt("name")


# ---- calibration set ---------------------------------------------------------------------


def test_drafted_calibration_set_is_balanced_and_labelled():
    data = calibration_set.load(DRAFT)
    assert calibration_set.counts(data) == {
        **{s: {"fail": 15, "pass": 15} for s in ("astro", "bazi", "dream", "name", "tarot")},
        "daily": {"fail": 9, "pass": 9},
    }
    for item in data["items"]:
        if item["label"] == "fail":
            assert item["change"]["before"] != item["change"]["after"], item["id"]
            assert item["defect"]["detail"]
    # A fail is a single edit of a real entry; daily alone reuses its nine entries as passes.
    bases = {}
    for item in data["items"]:
        bases.setdefault((item["system"], item["base"]), []).append(item["label"])
    assert all(len(labels) == 1 or system == "daily" for (system, _), labels in bases.items())


def test_freeze_binds_the_exact_items(tmp_path):
    path = tmp_path / "calibration.yaml"
    path.write_bytes(DRAFT.read_bytes())
    with pytest.raises(ValueError, match="尚未经负责人确认"):
        calibration_set.frozen(path)
    record = calibration_set.freeze(path, "负责人", at="2026-10-22T00:00:00+00:00")
    assert calibration_set.frozen(path)[1] == record
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["items"][0]["label"] = "fail" if data["items"][0]["label"] == "pass" else "pass"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError):
        calibration_set.frozen(path)


# ---- an offline campaign -----------------------------------------------------------------


def small_calibration(work, path):
    """Four real daily entries (pass) and four one-edit copies (fail), frozen."""
    entries = review.load_entries(work.sources, SYSTEM)
    items = []
    for number, entry in enumerate(entries[:8]):
        variant = copy.deepcopy(entry)
        label = "pass" if number % 2 == 0 else "fail"
        if label == "fail":
            variant["theme_map"]["self"] = 0.2
        items.append(
            dict(
                id=f"cal-daily-{number:02d}",
                system=SYSTEM,
                label=label,
                base=entry["id"],
                rationale="测试",
                **(
                    dict(defect=dict(type="nonzero_direction", detail="测试"))
                    if label == "fail"
                    else {}
                ),
                entry=variant,
            )
        )
    path.write_text(
        yaml.safe_dump(dict(schema_version=1, items=items), allow_unicode=True), encoding="utf-8"
    )
    calibration_set.freeze(path, "负责人")
    return path


class Models:
    """Reviewers flag content that differs from the sources and the doubtful entry's
    original text; the reviser appends a sentence (or returns the entry unchanged)."""

    def __init__(self, work, noop=False):
        self.work, self.noop, self.calls = work, noop, []
        self.original = {e["id"]: e for e in review.load_entries(work.sources, SYSTEM)}

    def make(self, role, spec):
        models = self

        class Model:
            async def chat(self, messages, tools):
                models.calls.append(role)
                payload = json.loads(messages[-1]["content"])
                if role == "reviser":
                    entry = payload["entry"]
                    text = entry["text"] if models.noop else entry["text"] + "本条只作约定说明。"
                    keywords = entry["keywords"] or [entry["key"]]
                    if models.noop:
                        keywords = entry["keywords"]
                    proposal = dict(
                        text=text,
                        theme_map=entry["theme_map"],
                        synonyms=entry["synonyms"],
                        keywords=keywords,
                        note="测试",
                    )
                    return ModelResponse(model="reviser-test", text=json.dumps(proposal))
                current = {e["key"]: e for e in review.load_entries(models.work.sources, SYSTEM)}
                items = []
                for item in payload["items"]:
                    real = current[item["key"]]
                    changed = any(item[f] != real[f] for f in ("text", "theme_map", "synonyms"))
                    doubtful = item["text"] == models.original[DOUBTFUL]["text"] and (
                        item["key"] == models.original[DOUBTFUL]["key"]
                    )
                    verdict = "revise" if changed or doubtful else "pass"
                    items.append(
                        dict(
                            item=item["item"],
                            verdict=verdict,
                            issues=[] if verdict == "pass" else [dict(detail="测试")],
                            reason="测试",
                        )
                    )
                return ModelResponse(model=f"{role}-test", text=json.dumps(dict(items=items)))

        return Model()


@pytest.fixture
def setting(tmp_path, monkeypatch):
    copy_draft_knowledge(review.ROOT / "knowledge", tmp_path / "knowledge")
    work = review.Workspace(tmp_path)
    config = review.load_config(review.ROOT)
    config["kb_review"] = dict(
        roles=copy.deepcopy(ROLES), budget=dict(unlimited=True, state_path="budget.json")
    )
    for spec in ROLES.values():
        monkeypatch.setenv(spec["api_key_env"], "offline-placeholder")
    root = tmp_path / "stage1-r2"
    calibration = small_calibration(work, tmp_path / "calibration.yaml")
    roles = review.load_roles(config)
    prereg = live.preregister(root, calibration, config, roles, systems=(SYSTEM,))
    return work, config, roles, root, prereg


async def run(setting, models):
    work, config, roles, root, prereg = setting
    return await live.run_system(
        root, SYSTEM, prereg, workspace=work, config=config, roles=roles, make_model=models.make
    )


def test_calibration_items_are_blind_and_apart_from_their_originals(setting):
    work, config, roles, root, prereg = setting
    path = review.ROOT / prereg["calibration"]["path"]
    plan = review.prepare(
        work, config, SYSTEM, calibration=review.calibration_for(path, SYSTEM), seed=3
    )
    assert plan["manifest"]["calibration"] == dict(
        lock_sha256=prereg["calibration"]["lock_sha256"], items=8
    )
    text = json.dumps(plan["prompts"], ensure_ascii=False)
    assert not any(
        word in text for word in ("cal-daily", "rationale", "nonzero_direction", "label")
    )
    ref_batch = {i["ref"]: b["batch"] for b in plan["batches"] for i in b["items"]}
    for item in plan["calibration"]:
        assert ref_batch[item["ref"]] != ref_batch[item["original"]]
    copies = [ref_batch[i["ref"]] for i in plan["calibration"]] + [
        ref_batch[p["ref"]] for p in plan["planted"]
    ]
    originals = [i["original"] for i in plan["calibration"]] + [
        p["original"] for p in plan["planted"]
    ]
    seen = {}
    for batch, original in zip(copies, originals, strict=True):
        assert (batch, original) not in seen  # two copies of one entry never meet
        seen[(batch, original)] = True


async def test_campaign_runs_revises_rereviews_and_resumes(setting):
    work, config, roles, root, prereg = setting
    models = Models(work)
    result = await run(setting, models)
    assert result["status"] == "done"
    assert [Path(s["run"]).name for s in result["steps"]] == ["daily-initial", "daily-rereview-1"]
    assert result["steps"][0]["queued"] == 1 and result["steps"][0]["revised"] == 1
    rereview = review.load_plan(root / "daily-rereview-1")
    assert [e["id"] for e in rereview["entries"]] == [DOUBTFUL]
    assert not rereview["calibration"]  # labelled items only in the initial run
    made = len(models.calls)
    again = await run(setting, models)
    assert len(models.calls) == made  # nothing is asked twice
    assert [s["completed"] for s in again["steps"]] == [0, 0]
    assert [dict(s, completed=0) for s in again["steps"]] == [
        dict(s, completed=0) for s in result["steps"]
    ]
    paths = sorted(p.parent for p in root.glob("*/manifest.json"))
    summary, outcomes, entries = campaign.summarize(work, paths, SYSTEM, prereg)
    assert summary["preregistered"] and summary["gates"]["complete"]
    assert summary["metrics"]["kappa"] == 1.0
    assert summary["metrics"]["calibration"]["label_agreement"]["reviewer_a"]["accuracy"] == 1.0
    assert summary["calibrated"] and outcomes[DOUBTFUL]["approved"]
    campaign.record(work, summary, outcomes, entries, root / "campaign/daily/report.md", root)
    assert len(load_ledgers(work.reviews)) == 9


async def test_deviation_from_the_preregistration_blocks_acceptance(setting):
    work, config, roles, root, prereg = setting
    await run(setting, Models(work))
    paths = sorted(p.parent for p in root.glob("*/manifest.json"))
    changed = dict(prereg, rubric_sha256="0" * 64)
    summary, _, _ = campaign.summarize(work, paths, SYSTEM, changed)
    assert not summary["gates"]["complete"] and summary["deviations"]
    with pytest.raises(ValueError, match="与预先登记不符"):
        await live.run_system(
            root,
            SYSTEM,
            changed,
            workspace=work,
            config=config,
            roles=roles,
            make_model=Models(work).make,
        )


async def test_unchanged_proposals_are_never_rereviewed(setting):
    work, config, roles, root, prereg = setting
    result = await run(setting, Models(work, noop=True))
    assert [Path(s["run"]).name for s in result["steps"]] == ["daily-initial"]
    assert result["steps"][0]["revised"] == 0
    assert not (root / "daily-rereview-1").exists()


async def test_apply_survives_a_crash_before_it_was_recorded(setting):
    work, config, roles, root, prereg = setting
    await run(setting, Models(work))
    initial = root / "daily-initial"
    (initial / "applied.json").unlink()
    applied = live.apply_pending(work, review.RunDir(initial), review.load_plan(initial))
    assert applied == [DOUBTFUL]
    current = {e["id"]: e for e in review.load_entries(work.sources, SYSTEM)}
    assert (
        content_hash(current[DOUBTFUL])
        != review.load_plan(initial)["manifest"]["entry_hashes"][DOUBTFUL]
    )


def test_preregistration_is_written_once_and_before_any_review(setting, tmp_path):
    work, config, roles, root, prereg = setting
    assert prereg["kappa_basis"]["scope"].startswith("每个体系初审中混入")
    assert (root / review.CAMPAIGN_MARKER).is_file()
    with pytest.raises(ValueError, match="已登记"):
        live.preregister(root, review.ROOT / prereg["calibration"]["path"], config, roles)
    late = tmp_path / "late"
    review.write_json(late / "daily-initial/manifest.json", {})
    with pytest.raises(ValueError, match="不能事后登记"):
        live.preregister(late, review.ROOT / prereg["calibration"]["path"], config, roles)


def test_calibration_draft_is_deterministic():
    from scripts.draft_calibration import draft

    assert draft() == draft()
