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


async def evaluate(output: Path, mode: str = "single") -> dict:
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
            runtime = create_runtime(
                root=workspace, user_id=case["id"], provider="demo", seed=42, mode=mode
            )
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
                # Child-session traces share the user directory, so computation tools called by
                # specialists count exactly as in single mode.
                actual -= {
                    "get_profile",
                    "start_reading",
                    "lookup_meaning",
                    "read_reading",
                    "consult_specialist",
                    "submit_report",
                    # Week 5 orchestration tools: the reviewer's verdict and the merge view.
                    "submit_review",
                    "merge_signals",
                }
                consulted = {
                    row["call"]["arguments"]["system"]
                    for row in records
                    if row["event"] == "tool_result"
                    and row["call"]["name"] == "consult_specialist"
                    and row["result"]["ok"]
                    and row["result"]["data"]["report"]["status"] == "ok"
                }
                spread = runtime.session.state.get("tarot_result", {}).get("spread")
                score = f1(set(case["expected"]["tools_single"]), actual)
                specialist_score = (
                    f1(set(case["expected"]["specialists"]), consulted) if mode == "multi" else None
                )
                rows.append(
                    {
                        "id": case["id"],
                        "status": result.status,
                        "tool_f1": score,
                        "specialist_f1": specialist_score,
                        "spread": spread,
                        "expected_spread": case["expected"]["tarot_spread"],
                        "pass": result.status == "submit_reading"
                        and score == 1
                        and specialist_score in (None, 1)
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
        "mode": mode,
        "provider": "demo",
        "scope": "离线流程验收，不能代表真实 LLM 的工具选择、解读质量或安全能力。",
        "dataset_status": fixture["status"],
        "coverage": coverage,
        "cases": len(rows),
        "passed": sum(row["pass"] for row in rows),
        "skipped": len(fixture["cases"]) - len(rows),
        "offline_tool_f1": sum(row["tool_f1"] for row in rows) / len(rows),
        "offline_specialist_f1": None
        if mode == "single"
        else sum(row["specialist_f1"] for row in rows) / len(rows),
        "seed_vector_pass": vector_ok,
        "results": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    stem = "week1-eval" if mode == "single" else "week1-eval-multi"
    (output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = [
        "# 第一周离线流程验收" + ("" if mode == "single" else "（多Agent模式）"),
        "",
        report["scope"],
        "",
        f"- 原数据集状态：{fixture['status']}（未将草稿标为已审核）",
        f"- 适用用例：{len(rows)}；通过：{report['passed']}；后续体系用例跳过：{report['skipped']}",
        f"- 离线工具集合 F1：{report['offline_tool_f1']:.3f}",
        *(
            []
            if mode == "single"
            else [f"- 离线专家集合 F1：{report['offline_specialist_f1']:.3f}"]
        ),
        f"- 塔罗条目覆盖：{coverage['coverage']:.0%}（156 牌面状态 + 7 牌位）",
        f"- 人工审核率：{coverage['reviewed_rate']:.0%}",
        "- 释义审核状态（草稿/模型交叉审核/人工审核）："
        + "/".join(str(n) for n in coverage["review_status"]["counts"].values()),
        f"- 固定 seed 测试向量：{'通过' if vector_ok else '失败'}",
        "",
        "| 用例 | 结果 | 牌阵 | F1 |",
        "|---|---|---|---|",
    ]
    text.extend(
        f"| {row['id']} | {'通过' if row['pass'] else '失败'} | {row['spread']} | {row['tool_f1']:.3f} |"
        for row in rows
    )
    (output / f"{stem}.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite", choices=["week1", "trajectory", "week23", "reviewer", "week6"], default="week1"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    parser.add_argument("--mode", choices=["single", "multi"], default="single")
    parser.add_argument(
        "--provider",
        choices=["demo", "deepseek", "openai", "anthropic"],
        default="demo",
        help="仅 reviewer：demo 为离线关键词基线",
    )
    parser.add_argument("--model", help="仅 reviewer：审校模型名，默认 config.models.reviewer")
    parser.add_argument(
        "--strictness", choices=["lenient", "strict"], default="lenient", help="仅 reviewer"
    )
    args = parser.parse_args()
    if args.suite == "reviewer":
        from evals.reviewer import evaluate as evaluate_reviewer

        report = asyncio.run(
            evaluate_reviewer(args.output, args.provider, args.model, args.strictness)
        )
        print(
            json.dumps(
                {k: v for k, v in report.items() if k not in ("results", "per_class")},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(0 if all(g["met"] for g in report["gates"].values()) else 1)
    if args.suite == "week6":
        from evals.week6 import evaluate as evaluate_week6

        report = asyncio.run(evaluate_week6(args.output))
        print(
            json.dumps(
                {k: report[k] for k in ("suite", "gates", "reviewed_rate", "output_dir")},
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(0 if all(g["met"] for g in report["gates"].values()) else 1)
    if args.suite == "week1":
        report = asyncio.run(evaluate(args.output, args.mode))
    elif args.mode == "multi":
        raise SystemExit(
            "trajectory/week23 是标注路线回放，只适用于 single；多Agent路由需真实模型评估"
        )
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
