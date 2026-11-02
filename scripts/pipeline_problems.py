"""What the pipeline's checks found in each draft of a live run, read from its traces.

The published summaries keep only how many problems each draft had (scripts/live_test.py
pipeline_record). The texts are traced as the ``problems`` stage (pipeline/runner.py), and this
reads them back on the machine that ran the batch; it never calls a model. Runs traced before
that stage existed show no texts.

Without --tally the output names each answer's problems and quotes fragments of the drafts, so
it stays local like scripts.quality_reasons. With --tally it is one table of the problem kinds
per batch, with every quoted fragment replaced by “…”, which can be published with the run.

    python -m scripts.pipeline_problems reports/p2-r2/Dream-pipeline
    python -m scripts.pipeline_problems reports/p2-r2/Dream-pipeline --tally
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from scripts.quality_reasons import reports, run_name

QUOTED = re.compile(r"“[^”]*”|「[^」]*」|‘[^’]*’")
DIGITS = re.compile(r"\d+")


def drafts(row: dict) -> list[list[str]] | None:
    """Each draft's problems for one answer; None when its trace has no texts."""
    path = Path(row.get("trace") or "")
    if not path.is_file():
        return None
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("stage") == "problems":
            found.append(list(event.get("problems") or []))
    return found if found or not (row.get("pipeline") or {}).get("problems") else None


def kind(problem: str) -> str:
    """A problem without the drafts' own words: what kind of check it was."""
    return DIGITS.sub("N", QUOTED.sub("“…”", problem))


def render(path: Path, report: dict) -> str:
    lines = [f"# {run_name(path)}", ""]
    for row in report.get("results", []):
        if not row.get("pipeline"):
            continue
        name = f"{row['id']}#{row.get('repeat', 0) + 1}"
        found = drafts(row)
        if found is None:
            lines.append(f"- {name}：trace 中没有问题文字")
            continue
        if not found:
            continue
        lines.append(f"- {name}（降级：{row['pipeline'].get('degraded') or '无'}）")
        for number, problems in enumerate(found, 1):
            lines += [f"  - 第{number}稿：{problem}" for problem in problems]
    return "\n".join(lines)


def tally(path: Path, report: dict) -> str:
    counts, missing = Counter(), 0
    for row in report.get("results", []):
        if not row.get("pipeline"):
            continue
        found = drafts(row)
        if found is None:
            missing += 1
            continue
        for number, problems in enumerate(found, 1):
            for problem in problems:
                counts[("首稿" if number == 1 else "修复稿", kind(problem))] += 1
    lines = [f"## {run_name(path)}", "", "| 稿 | 问题类别 | 次数 |", "| --- | --- | ---: |"]
    lines += [f"| {draft} | {text} | {n} |" for (draft, text), n in sorted(counts.items())]
    if missing:
        lines.append(f"\n{missing} 条回答的 trace 中没有问题文字，未计入。")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="live.json 或其所在批次目录")
    parser.add_argument("--tally", action="store_true", help="只输出问题类别计数，引文替换为“…”")
    parser.add_argument("--output", type=Path, help="写入文件；默认打印")
    args = parser.parse_args()
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in reports(args.paths)]
    show = tally if args.tally else render
    text = "\n\n".join(show(path, report) for path, report in loaded)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
