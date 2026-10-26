"""Evaluation summary in one command: ``python -m evals.report``.

Writes ``reports/eval/summary.md`` and ``summary.json``. Everything is computed offline with
the demo model and deterministic code, reusing the existing suites and their scoring, and never
calls a paid model. Real-model rows are only read from the archived summaries under
docs/verification/p1/. Every dataset carries its status; results on draft datasets are marked
草稿 and are not acceptance results.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app import ROOT
from evals import facts, safety
from evals.reviewer import GATES
from evals.reviewer import evaluate as evaluate_reviewer
from evals.run import evaluate as evaluate_trajectory
from evals.week6 import daily_report, strokes_report
from knowledge.build import build
from scripts.failure_taxonomy import percentile, summarize

SCHEMA_VERSION = 1
ARCHIVE = ROOT / "docs/verification/p1"
DATASETS = {
    "trajectory": "evals/cases/trajectory.yaml",
    "reference_charts": "evals/cases/reference_charts.yaml",
    "bazi_boundary": "evals/cases/bazi_boundary.yaml",
    "name_strokes": "evals/cases/name_strokes.yaml",
    "safety": "evals/cases/safety.yaml",
    "reviewer_drafts": "evals/cases/reviewer_drafts.yaml",
}
# The computed datasets have no status field; evals/README.md records how they were checked.
COMPUTED = "computed_cross_checked"
STATUS_LABELS = {
    "draft_needs_review": "草稿，待审核",
    COMPUTED: "计算生成并交叉校验",
}
SCOPE = (
    "离线可复现：离线演示模型与确定性代码，不调用任何付费模型。离线演示的工具选择与审校是规则基线，"
    "只验证流程与计分口径，不代表真实模型的工具选择、解读质量或安全能力。"
)


def dataset_status(name: str) -> dict:
    data = yaml.safe_load((ROOT / DATASETS[name]).read_text(encoding="utf-8"))
    status = data.get("status") or COMPUTED
    entry = dict(file=DATASETS[name], status=status, draft=status.startswith("draft"))
    if name == "name_strokes":
        # Item-level status: the gold strokes of some characters still await a final decision.
        counts: dict[str, int] = {}
        for item in data["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        entry["item_status"] = counts
    return entry


def latency(values_s: list[float]) -> dict:
    return dict(
        n=len(values_s),
        p50_ms=round(statistics.median(values_s) * 1000, 1) if values_s else None,
        # Nearest rank, as in the P1 real-model reports.
        p95_ms=round(percentile(values_s, 0.95) * 1000, 1) if values_s else None,
    )


async def tool_selection(workspace: Path) -> dict:
    result = {}
    for mode in ("single", "multi"):
        report = await evaluate_trajectory(workspace / f"trajectory-{mode}", mode)
        rows = report["results"]
        result[mode] = dict(
            dataset_cases=report["cases"] + report["skipped"],
            cases=report["cases"],
            skipped=report["skipped"],
            passed=report["passed"],
            tool_f1=report["offline_tool_f1"],
            specialist_f1=report["offline_specialist_f1"],
            seed_vector_pass=report["seed_vector_pass"],
            failed=[row["id"] for row in rows if not row["pass"]],
            latency=latency([row["latency_s"] for row in rows]),
        )
    return result


async def fact_checks(workspace: Path) -> dict:
    charts = facts.reference_charts()
    bazi = facts.bazi_boundaries()
    strokes = strokes_report()
    daily = await daily_report(workspace)
    return dict(
        reference_charts=dict(
            cases=charts["cases"],
            passed=charts["passed"],
            max_reference_error_deg=charts["max_reference_error_deg"],
            skyfield_cross_check=charts["max_skyfield_error_deg"] is not None,
            max_skyfield_error_deg=charts["max_skyfield_error_deg"],
            failed=[r["id"] for r in charts["results"] if not r["passed"]],
        ),
        bazi_boundary=dict(
            cases=bazi["cases"],
            variants=bazi["variants"],
            passed=bazi["passed"],
            failed=[r["id"] for r in bazi["results"] if not r["passed"]],
        ),
        name_strokes=dict(
            items=strokes["items"],
            correct=strokes["correct"],
            known_surnames=strokes["known_surnames"],
            known_correct=strokes["known_correct"],
            review_items=strokes["review_items"],
            review_correct=sum(r["ok"] for r in strokes["review"]),
            failed=[r["id"] for r in strokes["failures"]],
        ),
        daily_consistency=dict(
            repeats=daily["repeats"],
            identical=daily["identical"],
            distinct_outputs=daily["distinct_outputs"],
            cache_reused=sum(daily["cache_reused"]),
            seed_repeats=daily["seed_repeats"],
            seed_identical=daily["seed_identical"],
        ),
    )


async def reviewer_baseline(workspace: Path) -> dict:
    report = await evaluate_reviewer(workspace / "reviewer", "demo")
    return dict(
        provider="demo",
        cases=report["cases"],
        miss_rate=report["miss_rate"],
        over_intervention_rate=report["over_intervention_rate"],
        gates=report["gates"],
        per_class={
            cls: dict(cases=v["cases"], correct=v["correct"])
            for cls, v in report["per_class"].items()
        },
        failed=[r["id"] for r in report["results"] if not r["correct"]],
        latency=latency([r["latency_ms"] / 1000 for r in report["results"]]),
    )


def run_date(report: dict) -> str | None:
    if report.get("generated_at"):
        return report["generated_at"][:10]
    stamp = str(report.get("run_id", ""))[:8]
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}" if stamp.isdigit() else None


def archived_runs(directory: Path = ARCHIVE) -> list[dict]:
    """Published real-model summaries; numbers are recomputed with the P1 report's own code."""
    rows = []
    for path in sorted(directory.rglob("*-summary.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        base = dict(
            run=path.relative_to(directory).as_posix().removesuffix("-summary.json"),
            source=path.relative_to(ROOT).as_posix(),
            date=run_date(report),
            model=report.get("requested_model"),
        )
        if "rubric_version" in report:
            s = summarize(report)
            rows.append(
                dict(
                    base,
                    kind="rubric",
                    mode=report["mode"],
                    judge=report.get("judge_model"),
                    rubric_version=report["rubric_version"],
                    repeats=report.get("repeats"),
                    cases=s["cases"],
                    task_success=s["task_success"],
                    submitted=s["submitted"],
                    submitted_quality=s["submitted_quality"],
                    quality=s["quality"],
                    strict_v1=s["strict_v1"],
                    p50_s=s["median_s"],
                    p95_s=s["p95_s"],
                )
            )
        else:
            # Holdout scenarios (scripts.live_test): rule assertions, no judge.
            rows.append(
                dict(
                    base,
                    kind="holdout",
                    mode=None,
                    judge=None,
                    rubric_version="scripts.live_test 留出集断言",
                    cases=report["cases"],
                    passed=report["passed"],
                )
            )
    return rows


async def generate(output: Path) -> dict:
    began = time.perf_counter()
    datasets = {name: dataset_status(name) for name in DATASETS}
    with tempfile.TemporaryDirectory(prefix="zhiming-eval-") as temporary:
        workspace = Path(temporary)
        shutil.copyfile(ROOT / "config.yaml", workspace / "config.yaml")
        build(ROOT / "knowledge/sources", workspace / "data/kb.sqlite", ROOT / "knowledge/rules")
        tools = await tool_selection(workspace)
        checked = await fact_checks(workspace)
        safe = await safety.evaluate(workspace)
        reviewer = await reviewer_baseline(workspace)
    report = dict(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        environment=dict(platform=platform.platform(), python=platform.python_version()),
        offline=True,
        paid_model_calls=0,
        scope=SCOPE,
        datasets=datasets,
        tool_selection=tools,
        facts=checked,
        safety=dict(
            crisis={k: v for k, v in safe["crisis"].items() if k != "results"},
            high_risk=safe["high_risk"],
        ),
        reviewer=reviewer,
        latency=dict(
            single_turn=tools["single"]["latency"],
            multi_turn=tools["multi"]["latency"],
            reviewer=reviewer["latency"],
        ),
        real_model=archived_runs(),
        duration_s=round(time.perf_counter() - began, 1),
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "summary.md").write_text(render(report), encoding="utf-8")
    return report


def ratio(passed: int, total: int) -> str:
    return f"{passed}/{total}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def render(report: dict) -> str:
    datasets = report["datasets"]

    def tag(name: str) -> str:
        return "（草稿）" if datasets[name]["draft"] else ""

    def source(name: str) -> str:
        entry = datasets[name]
        return (
            f"`{Path(entry['file']).name}`（{STATUS_LABELS.get(entry['status'], entry['status'])}）"
        )

    tools, f, s, r, lat = (
        report["tool_selection"],
        report["facts"],
        report["safety"],
        report["reviewer"],
        report["latency"],
    )
    charts, bazi, strokes, daily = (
        f["reference_charts"],
        f["bazi_boundary"],
        f["name_strokes"],
        f["daily_consistency"],
    )
    skyfield = (
        f"Skyfield/JPL 交叉校验最大差 {charts['max_skyfield_error_deg']:.9f}°"
        if charts["skyfield_cross_check"]
        else "Skyfield/JPL 交叉校验未运行（缺少 data/ephe/de440s.bsp）"
    )
    single, multi = tools["single"], tools["multi"]
    gate = r["gates"]
    rows = [
        (
            "工具选择",
            "工具集合 F1（single）",
            f"{single['tool_f1']:.3f}；适用 {single['cases']}/{single['dataset_cases']} 题，"
            f"通过 {single['passed']}{tag('trajectory')}",
            source("trajectory"),
            "离线演示规则模型回放 evals.run 的塔罗题；其余题需要真实模型",
        ),
        (
            "工具选择",
            "工具 / 专家集合 F1（multi）",
            f"{multi['tool_f1']:.3f} / {multi['specialist_f1']:.3f}；适用 {multi['cases']}/"
            f"{multi['dataset_cases']} 题，通过 {multi['passed']}{tag('trajectory')}",
            source("trajectory"),
            "同上，编排者经专家子会话调用工具",
        ),
        (
            "事实",
            "参考星盘",
            f"{ratio(charts['passed'], charts['cases'])}，最大黄经误差 "
            f"{charts['max_reference_error_deg']:.9f}°",
            source("reference_charts"),
            skyfield,
        ),
        (
            "事实",
            "八字边界",
            f"{ratio(bazi['passed'], bazi['cases'])} 用例，{bazi['variants']} 个规则或追问变体",
            source("bazi_boundary"),
            "立春、节气、子时、真太阳时、夏令时、闰月",
        ),
        (
            "事实",
            "姓名笔画",
            f"{ratio(strokes['correct'], strokes['items'])}；其中 {strokes['review_items']} 字的金标"
            f"待人工定稿，这部分 {ratio(strokes['review_correct'], strokes['review_items'])}（草稿）",
            source("name_strokes"),
            f"公认姓氏五格笔画 {ratio(strokes['known_correct'], strokes['known_surnames'])}",
        ),
        (
            "事实",
            "每日运势跨会话一致",
            f"{daily['repeats']} 次调用 {daily['distinct_outputs']} 种结果；"
            f"同 seed 抽牌 {daily['seed_repeats']} 次{'一致' if daily['seed_identical'] else '不一致'}",
            "合成画像，无数据集",
            f"后 {daily['repeats'] - 1} 次中 {daily['cache_reused']} 次读缓存",
        ),
        (
            "安全",
            "危机识别",
            f"{ratio(s['crisis']['passed'], s['crisis']['cases'])}{tag('safety')}",
            source("safety"),
            "运行时停止占卜并给出求助回复（与 tests/runtime 同一组检查）",
        ),
        (
            "安全",
            "高风险提示（代码层）",
            f"{ratio(s['high_risk']['passed'], s['high_risk']['cases'])}{tag('safety')}",
            source("safety"),
            "HIGH_RISK 命中的题强制 safety.flag 与安全说明；其余依赖模型自行标注，离线不评估",
        ),
        (
            "审校",
            "漏拦率 / 过度干预率",
            f"{pct(r['miss_rate'])} / {pct(r['over_intervention_rate'])}{tag('reviewer_drafts')}",
            source("reviewer_drafts"),
            f"离线关键词基线，不是 LLM 审校；关口 ≤{GATES['miss_rate']:.0%} / "
            f"≤{GATES['over_intervention_rate']:.0%}，"
            f"{'均达到' if all(g['met'] for g in gate.values()) else '未全部达到'}",
        ),
        (
            "延迟",
            "离线单轮 P50 / P95",
            f"single {lat['single_turn']['p50_ms']} / {lat['single_turn']['p95_ms']} ms；"
            f"multi {lat['multi_turn']['p50_ms']} / {lat['multi_turn']['p95_ms']} ms",
            source("trajectory"),
            f"审校单次 {lat['reviewer']['p50_ms']} / {lat['reviewer']['p95_ms']} ms；"
            "本机测得，不含模型调用耗时",
        ),
    ]
    lines = [
        "# 评测总表",
        "",
        f"由 `uv run python -m evals.report` 生成于 {report['generated_at']}"
        f"（{report['environment']['platform']}，Python {report['environment']['python']}，"
        f"用时 {report['duration_s']} 秒）。",
        "",
        report["scope"],
        "",
        "## 离线结果",
        "",
        "| 维度 | 指标 | 结果 | 数据集（状态） | 说明 |",
        "| --- | --- | --- | --- | --- |",
        *(f"| {' | '.join(row)} |" for row in rows),
        "",
        "标“草稿”的结果来自待审核数据集，不作为验收结论。",
        "",
        "## 真实模型（只读归档摘要）",
        "",
        "以下数字读取 `docs/verification/p1/` 的已归档摘要，用 `scripts.failure_taxonomy` 的口径重算，"
        "本命令不重新运行任何模型。评委与被测模型同厂商，人工校准未完成，"
        "评委可靠性未经人工验证；详见 [P1 实施与验收](../../docs/verification/p1/README.md)。",
        "",
        "| 批次 | 日期 | 被测模型 | 模式 | 评委 | 口径版本 | 题 × 次 | 任务完成 | 质量通过 "
        "| 已提交回答质量通过 | 严格综合 | P50 / P95 秒 |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for run in report["real_model"]:
        if run["kind"] != "rubric":
            continue
        n = run["cases"]
        lines.append(
            f"| {run['run']} | {run['date']} | {run['model']} | {run['mode']} | {run['judge']} | "
            f"{run['rubric_version']} | {n // run['repeats']} × {run['repeats']} | "
            f"{ratio(run['task_success'], n)} | {ratio(run['quality'], n)} | "
            f"{ratio(run['submitted_quality'], run['submitted']) if run['submitted'] else '—'} | "
            f"{ratio(run['strict_v1'], n)} | {run['p50_s']:.1f} / {run['p95_s']:.1f} |"
        )
    holdout = [run for run in report["real_model"] if run["kind"] == "holdout"]
    if holdout:
        lines += [
            "",
            "留出场景（规则断言，无评委）："
            + "；".join(
                f"{run['run']}（{run['date']}，{run['model']}）{ratio(run['passed'], run['cases'])}"
                for run in holdout
            )
            + "。",
        ]
    lines += [
        "",
        "日期取自批次编号。`p1/` 顶层两批是改用中转接口前的旧活动，`codego-v4/` 是中转接口活动，"
        "其中 Final 为当前实现。任务完成不计 zero_tool_errors；严格综合为 v1 口径"
        "（全部工程检查与四项质量评审同时通过）。",
        "",
        "## 数据集状态",
        "",
        "| 数据集 | 文件 | 状态 |",
        "| --- | --- | --- |",
    ]
    for name, entry in datasets.items():
        status = STATUS_LABELS.get(entry["status"], entry["status"])
        if entry.get("item_status"):
            status += "；逐项：" + "，".join(f"{k} {v}" for k, v in entry["item_status"].items())
        lines.append(f"| {name} | `{entry['file']}` | {status} |")
    misses = {
        "工具选择（single）": single["failed"],
        "工具选择（multi）": multi["failed"],
        "参考星盘": charts["failed"],
        "八字边界": bazi["failed"],
        "姓名笔画": strokes["failed"],
        "高风险提示未被代码识别": s["high_risk"]["missed"],
        "审校判错": r["failed"],
    }
    lines += ["", "## 未通过的用例", ""]
    lines += [f"- {label}：{'、'.join(ids) if ids else '无'}" for label, ids in misses.items()]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="离线生成评测总表，不调用付费模型")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/eval")
    args = parser.parse_args()
    report = asyncio.run(generate(args.output))
    print(f"{args.output / 'summary.md'}（{report['duration_s']} 秒）")


if __name__ == "__main__":
    main()
