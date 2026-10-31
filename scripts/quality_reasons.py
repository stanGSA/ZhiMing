"""Why the judge failed answers of a live run: the failed dimensions, its reasons, the answer.

Reads the live.json reports of scripts.live_week23 on the machine that ran them and never
calls a model. The published summaries leave out the judge's reasons and the answers
(scripts/p1_report.PRIVATE), so this is where they can be read. Nothing is published: the
output goes to the terminal or to a file the owner names.

Each no_fabricated_facts failure is also sorted by the judge's reason into the two metrics of
根因整改实施计划 §5: a verifiable fact the code computes (事实类) or narrative only the writing
prompt can prevent (叙述类). A reason that names both kinds or neither is 未分类, for the owner
to judge by hand. With --counts-only the output is the counts alone, with no question, reason
or answer, so it can be published with the run.

    python -m scripts.quality_reasons reports/p1-tarot/Tarot-pipeline --answers
    python -m scripts.quality_reasons reports/p1-tarot-r2/Tarot-pipeline --counts-only
"""

import argparse
import json
import re
from pathlib import Path

DIMENSIONS = ("direct_answer", "time_consistent", "supported_conclusion", "no_fabricated_facts")
FABRICATION = "no_fabricated_facts"
KINDS = ("事实类", "叙述类", "未分类")
# Facts code computes and renders: cards and their positions, 干支 and pillars, houses, signs and
# aspects, dates, birth data, references.
VERIFIABLE = re.compile(
    r"牌名|正位|逆位|牌位|未抽到|没有抽到|没抽到|干支|十神|日主|[年月日时]柱|宫位|落座|相位|"
    r"起运|大运|流年|流月|流日|时辰|节气|出生(?:信息|时间|日期|地)|ref_id|编号"
)
# What only the writing prompt prevents: scenarios stated as the user's experience, foretold
# events, and card lore the fact sheet does not give.
NARRATIVE = re.compile(
    r"经历|场景|已经发生|预言|必然发生|具体事件|画面|图案|人物形象|元素|数字学|星象对应|故事"
)


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


def fabrication_kind(row: dict) -> str | None:
    """事实类, 叙述类 or 未分类 for a no_fabricated_facts failure; None for any other row."""
    review = row.get("quality_review") or {}
    if review.get(FABRICATION) is not False:
        return None
    reasons = [str(reason) for reason in review.get("reasons") or []]
    # The reasons cover every dimension; those about fabrication say so, else all are read.
    about = [r for r in reasons if FABRICATION in r or "编造" in r] or reasons
    text = " ".join(about)
    fact, story = bool(VERIFIABLE.search(text)), bool(NARRATIVE.search(text))
    if fact == story:
        return "未分类"
    return "事实类" if fact else "叙述类"


def counts(report: dict) -> dict:
    """The no_fabricated_facts failures of the submitted answers, by kind."""
    submitted = [r for r in report.get("results", []) if r.get("status") == "submit_reading"]
    kinds = [kind for row in submitted if (kind := fabrication_kind(row))]
    return {"submitted": len(submitted), **{kind: kinds.count(kind) for kind in KINDS}}


TABLE_HEAD = [
    "| 批次 | 已提交 | no_fabricated_facts 失败 | 事实类 | 叙述类 | 未分类 | 叙述类占已提交 |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
]


def counts_row(name: str, report: dict) -> str:
    numbers = counts(report)
    total = sum(numbers[kind] for kind in KINDS)
    share = f"{numbers['叙述类'] / numbers['submitted']:.1%}" if numbers["submitted"] else "—"
    return (
        f"| {name} | {numbers['submitted']} | {total} | {numbers['事实类']} | "
        f"{numbers['叙述类']} | {numbers['未分类']} | {share} |"
    )


def run_name(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.parent.name}"


def render(path: Path, report: dict, *, answers: bool) -> str:
    rows = report.get("results", [])
    failing = [(row, failed(row)) for row in rows]
    failing = [(row, dims) for row, dims in failing if dims]
    lines = [
        f"## {run_name(path)}",
        "",
        f"模式 {report.get('mode')}，评委 {report.get('judge_model')}，"
        f"质量未通过 {len(failing)}/{len(rows)}",
        "",
        *TABLE_HEAD,
        counts_row(run_name(path), report),
        "",
    ]
    for row, dims in failing:
        lines += [f"### {row['id']} · 第{row.get('repeat', 0) + 1}次", ""]
        lines.append(f"- 未通过：{'、'.join(dims)}")
        kind = fabrication_kind(row)
        if kind:
            lines.append(f"- 编造分类：{kind}")
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
    parser.add_argument(
        "--counts-only", action="store_true", help="只输出编造分类的计数表，不含问题、理由和回答"
    )
    parser.add_argument("--output", type=Path, help="写入文件；默认打印")
    args = parser.parse_args()
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in reports(args.paths)]
    if args.counts_only:
        text = "\n".join([*TABLE_HEAD, *(counts_row(run_name(path), r) for path, r in loaded)])
    else:
        text = "\n".join(render(path, report, answers=args.answers) for path, report in loaded)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
