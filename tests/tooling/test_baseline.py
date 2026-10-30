import json

from evals.baseline import OUTPUT, build_baseline, load, render
from scripts.failure_taxonomy import summarize


def test_groups_add_up_to_each_archived_run():
    baseline = build_baseline()
    for name, groups in baseline["runs"].items():
        whole = summarize(load(name))
        for key in ("task_success", "submitted", "first_try_clean", "quality"):
            assert sum(entry[key] for entry in groups.values()) == whole[key], (name, key)
        assert sum(entry["cases"] for entry in groups.values()) == whole["cases"]
    # The multi-system comparison set holds only multi-system questions.
    assert set(baseline["runs"]["Compare-single"]) == {"multi"}
    tarot = baseline["heldout"]["Final-heldout"]["tarot"]
    assert tarot["cases"] == 8 and tarot["submitted"] == 8


def test_committed_baseline_matches_the_archive():
    baseline = build_baseline()
    assert json.loads(OUTPUT.with_suffix(".json").read_text(encoding="utf-8")) == baseline
    assert OUTPUT.with_suffix(".md").read_text(encoding="utf-8") == render(baseline)
