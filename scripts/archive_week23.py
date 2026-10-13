"""Export an allowlist of local verification metrics, never traces or environment values."""

import hashlib
import json
import statistics
from xml.etree import ElementTree

from app import ROOT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_summary(path):
    report = read(path)
    fields = (
        "run_id",
        "requested_model",
        "cases",
        "passed",
        "failed",
        "model_calls",
        "model_request_attempts",
        "review_calls",
        "input_tokens",
        "output_tokens",
        "scope",
    )
    row_fields = (
        "id",
        "name",
        "pass",
        "status",
        "checks",
        "engineering_pass",
        "quality_pass",
        "passed",
        "tools",
        "latency_s",
        "review_latency_s",
        "model_calls",
        "model_request_attempts",
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "returned_models",
        "review_usage",
    )
    result = {k: report[k] for k in fields if k in report}
    result["source_sha256"] = digest(path)
    result["model_calls"] = report.get(
        "model_calls", sum(r.get("model_calls", 0) for r in report["results"])
    )
    result["latency_total_s"] = round(sum(r.get("latency_s", 0) for r in report["results"]), 3)
    result["review_latency_total_s"] = round(
        sum(r.get("review_latency_s", 0) for r in report["results"]), 3
    )
    result["results"] = []
    for row in report["results"]:
        saved = {k: row[k] for k in row_fields if k in row}
        saved["tool_error_count"] = len(row.get("tool_errors", []))
        saved["quality_review"] = {
            k: v
            for k, v in (row.get("quality_review") or {}).items()
            if k
            in (
                "direct_answer",
                "time_consistent",
                "supported_conclusion",
                "no_fabricated_facts",
                "error_type",
            )
        }
        result["results"].append(saved)
    return result


def main():
    local = ROOT / "reports/week23"
    target = ROOT / "docs/verification/week23"
    target.mkdir(parents=True, exist_ok=True)
    xml = local / "pytest-final.xml"
    suite = ElementTree.parse(xml).getroot().find("testsuite")
    tests = [
        dict(
            name=t.attrib["classname"] + "::" + t.attrib["name"],
            status="failed"
            if t.find("failure") is not None or t.find("error") is not None
            else "skipped"
            if t.find("skipped") is not None
            else "passed",
        )
        for t in suite.findall("testcase")
    ]
    outputs = {
        "pytest.json": dict(
            tests=len(tests),
            failures=int(suite.attrib["failures"]),
            errors=int(suite.attrib["errors"]),
            skipped=int(suite.attrib["skipped"]),
            duration_s=float(suite.attrib["time"]),
            results=tests,
            source_sha256=digest(xml),
        ),
        "computations.json": read(local / "computations.json"),
        "knowledge.json": read(ROOT / "data/kb.coverage.json"),
        "live-attempts.json": [
            live_summary(p) for p in sorted((local / "live").glob("*/live.json"))
        ],
        "week1-live-attempts.json": [
            live_summary(p) for p in sorted((local / "week1-live").glob("*/live.json"))
        ],
        "evidence-rereviews.json": [
            item
            for p in sorted((local / "live").glob("*/evidence-rereview-*.json"))
            for item in read(p)
        ],
    }
    trajectories = sorted(
        (local / "offline").glob("*/trajectory.json"), key=lambda p: p.stat().st_mtime
    )
    outputs["trajectory-attempts.json"] = [read(p) for p in trajectories]
    latest = {}
    for run in outputs["live-attempts.json"]:
        for row in run["results"]:
            latest[row["id"]] = {**row, "run_id": run["run_id"]}
    rows = list(latest.values())
    outputs["live-final-selected.json"] = dict(
        scope="Latest result per original synthetic scenario, spanning full batch and targeted retests; original attempts retained.",
        cases=len(rows),
        passed=sum(r["passed"] for r in rows),
        failed=sum(not r["passed"] for r in rows),
        skipped=0,
        tool_errors=sum(r["tool_error_count"] for r in rows),
        model_calls=sum(r["model_calls"] for r in rows),
        model_request_attempts=sum(r.get("model_request_attempts", r["model_calls"]) for r in rows),
        review_calls=sum(bool(r.get("review_usage")) for r in rows),
        input_tokens=sum(
            r["input_tokens"] + r["review_usage"].get("input_tokens", 0) for r in rows
        ),
        output_tokens=sum(
            r["output_tokens"] + r["review_usage"].get("output_tokens", 0) for r in rows
        ),
        agent_latency_total_s=round(sum(r["latency_s"] for r in rows), 3),
        agent_latency_median_s=statistics.median(r["latency_s"] for r in rows),
        agent_latency_max_s=max(r["latency_s"] for r in rows),
        review_latency_total_s=round(sum(r["review_latency_s"] for r in rows), 3),
        returned_models=sorted({m for r in rows for m in r["returned_models"]}),
        results=rows,
    )
    for name, content in outputs.items():
        serialized = json.dumps(content, ensure_ascii=False, indent=2)
        if str(ROOT) in serialized or "C:\\\\Users\\\\" in serialized:
            raise ValueError("Refusing to export a private path")
        (target / name).write_text(serialized + "\n", encoding="utf-8")
    print(json.dumps({"exported_files": len(outputs), "raw_dialogues_exported": False}))


if __name__ == "__main__":
    main()
