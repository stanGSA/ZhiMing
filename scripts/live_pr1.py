"""One source-version batch; concurrent independent users, each uses the single-agent harness."""

import asyncio
import json
import uuid
from datetime import UTC, datetime

from app import ROOT
from scripts.live_week23 import evaluate

GROUPS = [
    ["astro_trait", "astro_followup", "astro_timing", "ambiguous_place", "dst_fold"],
    ["bazi_trait", "bazi_followup", "bazi_timing", "dst_gap", "lunar_confirm"],
    ["three_system_timing", "unknown_time", "missing_birth", "investment_new", "natural_unknown"],
    ["natural_astro", "natural_bazi", "profile_reuse", "range_before_birth", "overseas_bazi"],
]


async def run():
    output = (
        ROOT
        / "reports/pr1-remediation/batches"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    )
    output.mkdir(parents=True)

    async def group(index, cases):
        return await evaluate(output / f"group{index}", cases, True, True)

    # Independent test users may run concurrently. No conversation uses multiple agents.
    results = await asyncio.gather(*(group(i, cases) for i, cases in enumerate(GROUPS)))
    fingerprints = sorted({r["source_fingerprint"] for r in results})
    rows = [row for result in results for row in result["results"]]
    expected = {name for group in GROUPS for name in group}
    complete = {r["id"] for r in rows} == expected and len(rows) == len(expected)
    report = dict(
        requested_model="gpt-6.1-sol",
        source_fingerprints=fingerprints,
        same_source_version=len(fingerprints) == 1,
        complete=complete,
        cases=len(rows),
        passed=sum(r["passed"] for r in rows),
        failed=sum(not r["passed"] for r in rows),
        skipped=0,
        model_calls=sum(r["model_calls"] for r in results),
        review_calls=sum(r["review_calls"] for r in results),
        model_request_attempts=sum(r["model_request_attempts"] for r in results),
        review_request_attempts=sum(r["review_request_attempts"] for r in results),
        input_tokens=sum(r["input_tokens"] for r in results),
        output_tokens=sum(r["output_tokens"] for r in results),
        results=rows,
        scope="20 fixed cases on one source version, independent synthetic users; same-model rubric, not human review.",
    )
    (output / "batch.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False),
        flush=True,
    )
    return report


if __name__ == "__main__":
    result = asyncio.run(run())
    raise SystemExit(
        0 if result["complete"] and result["same_source_version"] and result["failed"] == 0 else 1
    )
