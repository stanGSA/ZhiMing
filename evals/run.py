from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app import ROOT, create_runtime
from knowledge.build import build
from plugins.tarot.draw import draw_tarot


def f1(expected: set, actual: set) -> float:
    intersection = len(expected & actual)
    return 2 * intersection / (len(expected) + len(actual)) if expected or actual else 1.0


async def evaluate(output: Path) -> dict:
    fixture = yaml.safe_load((ROOT / "evals/cases/trajectory.yaml").read_text(encoding="utf-8"))
    cases = [
        case
        for case in fixture["cases"]
        if set(case["expected"].get("tools_single", [])) == {"draw_tarot", "submit_reading"}
        and case["type"] != "followup"
    ]
    rows = []
    with tempfile.TemporaryDirectory(prefix="zhiming-week1-") as temporary:
        workspace = Path(temporary)
        shutil.copyfile(ROOT / "config.yaml", workspace / "config.yaml")
        coverage = build(
            ROOT / "knowledge/sources", workspace / "data/kb.sqlite", ROOT / "knowledge/rules"
        )
        for case in cases:
            runtime = create_runtime(root=workspace, user_id=case["id"], provider="demo", seed=42)
            try:
                result = await runtime.turn(case["question"])
                traces = list(runtime.tracer.user_dir(case["id"]).glob("*.jsonl"))
                records = [
                    json.loads(line)
                    for path in traces
                    for line in path.read_text(encoding="utf-8").splitlines()
                ]
                actual = {
                    row["call"]["name"]
                    for row in records
                    if row["event"] == "tool_result" and row["result"]["ok"]
                }
                actual -= {"get_profile", "start_reading", "lookup_meaning", "read_reading"}
                spread = runtime.session.state.get("tarot_result", {}).get("spread")
                score = f1(set(case["expected"]["tools_single"]), actual)
                rows.append(
                    {
                        "id": case["id"],
                        "status": result.status,
                        "tool_f1": score,
                        "spread": spread,
                        "expected_spread": case["expected"]["tarot_spread"],
                        "pass": result.status == "submit_reading"
                        and score == 1
                        and spread == case["expected"]["tarot_spread"],
                    }
                )
                target = output / "week1_traces" / case["id"]
                target.mkdir(parents=True, exist_ok=True)
                for path in traces:
                    shutil.copyfile(path, target / path.name)
            finally:
                runtime.close()
    vectors = yaml.safe_load((ROOT / "plugins/tarot/evals/cases.yaml").read_text(encoding="utf-8"))
    vector_ok = all(
        [
            {k: c[k] for k in ("card_id", "reversed")}
            for c in draw_tarot(case["spread"], case["question"], case["seed"])["cards"]
        ]
        == case["expected"]
        for case in vectors["cases"]
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "suite": "week1",
        "provider": "demo",
        "scope": "离线流程验收，不能代表真实 LLM 的工具选择、解读质量或安全能力。",
        "dataset_status": fixture["status"],
        "coverage": coverage,
        "cases": len(rows),
        "passed": sum(row["pass"] for row in rows),
        "skipped": len(fixture["cases"]) - len(rows),
        "offline_tool_f1": sum(row["tool_f1"] for row in rows) / len(rows),
        "seed_vector_pass": vector_ok,
        "results": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "week1-eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = [
        "# 第一周离线流程验收",
        "",
        report["scope"],
        "",
        f"- 原数据集状态：{fixture['status']}（未将草稿标为已审核）",
        f"- 适用用例：{len(rows)}；通过：{report['passed']}；后续体系用例跳过：{report['skipped']}",
        f"- 离线工具集合 F1：{report['offline_tool_f1']:.3f}",
        f"- 塔罗条目覆盖：{coverage['coverage']:.0%}（156 牌面状态 + 7 牌位）",
        f"- 人工审核率：{coverage['reviewed_rate']:.0%}",
        f"- 固定 seed 测试向量：{'通过' if vector_ok else '失败'}",
        "",
        "| 用例 | 结果 | 牌阵 | F1 |",
        "|---|---|---|---|",
    ]
    text.extend(
        f"| {row['id']} | {'通过' if row['pass'] else '失败'} | {row['spread']} | {row['tool_f1']:.3f} |"
        for row in rows
    )
    (output / "week1-eval.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["week1", "trajectory", "week23"], default="week1")
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    if args.suite == "week1":
        report = asyncio.run(evaluate(args.output))
    else:
        from evals.week23 import evaluate as evaluate_week23

        report = asyncio.run(evaluate_week23(args.output))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("results", "coverage")},
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(
        0 if report["passed"] == report["cases"] and report.get("seed_vector_pass", True) else 1
    )


if __name__ == "__main__":
    main()
