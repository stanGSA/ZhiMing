import json

from evals.baseline import OUTPUT, build_baseline, load, render
from scripts.failure_taxonomy import summarize


def test_groups_add_up_to_each_archived_run():
    baseline = build_baseline()
    for name, groups in baseline["runs"].items():
        whole = summarize(load(name))
        for key, total in (
            ("task_success", "task_success"),
            ("submitted", "submitted"),
            ("no_tool_errors", "first_try_clean"),
            ("quality", "quality"),
        ):
            assert sum(entry[key] for entry in groups.values()) == whole[total], (name, key)
        assert sum(entry["cases"] for entry in groups.values()) == whole["cases"]
    # A clean success needs the task done as well: the review's recount of the archive.
    clean = {
        name: sum(e["clean_success"] for e in g.values()) for name, g in baseline["runs"].items()
    }
    assert clean == {
        "Final-single": 12,
        "Final-multi": 9,
        "Compare-single": 1,
        "Compare-multi": 0,
        "Compare-multi-lite": 0,
    }
    # The multi-system comparison set holds only multi-system questions.
    assert set(baseline["runs"]["Compare-single"]) == {"multi"}
    tarot = baseline["heldout"]["Final-heldout"]["tarot"]
    assert tarot["cases"] == 8 and tarot["submitted"] == 8


def test_committed_baseline_matches_the_archive():
    baseline = build_baseline()
    assert json.loads(OUTPUT.with_suffix(".json").read_text(encoding="utf-8")) == baseline
    assert OUTPUT.with_suffix(".md").read_text(encoding="utf-8") == render(baseline)
