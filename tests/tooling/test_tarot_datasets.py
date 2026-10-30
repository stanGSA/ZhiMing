"""The tarot pilot's tuning and final sets (P1 of docs/根因整改实施计划.md) stay usable and apart."""

import yaml

from app import ROOT

TUNING, FINAL = (
    yaml.safe_load((ROOT / f"evals/cases/{name}.yaml").read_text(encoding="utf-8"))["cases"]
    for name in ("tarot_pilot", "tarot_final")
)


def test_cases_have_the_fields_the_live_evaluation_reads(runtime):
    tools = set(runtime.registry.tools)
    for case in TUNING + FINAL:
        assert {"id", "question", "tools", "systems"} <= set(case), case["id"]
        assert set(case["tools"]) <= tools and case["systems"] == ["tarot"], case["id"]
        if case.get("parent"):
            ids = [c["id"] for c in (TUNING if case in TUNING else FINAL)]
            # A follow-up runs after its parent, in the same user's records.
            assert ids.index(case["parent"]) < ids.index(case["id"])


def test_the_final_set_is_never_the_tuning_set():
    assert not {c["id"] for c in TUNING} & {c["id"] for c in FINAL}
    assert not {c["question"] for c in TUNING} & {c["question"] for c in FINAL}

    # Each kind of question the pilot tunes on is checked again in the final set.
    def kinds(cases):
        return {
            ("followup" if c.get("followup") else "risk" if c.get("risk") else "draw")
            for c in cases
        }

    assert kinds(TUNING) == kinds(FINAL)
