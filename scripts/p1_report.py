"""Publish sanitized P1 summaries and paired results from completed serial runs."""

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from scripts.failure_taxonomy import cost, quality_score, render, scan_traces, summarize
from scripts.p1_calibration import score
from signals.merge import undisclosed

RUNS = [
    "B0-single",
    "B0-multi",
    "Final-single",
    "Final-multi",
    "Compare-single",
    "Compare-multi",
    "Compare-multi-lite",
]
EXPECTED_CASES = {
    "B0-single": 60,
    "B0-multi": 60,
    "Final-single": 60,
    "Final-multi": 60,
    "Compare-single": 36,
    "Compare-multi": 36,
    "Compare-multi-lite": 36,
    "B0-heldout": 17,
    "Final-heldout": 17,
}
PRIVATE = {
    "question",
    "clarification",
    "answer",
    "structured",
    "structured_output",
    "calculated_facts",
    "trace",
    "text",
}


def normalize_heldout_row(row):
    """Re-score historical holdout assertions using the corrected zero-tool policy."""
    row = json.loads(json.dumps(row))
    checks = row.get("checks", {})
    if "low_confidence" in checks:
        level = (row.get("structured_output") or {}).get("confidence", {}).get("level")
        checks["confidence_not_overstated"] = level in ("low", "medium")
        checks.pop("low_confidence", None)
    row["pass"] = all(value is True for key, value in checks.items() if key != "zero_tool_errors")
    return row


def valid_tension_table(table):
    """Whether a saved merge table has the fields required by ``undisclosed``."""
    if not isinstance(table, dict) or not isinstance(table.get("tensions"), list):
        return False
    for tension in table["tensions"]:
        if not isinstance(tension, dict) or not all(
            isinstance(tension.get(key), str) for key in ("horizon", "theme", "theme_label")
        ):
            return False
        if not isinstance(tension.get("systems"), list) or not all(
            isinstance(system, str) for system in tension["systems"]
        ):
            return False
        windows = tension.get("windows")
        if not isinstance(windows, list) or not all(
            isinstance(window, dict) and isinstance(window.get("window"), str) for window in windows
        ):
            return False
    return True


def paired(left, right):
    a = {(r.get("repeat", 0), r["id"]): r for r in left["results"]}
    b = {(r.get("repeat", 0), r["id"]): r for r in right["results"]}
    if a.keys() != b.keys():
        raise ValueError("paired comparison requires identical repeat/id keys")
    wins = losses = ties = 0
    for key, row in a.items():
        first = row.get("status") == "submit_reading" and quality_score(row) is True
        second = b[key].get("status") == "submit_reading" and quality_score(b[key]) is True
        wins += second > first
        losses += second < first
        ties += second == first
    return {"pairs": len(a), "right_wins": wins, "left_wins": losses, "ties": ties}


def publish(root, output, pricing_path):
    root, output = root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    pricing = yaml.safe_load(pricing_path.read_text(encoding="utf-8"))
    reports, summaries, manifest = {}, {}, {}
    for name in [*RUNS, "B0-heldout", "Final-heldout"]:
        paths = sorted((root / name).glob("*/live.json"))
        if not paths:
            continue
        path = paths[-1]
        report = json.loads(path.read_text(encoding="utf-8"))
        if len(report.get("results", [])) != EXPECTED_CASES[name]:
            continue
        reports[name] = report
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[name] = {"sha256": digest, "source": path.relative_to(root).as_posix()}
        safe = {k: v for k, v in report.items() if k not in ("results", "output_dir")}
        safe["raw_sha256"] = digest
        result_rows = (
            [normalize_heldout_row(row) for row in report["results"]]
            if name in ("B0-heldout", "Final-heldout")
            else report["results"]
        )
        safe["results"] = [
            {k: v for k, v in row.items() if k not in PRIVATE} for row in result_rows
        ]
        if name in ("B0-heldout", "Final-heldout"):
            safe["passed"] = sum(row["pass"] for row in result_rows)
        for row in safe["results"]:
            review = row.get("quality_review")
            if review:
                row["quality_review"] = {k: v for k, v in review.items() if k != "reasons"}
        (output / f"{name}-summary.json").write_text(
            json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        source = path.parent / "source-hashes.json"
        if source.exists():
            (output / f"{name}-source-hashes.json").write_bytes(source.read_bytes())
        if name in RUNS:
            summaries[name] = summarize(report)
            (output / f"failures-{name}.md").write_text(
                render([(name, summaries[name])], scan_traces(path.parent), pricing),
                encoding="utf-8",
            )
    for name in ("B0-heldout", "Final-heldout"):
        if name not in reports:
            continue
        rows = [normalize_heldout_row(row) for row in reports[name]["results"]]
        reports[name]["passed"] = sum(row["pass"] for row in rows)
    (output / "raw-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# P1 真实串行对照",
        "",
        "仅列已完整结束的批次；待完成不补零。原始答案/trace保留本机，入库摘要附原始文件SHA256。",
        "",
        "|版本|任务完成|已提交回答|评委已评分|无工具错误|已提交回答质量通过率|质量通过|严格综合|错误/题|调用/题|P50/P95秒|缓存|USD/题|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    table_rows = []
    for name in RUNS:
        s = summaries.get(name)
        if not s:
            line = f"|{name}|待完成|—|—|—|—|—|—|—|—|—|—|—|"
        else:
            n = s["cases"]
            counts = [
                f"{s[key]}/{n}"
                for key in (
                    "task_success",
                    "submitted",
                    "quality_scored",
                    "first_try_clean",
                    "submitted_quality",
                    "quality",
                    "strict_v1",
                )
            ]
            counts[4] = f"{s['submitted_quality']}/{s['submitted']}" if s["submitted"] else "—"
            money = cost(s, pricing)
            cache = "未知" if s["cache_rate"] is None else f"{s['cache_rate']:.1%}"
            usd = "未知" if money is None else f"{money / n:.6f}"
            line = (
                "|"
                + "|".join(
                    [
                        name,
                        *counts,
                        f"{s['tool_errors'] / n:.2f}",
                        f"{s['model_calls'] / n:.2f}",
                        f"{s['median_s']:.1f}/{s['p95_s']:.1f}",
                        cache,
                        usd,
                    ]
                )
                + "|"
            )
        lines.append(line)
        table_rows.append(line)
    lines += [
        "",
        "费用仅被测运行（包含专家/运行审校），不含rubric评委；按pricing.yaml指定日期费率估算，非账单。缺失usage或cache时未知。延迟含澄清、不含rubric评分和准备工作。评委Pro与运行Flash同厂商，人工校准未完成前不宣称评委可靠性已验证。",
        "",
        "## 配对结果",
        "",
        "胜负指标：同repeat/id的任务完成且质量通过；同题3次非独立样本，小样本仅作描述。",
    ]
    comparisons = {}
    for left, right in (
        ("B0-single", "Final-single"),
        ("B0-multi", "Final-multi"),
        ("Compare-single", "Compare-multi"),
        ("Compare-single", "Compare-multi-lite"),
        ("Compare-multi", "Compare-multi-lite"),
    ):
        if left in reports and right in reports:
            result = paired(reports[left], reports[right])
            comparisons[f"{left} vs {right}"] = result
            lines += [
                f"- {left} → {right}：右胜{result['right_wins']}，左胜{result['left_wins']}，平{result['ties']}，共{result['pairs']}配对。"
            ]
    lines += ["", "## 多体系合规", "", "|模式|报告合规率|张力覆盖|", "|---|---:|---|"]
    for name in ("Compare-single", "Compare-multi", "Compare-multi-lite"):
        report = reports.get(name)
        if not report:
            continue
        compliance = (report.get("multi_agent") or {}).get("report_compliance_rate")
        evaluable, disclosed, malformed = 0, 0, 0
        for row in report["results"]:
            trace_path = Path(row["trace"])
            if not trace_path.exists():
                continue
            tables = [
                e.get("result", {}).get("data", {}).get("merge")
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if (e := json.loads(line)).get("event") == "tool_result"
                and e.get("call", {}).get("name") == "merge_signals"
                and e.get("result", {}).get("ok")
            ]
            table = next(
                (table for table in reversed(tables) if table and table.get("tensions")), None
            )
            if table:
                if not valid_tension_table(table):
                    malformed += 1
                    continue
                from common.schemas import Reading

                evaluable += 1
                structured = row.get("structured")
                disclosed += bool(
                    structured and not undisclosed(table, Reading.model_validate(structured))
                )
        coverage = f"{disclosed}/{evaluable}" if evaluable else "无可评估的实际张力（不按100%）"
        if malformed:
            coverage += f"（另有{malformed}条合并记录格式异常，未纳入）"
        lines.append(f"|{name}|{compliance if compliance is not None else '不适用'}|{coverage}|")
    lines += ["", "## 留出集", ""]
    for name in ("B0-heldout", "Final-heldout"):
        if name in reports:
            r = reports[name]
            lines.append(
                f"- {name}：{r['passed']}/{r['cases']}，verdict结构化断言口径（旧agent缺字段计失败，不能解读为旧文本内容变差）。"
            )
    lines += ["", "## 评测脚本哈希核对", ""]
    for mode in ("single", "multi"):
        baseline = output / f"B0-{mode}-source-hashes.json"
        final = output / f"Final-{mode}-source-hashes.json"
        if baseline.exists() and final.exists():
            b_hashes = json.loads(baseline.read_text(encoding="utf-8"))
            f_hashes = json.loads(final.read_text(encoding="utf-8"))
            same = b_hashes.get("scripts/live_test.py") == f_hashes.get("scripts/live_test.py")
            lines.append(
                f"- B0-{mode} / Final-{mode} 的留出集评测脚本 `scripts/live_test.py`："
                f"{'哈希一致' if same else '哈希不一致'}"
                + (
                    f"（SHA256 `{f_hashes['scripts/live_test.py']}`）。"
                    if same and f_hashes.get("scripts/live_test.py")
                    else "。"
                )
            )
            if not same:
                raise ValueError(f"B0-{mode} 与 Final-{mode} 的留出集评测脚本哈希不一致")
    labels = root / "human-calibration.json"
    if labels.exists():
        try:
            kappas = score(labels)
            lines += ["", "人工标签kappa：" + json.dumps(kappas, ensure_ascii=False)]
        except ValueError:
            lines += ["", "人工校准待完成：20份四维标签尚不齐，kappa不计算。"]
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "paired.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"completed": list(reports), "paired": comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pricing", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.root, args.output, args.pricing), ensure_ascii=False))


if __name__ == "__main__":
    main()
