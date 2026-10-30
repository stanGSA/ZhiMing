"""Rank the failures of real-model runs: metrics, tool errors by category, final outcomes.

Reads one or more live.json reports (scripts.live_week23) or the archived stage 0 summaries,
which share the same per-case rows. Never calls a model.
"""

import argparse
import glob
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import yaml

# First match wins; the order separates provenance failures from plain fact mismatches.
CATEGORIES = [
    (
        "A 参数不是合法JSON",
        lambda tool, code, error: code == "invalid_arguments" and "合法JSON" in error,
    ),
    ("B 参数不符合schema", lambda tool, code, error: code == "invalid_arguments"),
    ("H 审校工具协议", lambda tool, code, error: tool == "submit_review"),
    (
        "C 画像写入越界（地理/历法口径）",
        lambda tool, code, error: (
            tool == "update_profile"
            and bool(
                re.search(
                    r"地理字段|已确认地点|经纬度|钟表时区|历法与子时|子时规则|location_id",
                    error,
                )
            )
        ),
    ),
    (
        "C 资料来源/地点未确认就计算",
        lambda tool, code, error: bool(
            re.search(
                r"原话|画像|resolve_location|地名解析|已确认地点|候选地名|钟表|历法与子时", error
            )
        ),
    ),
    (
        "D ref_id不属于本次计算",
        lambda tool, code, error: "ref_id" in error or "引用必须来自" in error,
    ),
    (
        "E 事实与计算不符",
        lambda tool, code, error: bool(
            re.search(r"不符|编造|不能使用宫位|日期须与|日期范围|不可用", error)
        ),
    ),
    (
        "F 流程跳步/依赖缺失",
        lambda tool, code, error: (
            code in ("missing_dependency", "missing_signals", "turn_finished")
            or bool(re.search(r"[须必]须?先调用", error))
        ),
    ),
    ("G 释义查询未命中", lambda tool, code, error: code == "missing_entry"),
    ("I 表达策略", lambda tool, code, error: bool(re.search(r"确定性|免责|劝阻就医", error))),
]
QUALITY = ("direct_answer", "time_consistent", "supported_conclusion", "no_fabricated_facts")


def quality_score(row: dict) -> bool | None:
    """Return None when the judge did not produce a complete, parseable score."""
    review = row.get("quality_review")
    if row.get("quality_pass") is None or not isinstance(review, dict):
        return None
    if review.get("error_type") or not all(type(review.get(key)) is bool for key in QUALITY):
        return None
    return all(review[key] for key in QUALITY)


def category(tool: str, code: str | None, error: str | None) -> str:
    error = error or ""
    for name, matches in CATEGORIES:
        if matches(tool, code, error):
            return name
    return f"Z 其他：{(error or code or '')[:30]}"


def task_success(row: dict) -> bool:
    """Final outcome only: a guard rejection the model then corrected is not a failure."""
    return all(
        value
        for key, value in row["checks"].items()
        if key not in ("zero_tool_errors", "low_confidence")
    )


def outcome_failure(row: dict) -> str | None:
    if task_success(row):
        return None
    if row["status"] == "limit_reached":
        return "达到步数或预算上限"
    if row["status"] == "text":
        return "用普通文本代替 ask_user"
    if row["status"] == "model_error":
        return "模型服务错误"
    failed = [
        key for key, value in row["checks"].items() if value is False and key != "zero_tool_errors"
    ]
    return f"结局为 {row['status']}，未通过：{'、'.join(failed)}"


def clean_pass(row: dict) -> bool:
    pipeline = row.get("pipeline") or {}
    return (
        not row.get("tool_errors") and not pipeline.get("repairs") and not pipeline.get("degraded")
    )


def percentile(values: list[float], share: float) -> float | None:
    ordered = sorted(values)
    return ordered[math.ceil(share * len(ordered)) - 1] if ordered else None


def summarize(report: dict) -> dict:
    rows = report["results"]
    errors, cases, failed_cases = Counter(), defaultdict(set), defaultdict(set)
    quality_failures = Counter()
    for row in rows:
        for item in row.get("tool_errors", []):
            name = category(item["tool"], item.get("code"), item.get("error"))
            errors[name] += 1
            case_key = (row.get("repeat", 0), row["id"])
            cases[name].add(case_key)
            if not task_success(row):
                failed_cases[name].add(case_key)
        review = row.get("quality_review") or {}
        if quality_score(row) is not None:
            for key in QUALITY:
                if review.get(key) is False:
                    quality_failures[key] += 1
    latencies = [row["latency_s"] for row in rows]
    inputs = sum(row.get("input_tokens", 0) for row in rows)
    cached = sum(row.get("cached_input_tokens") or 0 for row in rows)
    recorded = bool(rows) and all(
        row.get("cached_input_tokens") is not None and row.get("cached_usage_complete", True)
        for row in rows
    )
    return dict(
        run_id=report.get("run_id"),
        mode=report.get("mode"),
        model=report.get("requested_model"),
        rubric_version=report.get("rubric_version", "v1"),
        cases=len(rows),
        task_success=sum(task_success(row) for row in rows),
        first_try_clean=sum(not row.get("tool_errors") for row in rows),
        submitted=sum(row.get("status") == "submit_reading" for row in rows),
        quality_scored=sum(quality_score(row) is not None for row in rows),
        quality_unscored=sum(quality_score(row) is None for row in rows),
        quality=sum(quality_score(row) is True for row in rows),
        submitted_quality=sum(
            row.get("status") == "submit_reading" and quality_score(row) is True for row in rows
        ),
        task_and_quality=sum(task_success(row) and quality_score(row) is True for row in rows),
        # The pipeline's own record (scripts/live_week23.py); absent rows count as neither.
        repaired=sum(bool((row.get("pipeline") or {}).get("repairs")) for row in rows),
        degraded=sum(bool((row.get("pipeline") or {}).get("degraded")) for row in rows),
        # 根因整改计划 §5: done in one clean pass, without a tool error, a repair or code writing it.
        clean_success=sum(task_success(row) and clean_pass(row) for row in rows),
        strict_v1=sum(row.get("passed") is True for row in rows),
        tool_errors=sum(errors.values()),
        model_calls=sum(row.get("model_calls", 0) for row in rows),
        median_s=statistics.median(latencies) if latencies else None,
        p95_s=percentile(latencies, 0.95),
        input_tokens=inputs,
        output_tokens=sum(row.get("output_tokens", 0) for row in rows),
        cache_rate=cached / inputs if recorded and inputs else None,
        categories=[
            (name, count, len(cases[name]), len(failed_cases[name]))
            for name, count in sorted(errors.items(), key=lambda item: (-item[1], item[0]))
        ],
        outcomes=Counter(filter(None, (outcome_failure(row) for row in rows))),
        quality_failures=quality_failures,
    )


def scan_traces(directory: Path) -> Counter:
    """Why argument JSON failed to parse, from raw_arguments kept in the JSONL traces."""
    reasons = Counter()
    for path in sorted(directory.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            call = event.get("call") or {}
            if event.get("event") != "tool_result" or not call.get("argument_error"):
                continue
            raw = call.get("raw_arguments") or ""
            try:
                json.loads(raw)
                reasons["严格解析可通过（非对象等）"] += 1
            except json.JSONDecodeError as exc:
                try:
                    json.loads(raw, strict=False)
                    reasons[f"{exc.msg}（strict=False 可解析）"] += 1
                except json.JSONDecodeError:
                    reasons[exc.msg] += 1
    return reasons


def rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def cost(summary, pricing):
    if summary["cache_rate"] is None:
        return None
    model = pricing["models"].get(summary["model"])
    if model is None:
        return None
    cached = summary["input_tokens"] * summary["cache_rate"]
    return (
        (summary["input_tokens"] - cached) * model["input_per_mtok"]
        + cached * model["cached_input_per_mtok"]
        + summary["output_tokens"] * model["output_per_mtok"]
    ) / 1_000_000


def render(summaries: list[tuple[str, dict]], traces: Counter | None, pricing=None) -> str:
    lines = ["# 失败归因", "", "## 指标", ""]
    header = ["指标", *[name for name, _ in summaries]]
    lines += ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    metrics = [
        ("模式 / 模型", lambda s: f"{s['mode']} / {s['model']}"),
        ("评委规则版本", lambda s: s["rubric_version"]),
        ("任务完成（不计 zero_tool_errors）", lambda s: f"{s['task_success']}/{s['cases']}"),
        ("已提交回答", lambda s: f"{s['submitted']}/{s['cases']}"),
        ("评委已评分", lambda s: f"{s['quality_scored']}/{s['cases']}"),
        ("评委未评分", lambda s: f"{s['quality_unscored']}/{s['cases']}"),
        ("无工具错误（P1 口径，不要求任务完成）", lambda s: f"{s['first_try_clean']}/{s['cases']}"),
        (
            "任务完成且一次做对（无工具错误、无修复、无降级）",
            lambda s: f"{s['clean_success']}/{s['cases']}",
        ),
        ("流水线修复过", lambda s: f"{s['repaired']}/{s['cases']}"),
        ("流水线降级", lambda s: f"{s['degraded']}/{s['cases']}"),
        ("质量通过", lambda s: f"{s['quality']}/{s['cases']}"),
        (
            "已提交回答的质量通过率",
            lambda s: f"{s['submitted_quality']}/{s['submitted']}" if s["submitted"] else "—",
        ),
        ("任务完成且质量通过", lambda s: f"{s['task_and_quality']}/{s['cases']}"),
        ("原严格综合（v1 口径）", lambda s: f"{s['strict_v1']}/{s['cases']}"),
        ("每题工具错误", lambda s: f"{s['tool_errors'] / s['cases']:.1f}"),
        ("每题模型调用", lambda s: f"{s['model_calls'] / s['cases']:.1f}"),
        ("中位 / P95 耗时（秒）", lambda s: f"{s['median_s']:.1f} / {s['p95_s']:.1f}"),
        (
            "每题输入 / 输出 token",
            lambda s: f"{s['input_tokens'] // s['cases']} / {s['output_tokens'] // s['cases']}",
        ),
        ("前缀缓存命中率", lambda s: rate(s["cache_rate"])),
    ]
    if pricing:
        metrics.append(
            (
                "每题估算成本（" + pricing["currency"] + "；仅被测运行，不含评委）",
                lambda s: (
                    "—" if cost(s, pricing) is None else f"{cost(s, pricing) / s['cases']:.6f}"
                ),
            )
        )
    for label, value in metrics:
        lines.append("| " + " | ".join([label, *[value(s) for _, s in summaries]]) + " |")
    for name, summary in summaries:
        lines += [
            "",
            f"## {name}：工具错误（按次数排序）",
            "",
            "| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |",
            "| --- | ---: | ---: | ---: |",
        ]
        lines += [f"| {c} | {n} | {k} | {f} |" for c, n, k, f in summary["categories"]]
        lines += ["", "最终未完成的原因：", ""]
        lines += [f"- {reason}：{count} 题" for reason, count in summary["outcomes"].most_common()]
        lines += ["", "质量维度失败次数：", ""]
        lines += [f"- {key}：{count}" for key, count in summary["quality_failures"].most_common()]
    if traces is not None:
        lines += ["", "## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）", ""]
        lines += [f"- {reason}：{count}" for reason, count in traces.most_common()] or [
            "- 没有找到"
        ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path, help="live.json 或阶段0摘要 JSON")
    parser.add_argument("--traces", type=Path, help="可选：含 *.jsonl trace 的目录")
    parser.add_argument("--output", type=Path, help="写入 markdown；省略时打印")
    parser.add_argument("--pricing", type=Path)
    args = parser.parse_args()
    paths = [Path(p) for pattern in args.reports for p in glob.glob(str(pattern))]
    if not paths:
        parser.error("没有匹配到报告文件")
    pricing = yaml.safe_load(args.pricing.read_text(encoding="utf-8")) if args.pricing else None
    summaries = [
        (
            path.parent.name if path.name == "live.json" else path.stem,
            summarize(json.loads(path.read_text(encoding="utf-8"))),
        )
        for path in paths
    ]
    text = render(summaries, scan_traces(args.traces) if args.traces else None, pricing)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
