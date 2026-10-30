"""Replay the drafts a live run refused for certainty wording through today's check.

Reads the traces that the rows of a live.json name (scripts.live_week23 keeps each run's trace
path) on the machine that ran them and never calls a model. Every submit_reading refused as a
certainty claim is rebuilt as a Reading, and its authored texts go through the current
certainty_claim, so a change to the check is measured on the drafts that were really refused.
Only the certainty wording is replayed; the high-risk check's other words (稳赚, 必死…) are not.

    python -m scripts.replay_rejections reports/p1-tarot/Tarot-single reports/p1-tarot/Tarot-pipeline
"""

import argparse
import json
import re
from pathlib import Path

from pydantic import ValidationError

from common.output_policy import CERTAINTY, SENTENCE, authored_texts, certainty_claim
from common.schemas import Reading
from scripts.quality_reasons import reports

REFUSED = re.compile(r"这类确定性说法|确定性结论")


def refused_drafts(trace: Path):
    """(arguments, error) of each certainty refusal of submit_reading in one trace."""
    for line in trace.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") != "tool_result" or event["call"]["name"] != "submit_reading":
            continue
        result = event["result"]
        if not result.get("ok") and REFUSED.search(result.get("error") or ""):
            yield event["call"]["arguments"], result["error"]


def replay(arguments: dict) -> tuple[str | None, list[tuple[str, bool]]]:
    """(the claim today's check finds, each sentence with a certainty word and whether it is
    still refused); the claim is "无法解析" when the draft is not a Reading."""
    try:
        reading = Reading.model_validate(arguments)
    except ValidationError:
        return "无法解析", []
    texts = authored_texts(reading)
    sentences = [
        piece.strip()
        for text in texts
        for piece in SENTENCE.findall(text or "")
        if CERTAINTY.search(piece)
    ]
    return certainty_claim(texts), [(s, bool(certainty_claim([s]))) for s in sentences]


def render(path: Path, report: dict) -> str:
    rows, missing = [], []
    for row in report.get("results", []):
        trace = Path(row.get("trace") or "")
        if not trace.is_file():
            missing.append(row["id"])
            continue
        for arguments, error in refused_drafts(trace):
            rows.append((row, error, *replay(arguments)))
    still = sum(claim is not None for _, _, claim, _ in rows)
    lines = [
        f"## {path.parent.parent.name}/{path.parent.name}",
        "",
        f"因确定性措辞被拒的草稿 {len(rows)} 份，按当前校验仍被拒 {still} 份",
        "",
    ]
    if missing:
        # A count over missing traces would read as a pass.
        lines += [f"**缺少 trace {len(missing)} 条，结果不完整：**{'、'.join(missing)}", ""]
    for row, error, claim, sentences in rows:
        verdict = f"仍拒（{claim}）" if claim else "放行"
        lines += [f"### {row['id']} · 第{row.get('repeat', 0) + 1}次：{verdict}", ""]
        lines.append(f"- 当时的报错：{error}")
        lines += [
            f"- {'仍拒' if refused else '放行'}：{sentence}" for sentence, refused in sentences
        ]
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="live.json 或其所在批次目录")
    parser.add_argument("--output", type=Path, help="写入文件；默认打印")
    args = parser.parse_args()
    text = "\n".join(
        render(path, json.loads(path.read_text(encoding="utf-8"))) for path in reports(args.paths)
    )
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
