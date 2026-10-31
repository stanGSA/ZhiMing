"""Why the judge failed answers of a live run: the failed dimensions, its reasons, the answer.

Reads the live.json reports of scripts.live_week23 on the machine that ran them and never
calls a model. The published summaries leave out the judge's reasons and the answers
(scripts/p1_report.PRIVATE), so this is where they can be read. Nothing is published: the
output goes to the terminal or to a file the owner names.

    python -m scripts.quality_reasons reports/p1-tarot/Tarot-pipeline --answers
"""

import argparse
import json
from pathlib import Path

DIMENSIONS = ("direct_answer", "time_consistent", "supported_conclusion", "no_fabricated_facts")


def reports(paths: list[Path]) -> list[Path]:
    """live.json files: given directly, or the latest one under each directory."""
    found = []
    for path in paths:
        if path.is_file():
            found.append(path)
            continue
        runs = sorted(path.glob("*/live.json")) or sorted(path.glob("live.json"))
        if not runs:
            raise FileNotFoundError(f"没有找到 live.json：{path}")
        found.append(runs[-1])
    return found


def failed(row: dict) -> list[str]:
    review = row.get("quality_review") or {}
    if review.get("scored") is False:
        return ["未评分"]
    return [key for key in DIMENSIONS if review.get(key) is False]


def render(path: Path, report: dict, *, answers: bool) -> str:
    rows = report.get("results", [])
    failing = [(row, failed(row)) for row in rows]
    failing = [(row, dims) for row, dims in failing if dims]
    lines = [
        f"## {path.parent.parent.name}/{path.parent.name}",
        "",
        f"模式 {report.get('mode')}，评委 {report.get('judge_model')}，"
        f"质量未通过 {len(failing)}/{len(rows)}",
        "",
    ]
    for row, dims in failing:
        lines += [f"### {row['id']} · 第{row.get('repeat', 0) + 1}次", ""]
        lines.append(f"- 未通过：{'、'.join(dims)}")
        if row.get("pipeline"):
            info = row["pipeline"]
            lines.append(
                f"- 流水线：{info.get('kind')}，修复 {info.get('repairs')}，"
                f"降级 {info.get('degraded') or '无'}"
            )
        reasons = (row.get("quality_review") or {}).get("reasons") or []
        lines.append("- 评委理由：")
        lines += [f"  - {reason}" for reason in reasons] or ["  - （评委没有给出理由）"]
        summary = (row.get("structured") or {}).get("summary")
        if summary:
            lines.append(f"- 摘要：{summary}")
        if answers and row.get("answer"):
            lines += ["", *[f"> {line}" for line in row["answer"].splitlines()]]
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="live.json 或其所在批次目录")
    parser.add_argument("--answers", action="store_true", help="附上回答全文")
    parser.add_argument("--output", type=Path, help="写入文件；默认打印")
    args = parser.parse_args()
    text = "\n".join(
        render(path, json.loads(path.read_text(encoding="utf-8")), answers=args.answers)
        for path in reports(args.paths)
    )
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
