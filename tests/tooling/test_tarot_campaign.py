"""The tarot pilot's batches publish like the P1 batch, offline, from synthetic reports."""

import json

import yaml

from app import ROOT
from scripts.p1_campaign import CAMPAIGN_JOBS
from scripts.p1_report import CAMPAIGNS, EXPECTED_CASES, publish

QUALITY = dict(
    direct_answer=True, time_consistent=True, supported_conclusion=True, no_fabricated_facts=True
)


def judged(case_id, repeat, mode, pipeline=None):
    return dict(
        id=case_id,
        repeat=repeat,
        status="submit_reading",
        checks={"expected_status": True, "zero_tool_errors": True},
        quality_review=QUALITY,
        quality_pass=True,
        passed=True,
        tools=["start_reading", "draw_tarot", "submit_reading"],
        tool_errors=[],
        latency_s=10.0,
        model_calls=1 if mode == "pipeline" else 4,
        input_tokens=3000,
        output_tokens=600,
        cached_input_tokens=0,
        pipeline=pipeline,
        trace="missing.jsonl",
    )


def write(root, name, rows, **extra):
    folder = root / name / "run"
    folder.mkdir(parents=True)
    report = dict(run_id=name, requested_model="deepseek-v4-flash", results=rows, **extra)
    (folder / "live.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def test_campaign_jobs_match_the_published_runs_and_datasets():
    for campaign, jobs in CAMPAIGN_JOBS.items():
        published = CAMPAIGNS[campaign]
        assert [name for name, *_ in jobs if name not in published["heldout"]] == [
            name for name in published["runs"] if name in {j[0] for j in jobs}
        ]
        for name, _module, args, count in jobs:
            assert EXPECTED_CASES[name] == count, name
            if "--dataset" in args:
                dataset = yaml.safe_load((ROOT / args[args.index("--dataset") + 1]).read_text())
                assert len(dataset["cases"]) * 3 == count, name


def test_tarot_batches_publish_single_against_pipeline(tmp_path):
    root, output = tmp_path / "runs", tmp_path / "published"
    cases = [f"t{i}" for i in range(8)]
    write(
        root,
        "Tarot-single",
        [judged(c, r, "single") for r in range(3) for c in cases],
        mode="single",
    )
    pipeline_rows = [
        judged(c, r, "pipeline", {"kind": "new", "model_calls": 1, "repairs": 0, "degraded": None})
        for r in range(3)
        for c in cases
    ]
    pipeline_rows[0]["pipeline"] = {"kind": "new", "model_calls": 2, "repairs": 1, "degraded": None}
    write(root, "Tarot-pipeline", pipeline_rows, mode="pipeline")
    heldout = [
        dict(name=f"h{i}", status="submit_reading", checks={"successful_submit": True})
        for i in range(17)
    ]
    write(root, "Tarot-heldout-pipeline", heldout, mode="pipeline", cases=17)
    pricing = ROOT / "docs/verification/p1/codego-v4/pricing.yaml"
    result = publish(root, output, pricing, "tarot")
    assert set(result["completed"]) == {"Tarot-single", "Tarot-pipeline", "Tarot-heldout-pipeline"}
    assert result["paired"]["Tarot-single vs Tarot-pipeline"]["pairs"] == 24
    table = (output / "comparison.md").read_text(encoding="utf-8")
    assert "任务完成且一次做对|修复/降级" in table
    assert "|Tarot-pipeline|24/24|24/24|24/24|24/24|24/24|24/24|24/24|23/24|1/0|" in table
    assert "|Tarot-single|24/24|24/24|24/24|24/24|24/24|24/24|24/24|24/24|0/0|" in table
    assert "- Tarot-heldout-pipeline：17/17" in table
    failures = (output / "failures-Tarot-pipeline.md").read_text(encoding="utf-8")
    assert "| 流水线修复过 | 1/24 |" in failures
