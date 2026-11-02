"""The P2 tuning and final sets (docs/根因整改实施计划.md P2) stay usable and apart."""

import pytest
import yaml

from app import ROOT
from common.validation import HIGH_RISK

SYSTEMS = ("dream", "name", "daily")


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


@pytest.mark.parametrize("system", SYSTEMS)
async def test_every_case_is_routed_to_its_pipeline(project, system):
    """The sets measure the pipeline, not the agent loop it hands other questions to."""
    from app import create_runtime
    from pipeline.runner import PipelineRunner
    from tests.pipeline.drafts import Composer

    for case in cases(f"{system}_pilot") + cases(f"{system}_final"):
        user = f"routing-{case['id']}"
        runtime = create_runtime(root=project, user_id=user, model=Composer(), mode="pipeline")
        try:
            if case.get("profile"):
                runtime.store.update_profile_fields(user, case["profile"], "评测预置资料")
                runtime.session.profile = runtime.store.get_profile(user)
                runtime.session.refresh_calendar(runtime.clock())
            found = PipelineRunner(runtime).detect(case["question"])
            assert found is not None and found.system == system, case["id"]
        finally:
            runtime.close()


def test_daily_cases_carry_the_birth_data_the_pipeline_needs():
    for case in cases("daily_pilot") + cases("daily_final"):
        assert {"birth_local_dt", "tz", "lat", "lon", "time_known"} <= set(case["profile"])
