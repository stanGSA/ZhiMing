"""Rebuild the nested call tree of one reading from the per-session JSONL traces."""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import ROOT
from harness.trace import Tracer


def load(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def build_tree(records: list[dict], reading_id: str) -> dict:
    """Group events by session and link each child to the consult call that spawned it."""
    sessions: dict[str, dict] = {}
    for row in sorted(records, key=lambda r: r["timestamp"]):
        if row.get("reading_id") != reading_id:
            continue
        node = sessions.setdefault(
            row["session_id"],
            dict(
                session_id=row["session_id"],
                role=row["role"],
                parent_session_id=row.get("parent_session_id"),
                parent_call_id=row.get("parent_call_id"),
                events=[],
                children=[],
            ),
        )
        node["events"].append(row)
    problems = []
    for node in sessions.values():
        queued = {
            e["child_session_id"]: e for e in node["events"] if e["event"] == "specialist_queued"
        }
        finished = {
            e["child_session_id"] for e in node["events"] if e["event"] == "specialist_finished"
        }
        for child_id, event in queued.items():
            child = sessions.get(child_id)
            if child is None:
                problems.append(f"{node['session_id']}: 子会话 {child_id} 没有 trace")
            else:
                if child["parent_call_id"] != event["call_id"]:
                    problems.append(f"{child_id}: parent_call_id 与咨询调用不一致")
                names = {e["event"] for e in child["events"]}
                if not {"session_started", "session_finished"} <= names:
                    problems.append(f"{child_id}: 子会话缺少开始或结束事件")
            if child_id not in finished:
                problems.append(f"{child_id}: 缺少 specialist_finished")
        consult_calls = {
            e["call"]["id"]
            for e in node["events"]
            if e["event"] == "tool_result"
            and e["call"]["name"] == "consult_specialist"
            and e["result"]["ok"]
            and not e["result"].get("cached")
        }
        missing = consult_calls - {e["call_id"] for e in queued.values()}
        problems.extend(f"{node['session_id']}: 咨询调用 {c} 没有子会话" for c in sorted(missing))
    roots = []
    for node in sessions.values():
        parent = sessions.get(node["parent_session_id"])
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    for node in sessions.values():
        if node["parent_session_id"] and node["parent_session_id"] not in sessions:
            problems.append(f"{node['session_id']}: 找不到父会话 {node['parent_session_id']}")
    return dict(reading_id=reading_id, roots=roots, problems=problems)


SCOPE_CODES = {"unknown_tool", "permission_denied", "partition_denied"}


def specialist_metrics(records: list[dict]) -> dict:
    """Plan metrics from traces.

    - Concurrency counts only execution (after the parallelism permit), never queueing.
    - report_compliance_rate (the >=98% gate): consults that ended with a valid report, over
      consults that ran, excluding needs_input (a legitimate request for user data). Failed
      consults that never submitted a report count against it.
    - report_first_pass_rate: consults whose first submit_report passed validation, over
      consults that submitted at least once. report_corrected_pass_rate: consults with any
      accepted submission (first try or after correction), same denominator; consults that
      never submitted are counted separately (consults_without_submission) and only lower
      report_compliance_rate. submit_attempt_pass_rate counts every attempt.
    """

    def by_child(name):
        return {e["child_session_id"]: e for e in records if e["event"] == name}

    def at(event):
        return datetime.fromisoformat(event["timestamp"])

    started, finished = by_child("specialist_started"), by_child("specialist_finished")
    edges = []
    for child, event in started.items():
        edges.append((at(event), 1))
        if child in finished:
            edges.append((at(finished[child]), -1))
    running = peak = 0
    for _, step in sorted(edges):
        running += step
        peak = max(peak, running)
    calls = [e for e in records if e.get("parent_session_id") and e["event"] == "tool_result"]
    submits = sorted(
        (e for e in calls if e["call"]["name"] == "submit_report"), key=lambda e: e["timestamp"]
    )
    first, passed = {}, {}
    for event in submits:
        first.setdefault(event["session_id"], event["result"]["ok"])
        passed[event["session_id"]] = passed.get(event["session_id"]) or event["result"]["ok"]
    ran = [e for e in finished.values() if e["status"] != "cancelled"]
    statuses = Counter(e["status"] for e in finished.values())
    gated = len(ran) - statuses.get("needs_input", 0)

    def rate(numerator, denominator):
        return numerator / denominator if denominator else None

    return dict(
        consults=len(finished),
        statuses=dict(statuses),
        specialist_tool_calls=len(calls),
        out_of_scope_attempts=sum(e["result"].get("code") in SCOPE_CODES for e in calls),
        report_submissions=len(submits),
        report_submissions_accepted=sum(e["result"]["ok"] for e in submits),
        consults_with_submission=len(first),
        consults_without_submission=len([e for e in ran if e["child_session_id"] not in first]),
        report_first_pass=sum(first.values()),
        report_corrected_pass=sum(passed.values()),
        report_compliance_rate=rate(statuses.get("ok", 0), gated),
        report_first_pass_rate=rate(sum(first.values()), len(first)),
        report_corrected_pass_rate=rate(sum(passed.values()), len(first)),
        submit_attempt_pass_rate=rate(sum(e["result"]["ok"] for e in submits), len(submits)),
        max_concurrent_specialists=peak,
        queue_ms=[e.get("queue_ms", 0) for e in finished.values()],
        specialist_latency_ms=[e["latency_ms"] for e in finished.values()],
        specialist_tokens=sum(e["tokens"] for e in finished.values()),
    )


def render(node: dict, depth: int = 0) -> list[str]:
    calls = [e["call"]["name"] for e in node["events"] if e["event"] == "tool_result"]
    tokens = sum(
        (e.get("input_tokens") or 0) + (e.get("output_tokens") or 0)
        for e in node["events"]
        if e["event"] == "model_response"
    )
    lines = ["  " * depth + f"{node['role']} {node['session_id'][:8]} tokens={tokens} {calls}"]
    for child in node["children"]:
        lines.extend(render(child, depth + 1))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="用户编号（目录按哈希定位）")
    parser.add_argument("--reading", required=True)
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    tree = build_tree(load(Tracer(args.runs).user_dir(args.user)), args.reading)
    if args.json:
        print(json.dumps(tree, ensure_ascii=False, indent=2, default=str))
    else:
        for root in tree["roots"]:
            print("\n".join(render(root)))
        print("问题：" + ("无" if not tree["problems"] else "；".join(tree["problems"])))
    raise SystemExit(1 if tree["problems"] else 0)


if __name__ == "__main__":
    main()
