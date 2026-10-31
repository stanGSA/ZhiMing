"""Why the judge failed answers of a live run: the failed dimensions, its reasons, the answer.

Reads the live.json reports of scripts.live_week23 on the machine that ran them and never
calls a model. The published summaries leave out the judge's reasons and the answers
(scripts/p1_report.PRIVATE), so this is where they can be read. Nothing is published: the
output goes to the terminal or to a file the owner names.

Each no_fabricated_facts failure is also sorted by the judge's reason into the two metrics of
根因整改实施计划 §5: a verifiable fact the code computes (事实类) or narrative only the writing
prompt can prevent (叙述类). Only reasons labelled no_fabricated_facts are read, and a keyword the
reason rules out ("没有新增牌名") is no evidence. A failure without such a reason, or whose reason
names both kinds or neither, is 待复核: the owner decides it, and --reviewed takes those
decisions (an answer may be both kinds; it is still one failure). The counts say how many
submitted answers were scored; with missing scores or open reviews they are marked incomplete
and the narrative share is a range, never a confirmed zero. With --counts-only the output is
the counts alone, with no question, reason or answer, so it can be published with the run.

    python -m scripts.quality_reasons reports/p1-tarot/Tarot-pipeline --answers
    python -m scripts.quality_reasons reports/p1-tarot-r2/Tarot-pipeline --counts-only \
        --reviewed reports/p1-tarot-r2/fabrication-reviewed.yaml

A --reviewed file maps a batch to its decided answers, each by id and the run number shown in
the report ("第2次" is #2): {"Tarot-single": {"tarot_exam_rhythm#2": ["叙述类"]}}, YAML or JSON.
"""

import argparse
import json
import re
from pathlib import Path

import yaml

DIMENSIONS = ("direct_answer", "time_consistent", "supported_conclusion", "no_fabricated_facts")
FABRICATION = "no_fabricated_facts"
FACT, NARRATION, PENDING = "事实类", "叙述类", "待复核"
# Facts code computes and renders: cards and their positions, 干支 and pillars, houses, signs and
# aspects, dates, birth data, references.
VERIFIABLE = re.compile(
    r"牌名|正位|逆位|牌位|未抽到|没有抽到|没抽到|干支|十神|日主|[年月日时]柱|宫位|落座|相位|"
    r"起运|大运|流年|流月|流日|时辰|节气|出生(?:信息|时间|日期|地)|ref_id|编号"
)
# What only the writing prompt prevents: scenarios stated as the user's experience or state,
# foretold events, and card lore the fact sheet does not give.
NARRATIVE = re.compile(
    r"经历|场景|已经发生|预言|必然发生|具体事件|画面|图案|人物形象|元素|数字学|星象对应|故事|"
    r"用户(?:已经|正在|长期|一直)|断言用户|用户的现状"
)
# A keyword the reason rules out is no evidence: "没有新增牌名", "未编造宫位", "牌名无误".
RULED_OUT_BEFORE = re.compile(
    r"(?:没有|并没有|没|未|无|不是|并非)(?:新增|编造|捏造|写错|出现|提到|涉及|改动)?$"
)
RULED_OUT_AFTER = re.compile(r"(?:均|都|也)?(?:无误|正确|一致|准确|没有问题|无问题)")
CLAUSE = re.compile(r"[，,。；;：:！!？?\s]")


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


def evidence(pattern: re.Pattern, text: str) -> bool:
    """Whether ``text`` names ``pattern`` as an error, not only to rule it out."""
    for match in pattern.finditer(text):
        before = CLAUSE.split(text[: match.start()])[-1]
        if RULED_OUT_BEFORE.search(before) or RULED_OUT_AFTER.match(text, match.end()):
            continue
        return True
    return False


def scored(row: dict) -> bool:
    """Whether the judge scored this answer on every dimension."""
    review = row.get("quality_review") or {}
    return review.get("scored", True) is not False and all(
        type(review.get(key)) is bool for key in DIMENSIONS
    )


def fabrication_kind(row: dict) -> str | None:
    """事实类, 叙述类 or 待复核 for a no_fabricated_facts failure; None for any other row."""
    review = row.get("quality_review") or {}
    if not scored(row) or review.get(FABRICATION) is not False:
        return None
    # The reasons cover every dimension; only those labelled with this one decide.
    about = [str(reason) for reason in review.get("reasons") or [] if FABRICATION in str(reason)]
    if not about:
        return PENDING
    text = " ".join(about)
    fact, story = evidence(VERIFIABLE, text), evidence(NARRATIVE, text)
    if fact == story:
        return PENDING
    return FACT if fact else NARRATION


def answer_key(row: dict) -> str:
    """How a --reviewed file names an answer: its id and the run number of the report."""
    return f"{row['id']}#{row.get('repeat', 0) + 1}"


def load_reviewed(path: Path | None) -> dict:
    """{batch: {answer: [kinds]}} from a YAML or JSON file of the owner's decisions."""
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for batch, answers in data.items():
        for key, kinds in (answers or {}).items():
            if not isinstance(kinds, list) or not set(kinds) <= {FACT, NARRATION}:
                raise ValueError(f"{batch} {key}：判定须为由“{FACT}”“{NARRATION}”组成的列表")
    return data


def counts(report: dict, reviewed: dict | None = None) -> dict:
    """The no_fabricated_facts failures of the submitted answers, by kind.

    An answer decided as both kinds counts once in each kind and once among the failures.
    """
    reviewed = reviewed or {}
    submitted = [r for r in report.get("results", []) if r.get("status") == "submit_reading"]
    graded = [r for r in submitted if scored(r)]
    failures = [r for r in graded if r["quality_review"][FABRICATION] is False]
    decided, pending = [], 0
    for row in failures:
        if answer_key(row) in reviewed:
            decided.append(set(reviewed[answer_key(row)]))
        elif (kind := fabrication_kind(row)) == PENDING:
            pending += 1
        else:
            decided.append({kind})
    return {
        "submitted": len(submitted),
        "scored": len(graded),
        "unscored": len(submitted) - len(graded),
        "failures": len(failures),
        "fact": sum(FACT in kinds for kinds in decided),
        "narrative": sum(NARRATION in kinds for kinds in decided),
        "pending": pending,
    }


TABLE_HEAD = [
    "| 批次 | 已提交 | 已评分 | 未评分 | 编造失败 | 事实类 | 叙述类 | 待复核 | 叙述类占已提交 | 结果 |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
]


def counts_row(name: str, report: dict, reviewed: dict | None = None) -> str:
    n = counts(report, reviewed)
    open_ = n["pending"] + n["unscored"]
    if not n["submitted"]:
        share = "—"
    elif not n["scored"]:
        share = "待定（未评分）"
    elif open_:
        # Every open answer could still be narrative fabrication, or none of them.
        low, high = n["narrative"] / n["submitted"], (n["narrative"] + open_) / n["submitted"]
        share = f"{low:.1%}–{high:.1%}"
    else:
        share = f"{n['narrative'] / n['submitted']:.1%}"
    missing = [f"待复核 {n['pending']}"] * bool(n["pending"]) + [f"未评分 {n['unscored']}"] * bool(
        n["unscored"]
    )
    state = f"不完整：{'、'.join(missing)}" if missing else "完整"
    return (
        f"| {name} | {n['submitted']} | {n['scored']} | {n['unscored']} | {n['failures']} | "
        f"{n['fact']} | {n['narrative']} | {n['pending']} | {share} | {state} |"
    )


def run_name(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.parent.name}"


def render(path: Path, report: dict, *, answers: bool, reviewed: dict | None = None) -> str:
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
        counts_row(run_name(path), report, reviewed),
        "",
    ]
    for row, dims in failing:
        lines += [f"### {row['id']} · 第{row.get('repeat', 0) + 1}次", ""]
        lines.append(f"- 未通过：{'、'.join(dims)}")
        if answer_key(row) in (reviewed or {}):
            decided = "、".join(reviewed[answer_key(row)]) or "两类都不是"
            lines.append(f"- 编造分类：{decided}（人工判定，{answer_key(row)}）")
        elif kind := fabrication_kind(row):
            lines.append(f"- 编造分类：{kind}（{answer_key(row)}）")
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
    parser.add_argument(
        "--reviewed", type=Path, help="负责人对待复核答案的判定（YAML 或 JSON），计入计数表"
    )
    parser.add_argument("--output", type=Path, help="写入文件；默认打印")
    args = parser.parse_args()
    decisions = load_reviewed(args.reviewed)
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in reports(args.paths)]

    def reviewed(path: Path) -> dict:
        return decisions.get(path.parent.parent.name) or {}

    if args.counts_only:
        rows = (counts_row(run_name(path), r, reviewed(path)) for path, r in loaded)
        text = "\n".join([*TABLE_HEAD, *rows])
    else:
        text = "\n".join(
            render(path, report, answers=args.answers, reviewed=reviewed(path))
            for path, report in loaded
        )
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
