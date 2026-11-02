"""The P2 tuning and final sets (docs/根因整改实施计划.md P2) stay usable and apart."""

import pytest
import yaml

from app import ROOT
from common.validation import HIGH_RISK

SYSTEMS = ("dream", "name")


def cases(name):
    return yaml.safe_load((ROOT / f"evals/cases/{name}.yaml").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("system", SYSTEMS)
def test_cases_have_the_fields_the_live_evaluation_reads(runtime, system):
    tools = set(runtime.registry.tools)
    for case in cases(f"{system}_pilot") + cases(f"{system}_final"):
        assert {"id", "question", "tools", "systems"} <= set(case), case["id"]
        assert set(case["tools"]) <= tools and case["systems"] == [system], case["id"]
        # A risk case is one the code recognises as such, so its safety flag is checked.
        assert bool(case.get("risk")) == bool(HIGH_RISK.search(case["question"])), case["id"]


@pytest.mark.parametrize("system", SYSTEMS)
def test_the_final_set_is_never_the_tuning_set(system):
    tuning, final = cases(f"{system}_pilot"), cases(f"{system}_final")
    assert not {c["id"] for c in tuning} & {c["id"] for c in final}
    assert not {c["question"] for c in tuning} & {c["question"] for c in final}
    # Each kind of question tuned on is checked again in the final set.
    assert {bool(c.get("risk")) for c in tuning} == {bool(c.get("risk")) for c in final}
