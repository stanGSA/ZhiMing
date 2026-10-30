"""Per-system baselines from the archived P1 summaries: ``python -m evals.baseline``.

The pipeline refactor (docs/根因整改实施计划.md) moves one system at a time, so each step is
compared with the same questions answered by the previous agent. This reads only the sanitized
summaries committed under docs/verification/p1/codego-v4/, groups their rows by the systems each
question asks for, and reuses the P1 failure taxonomy's scoring. It never calls a model.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import yaml

from app import ROOT
from scripts.failure_taxonomy import percentile, summarize, task_success
from scripts.live_week23 import CASES, NATURAL_CASES

ARCHIVE = ROOT / "docs/verification/p1/codego-v4"
OUTPUT = ROOT / "docs/verification/p1/baseline-by-system"
P1_RUNS = ("Final-single", "Final-multi")
COMPARE_RUNS = ("Compare-single", "Compare-multi", "Compare-multi-lite")
HELDOUT_RUNS = ("Final-heldout",)
# Heldout cases (scripts/live_test.py) that consult tarot only; the rest are crisis checks and
# a profile write, which the pipeline keeps outside its scope.
TAROT_HELDOUT = (
    "三张牌",
    "同会话追问",
    "跨会话追问",
    "明确重抽",
    "单张牌",
    "二选一",
    "投资边界",
    "跳槽时机正面回答",
)
GROUP_LABELS = {
    "astro": "仅占星",
    "bazi": "仅八字",
    "multi": "两个及以上体系",
    "clarify": "应先追问（不应出解读）",
}


def group(systems) -> str:
    systems = set(systems)
    if not systems:
        return "clarify"
    if len(systems) > 1:
        return "multi"
    return next(iter(systems))


def case_groups() -> dict[str, str]:
    groups = {case["id"]: group(case["systems"]) for case in CASES + NATURAL_CASES}
    compare = yaml.safe_load((ROOT / "evals/cases/p1_multi.yaml").read_text(encoding="utf-8"))
    for case in compare["cases"]:
        groups.setdefault(case["id"], group(case.get("systems") or []))
    return groups


def load(name: str) -> dict:
    return json.loads((ARCHIVE / f"{name}-summary.json").read_text(encoding="utf-8"))


def grouped_rows(report: dict, groups: dict[str, str]) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for row in report["results"]:
        rows.setdefault(groups[row["id"]], []).append(row)
    return rows


def run_entry(report: dict, rows: list[dict]) -> dict:
    s = summarize({**report, "results": rows})
    n = s["cases"]
    return dict(
        cases=n,
        questions=len({row["id"] for row in rows}),
        task_success=s["task_success"],
        submitted=s["submitted"],
        # The P1 taxonomy's first_try_clean only means no tool error, failed tasks included.
        no_tool_errors=s["first_try_clean"],
        # What the pipeline is measured against: the task done without a single tool error.
        clean_success=sum(task_success(row) and not row.get("tool_errors") for row in rows),
        submitted_quality=s["submitted_quality"],
        quality=s["quality"],
        tool_errors_per_case=round(s["tool_errors"] / n, 2),
        model_calls_per_case=round(s["model_calls"] / n, 2),
        input_tokens_per_case=round(s["input_tokens"] / n),
        median_s=s["median_s"],
        p95_s=s["p95_s"],
        limit_failures=s["outcomes"].get("达到步数或预算上限", 0),
        quality_failures=dict(s["quality_failures"]),
    )


def heldout_entry(report: dict, names) -> dict:
    rows = [row for row in report["results"] if row["name"] in names]
    latencies = [row["latency_s"] for row in rows]
    return dict(
        cases=len(rows),
        passed=sum(row["pass"] for row in rows),
        submitted=sum(row["status"] == "submit_reading" for row in rows),
        failed=[row["name"] for row in rows if not row["pass"]],
        model_calls_per_case=round(sum(row["model_calls"] for row in rows) / len(rows), 2),
        input_tokens_per_case=round(sum(row["input_tokens"] for row in rows) / len(rows)),
        median_s=statistics.median(latencies),
        p95_s=percentile(latencies, 0.95),
    )


def provenance(name: str, report: dict) -> dict:
    return dict(
        run=name,
        run_id=report.get("run_id"),
        requested_model=report.get("requested_model"),
        rubric_version=report.get("rubric_version"),
        judge_model=report.get("judge_model"),
        source_fingerprint=report.get("source_fingerprint"),
        raw_sha256=report.get("raw_sha256"),
    )


def build_baseline() -> dict:
    groups = case_groups()
    runs, sources = {}, []
    for name in (*P1_RUNS, *COMPARE_RUNS):
        report = load(name)
        sources.append(provenance(name, report))
        runs[name] = {
            key: run_entry(report, rows)
            for key, rows in sorted(grouped_rows(report, groups).items())
        }
    heldout = {}
    for name in HELDOUT_RUNS:
        report = load(name)
        sources.append(provenance(name, report))
        heldout[name] = {"tarot": heldout_entry(report, TAROT_HELDOUT)}
    return dict(
        schema_version=1,
        scope="按体系切分的已归档P1摘要；离线重算，不调用模型。同题3次重复为非独立样本，小样本仅作描述。",
        sources=sources,
        runs=runs,
        heldout=heldout,
    )


def render(baseline: dict) -> str:
    lines = [
        "# P1 按体系切分的基线",
        "",
        "由 `python -m evals.baseline` 从 `docs/verification/p1/codego-v4/` 已入库的摘要离线生成，"
        "评分沿用 `scripts/failure_taxonomy.py`，不调用模型。同题3次重复不是独立样本，小样本只作描述。",
        "",
        "这些是历史基线：归档批次早于当前 main（见根因整改实施计划附录 A），"
        "流水线的对照基线须在当前 main 上重跑。“无工具错误”沿用 P1 的 first_try_clean，"
        "不要求任务完成；“任务完成且无工具错误”才是流水线对照用的口径。",
        "",
        "## 主集与多体系集",
        "",
        "|批次|分组|题×次|任务完成|已提交回答|无工具错误|任务完成且无工具错误|"
        "已提交回答质量通过|质量通过|错误/题|调用/题|输入token/题|P50/P95秒|步数或预算失败|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, groups in baseline["runs"].items():
        for key, e in groups.items():
            n = e["cases"]
            quality = f"{e['submitted_quality']}/{e['submitted']}" if e["submitted"] else "—"
            lines.append(
                f"|{name}|{GROUP_LABELS[key]}|{e['questions']}×{n // e['questions']}"
                f"|{e['task_success']}/{n}|{e['submitted']}/{n}|{e['no_tool_errors']}/{n}"
                f"|{e['clean_success']}/{n}"
                f"|{quality}|{e['quality']}/{n}|{e['tool_errors_per_case']:.2f}"
                f"|{e['model_calls_per_case']:.2f}|{e['input_tokens_per_case']}"
                f"|{e['median_s']:.1f}/{e['p95_s']:.1f}|{e['limit_failures']}|"
            )
    lines += [
        "",
        "## 留出集中的塔罗题",
        "",
        "主集没有只用塔罗的题。留出集 `scripts/live_test.py` 中的8道塔罗题只有脚本断言，"
        "没有评委质量评分，不能作为回答质量基线；塔罗试点的质量对照见 `evals/cases/tarot_pilot.yaml`。",
        "",
        "|批次|题数|脚本断言通过|已提交回答|调用/题|输入token/题|P50/P95秒|未通过|",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, groups in baseline["heldout"].items():
        e = groups["tarot"]
        lines.append(
            f"|{name}|{e['cases']}|{e['passed']}/{e['cases']}|{e['submitted']}/{e['cases']}"
            f"|{e['model_calls_per_case']:.2f}|{e['input_tokens_per_case']}"
            f"|{e['median_s']:.1f}/{e['p95_s']:.1f}|{'、'.join(e['failed']) or '无'}|"
        )
    lines += [
        "",
        "## 来源",
        "",
        "|批次|run_id|模型|rubric|评委|源码指纹|原始结果SHA256|",
        "|---|---|---|---|---|---|---|",
    ]
    for s in baseline["sources"]:
        lines.append(
            f"|{s['run']}|{s['run_id']}|{s['requested_model']}|{s['rubric_version'] or '—'}"
            f"|{s['judge_model'] or '—'}|{(s['source_fingerprint'] or '—')[:16]}"
            f"|{s['raw_sha256'][:16]}|"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="按体系切分已归档的P1基线（离线）")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    baseline = build_baseline()
    args.output.with_suffix(".json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_suffix(".md").write_text(render(baseline), encoding="utf-8")
    print(args.output.with_suffix(".md"))


if __name__ == "__main__":
    main()
