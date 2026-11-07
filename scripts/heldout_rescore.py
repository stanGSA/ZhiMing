"""Re-score held-out batches under the old and the new direct_timing_answer (plan P3.0).

Reads each batch's live.json (it keeps every answer's structured output), re-scores the job
change timing case from its saved summary under both word-order readings, and reports the two
side by side; nothing else in a row changes. Rows are first normalized the way p1_report
reports historical held-out batches. Offline: no model is called.

    python -m scripts.heldout_rescore reports/p1/Final-heldout/*/live.json --output rescore.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evals.heldout import first_sentence, timing_answer, timing_answer_legacy
from scripts.p1_report import normalize_heldout_row

CHECK = "direct_timing_answer"


def rescore_row(row: dict) -> dict:
    """{name, legacy, new, legacy_pass, new_pass, sentence} for one held-out row."""
    row = normalize_heldout_row(row)
    checks = row.get("checks", {})
    if CHECK not in checks:
        passed = row["pass"]
        return dict(name=row.get("name"), legacy_pass=passed, new_pass=passed, timing=None)
    summary = (row.get("structured_output") or {}).get("summary")

    def passes(value: bool) -> bool:
        merged = {**checks, CHECK: value}
        return all(v is True for key, v in merged.items() if key != "zero_tool_errors")

    old, new = timing_answer_legacy(summary), timing_answer(summary)
    return dict(
        name=row.get("name"),
        legacy_pass=passes(old),
        new_pass=passes(new),
        timing=dict(legacy=old, new=new, recorded=checks[CHECK], sentence=first_sentence(summary)),
    )


def rescore(path: Path) -> dict:
    data = path.read_bytes()
    report = json.loads(data)
    rows = [rescore_row(row) for row in report.get("results", [])]
    return dict(
        report=str(path),
        sha256=hashlib.sha256(data).hexdigest(),
        cases=len(rows),
        legacy_passed=sum(r["legacy_pass"] for r in rows),
        new_passed=sum(r["new_pass"] for r in rows),
        timing=[r["timing"] for r in rows if r["timing"] is not None],
    )


def markdown(results: list[dict]) -> str:
    lines = [
        "# 留出集按新旧两种 direct_timing_answer 口径重评",
        "",
        "旧口径：P1、P2 期间的断言，只认“下个月……适合……跳槽”一种语序。"
        "新口径：P3.0，两种语序都认（`evals/heldout.py`）。其余断言不变，未调用模型。",
        "",
        "| 批次 | 原始 SHA256 | 题数 | 旧口径通过 | 新口径通过 | 跳槽题 旧 / 新 | 摘要首句 |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        timing = result["timing"]
        verdicts = "；".join(
            f"{'通过' if t['legacy'] else '失败'} / {'通过' if t['new'] else '失败'}"
            for t in timing
        )
        sentences = "；".join(t["sentence"].replace("|", "\\|") for t in timing)
        lines.append(
            f"| {result['report']} | `{result['sha256'][:16]}` | {result['cases']} "
            f"| {result['legacy_passed']}/{result['cases']} | {result['new_passed']}/{result['cases']} "
            f"| {verdicts or '—'} | {sentences or '—'} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", type=Path, help="also write the per-batch results as JSON")
    args = parser.parse_args()
    results = [rescore(path) for path in args.reports]
    text = markdown(results)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
