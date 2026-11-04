"""What the pipeline's checks found in each draft of a live run, read from its traces.

The published summaries keep only how many problems each draft had (scripts/live_test.py
pipeline_record). The texts are traced as the ``problems`` stage (pipeline/runner.py), and this
reads them back on the machine that ran the batch; it never calls a model. Older traces show
no texts, but saved readings may still hold them in the workspace database's pipeline_json.

Without --tally the output names each answer's problems and quotes fragments of the drafts,
with all candidate sentences holding each quoted word when the trace records the draft, so
it stays local like scripts.quality_reasons. With --tally it is one table of the problem kinds
per batch, using fixed labels only. Unknown problems use a generic label, so names and other
unquoted source text cannot enter the published categories.

    python -m scripts.pipeline_problems reports/p2-r2/Dream-pipeline
    python -m scripts.pipeline_problems reports/p2-r2/Dream-pipeline --tally
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from scripts.quality_reasons import reports, run_name

# Never return a transformed original error as a public category: validators include
# unquoted names, dates and other source text. Only these fixed labels leave the machine.
KINDS = (
    (r"不在事实表里，只能解读事实表里的意象", "事实表外的梦境意象"),
    (r"未在词典中命中，只能说明未收录", "未收录的梦境意象"),
    (r"不是本次命中的意象", "未命中的梦境意象"),
    (r"解梦只提供心理层面的线索", "解梦预兆或时间表"),
    (r"的(?:天格|人格|地格|外格|总格)\d+与本次计算不符", "姓名五格数值错误"),
    (r"的数理\d+与本次计算不符", "姓名数理错误"),
    (r"的总笔画与本次计算不符", "姓名总笔画错误"),
    (r"的三才配置与本次计算不符", "姓名三才配置错误"),
    (r"笔画与本次计算不符|笔画不能串用", "姓名单字笔画错误"),
    (r"有多个姓名时.*须写明是哪个名字", "姓名归属不明确"),
    (r"当天流日的十神是", "流日十神错误"),
    (r"不是当天的流日，也不是本命的干支", "流日干支错误"),
    (r"本命日主是", "本命日主错误"),
    (r"当天流日五行是", "流日五行错误"),
    (r"当天日期是", "当天日期错误"),
    (r"牌面方向错误|正逆位", "塔罗牌面方向错误"),
    (r"位是【.*正文写成了", "塔罗牌位错误"),
    (r"没有抽到|正文提到未抽出的牌", "未抽出的塔罗牌"),
    (r"编号|【引用】|ref_id", "引用编号错误"),
    (r"格式：|摘要.*字|层.*(?:标题|正文)|输出上限被截断", "稿件格式或长度错误"),
    (r"不能劝阻就医", "劝阻就医"),
    (r"停药|确定性结果", "确定性结果或用药指令"),
    (r"确定性说法|健康、投资或生死的确定性结论", "确定性断言"),
    (r"本轮token预算已用尽", "预算用尽"),
)


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


def draft_texts(row: dict) -> list[str]:
    """Each refused draft as checked, falling back to raw text in older traces."""
    path = Path(row.get("trace") or "")
    if not path.is_file():
        return []
    events = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return [
        e.get("rendered_text") or e.get("text") or ""
        for e in events
        if e.get("stage") == "problems"
    ]


QUOTE = re.compile(r"“([^”]+)”")
SENTENCES = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


# Name problems quote nothing (“赵杰的数理1与本次计算不符”): the grid word they name is the cue.
NAMED_GRID = re.compile(r"(天格|人格|地格|外格|总格|数理|三才|总笔画)")


def sources(problem: str, text: str) -> list[str]:
    """All candidate sentences in draft order; a word match does not locate the violation."""
    words = QUOTE.findall(problem) or NAMED_GRID.findall(problem)
    return list(
        dict.fromkeys(
            sentence.strip()
            for sentence in SENTENCES.findall(text)
            if any(word in sentence for word in words)
        )
    )


def kind(problem: str) -> str:
    """A fixed category, never any of the draft's or the user's own words."""
    return next((label for pattern, label in KINDS if re.search(pattern, problem)), "其他校验问题")


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
        texts = draft_texts(row)
        for number, problems in enumerate(found, 1):
            text = texts[number - 1] if number <= len(texts) else ""
            for problem in problems:
                lines.append(f"  - 第{number}稿：{problem}")
                lines += [f"    - 候选原句：{sentence}" for sentence in sources(problem, text)]
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
    parser.add_argument("--tally", action="store_true", help="只输出固定问题类别计数，不含原文")
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
