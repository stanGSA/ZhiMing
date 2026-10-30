"""Code writes the facts: placeholders become the calculation's own text (plan §3.3).

The result is the argument set of submit_reading, citing R-numbers exactly as a model would, so
the Guard, validate_reading and the store treat it like any other submission.
"""

from __future__ import annotations

import re

from common.validation import HIGH_RISK
from pipeline.compose import Draft

PLACEHOLDER = re.compile(r"[{｛]{1,2}\s*(R\d+)\s*[}｝]{1,2}")
# Safety notes are written by code, by the kind of risk the question carries.
SAFETY_NOTES = (
    (
        re.compile(r"投资|股票|基金|借贷|借钱|期货|理财|积蓄"),
        "这不构成投资建议；涉及大额资金请结合自身财务状况，必要时咨询持牌专业人士。",
    ),
    (
        re.compile(r"疾病|癌|诊断|停药|治疗|健康"),
        "这不能代替诊断；如有身体不适，请及时就医，以医生的诊断为准。",
    ),
    (re.compile(r"法律|诉讼|判刑"), "这不构成法律意见；具体问题请咨询专业律师。"),
    (
        re.compile(r"死亡|寿命"),
        "生死与寿命不作预测；如有健康方面的担忧，请及时就医或联系信任的人。",
    ),
)


def expand(text: str, facts: dict) -> tuple[str, list[str], list[str]]:
    """(rendered text, R-numbers used, unknown R-numbers)."""
    used, unknown = [], []

    def replace(match):
        alias = match[1]
        if alias not in facts:
            unknown.append(alias)
            return match[0]
        used.append(alias)
        return facts[alias].text

    return PLACEHOLDER.sub(replace, text or ""), used, unknown


def safety_for(question: str) -> dict:
    if not HIGH_RISK.search(question):
        return {"flag": False, "note": ""}
    note = next((note for pattern, note in SAFETY_NOTES if pattern.search(question)), None)
    return {"flag": True, "note": note or SAFETY_NOTES[0][1]}


def reading_args(
    draft: Draft, facts: list, *, question_type: str, question: str
) -> tuple[dict, list[str], list[str]]:
    """(submit_reading arguments, problems, rendered texts to check)."""
    by_alias = {fact.alias: fact for fact in facts}
    problems: list[str] = []
    cited: list[str] = []

    def render(text: str, where: str) -> str:
        rendered, used, unknown = expand(text, by_alias)
        cited.extend(used)
        for alias in dict.fromkeys(unknown):
            problems.append(f"{where}引用了不存在的编号{alias}")
        return rendered

    summary = render(draft.summary, "摘要")
    sections = []
    for index, section in enumerate(draft.sections, 1):
        title = render(section.title, f"第{index}层标题")
        body = render(section.body, f"第{index}层正文")
        refs = list(dict.fromkeys([*section.refs, *placeholders_in(section)]))
        for alias in refs:
            if alias not in by_alias:
                problems.append(f"第{index}层【引用】中的{alias}不在事实表里")
        refs = [alias for alias in refs if alias in by_alias]
        cited.extend(refs)
        sections.append({"title": title, "body": body, "ref_ids": refs})
    advice = [render(item, "建议") for item in draft.advice]
    closing = render(draft.closing, "收尾")
    for alias in draft.refs:
        if alias in by_alias:
            cited.append(alias)
        else:
            problems.append(f"【引用】中的{alias}不在事实表里")
    evidence = list(dict.fromkeys(cited)) or [fact.alias for fact in facts]
    args = {
        "question_type": question_type,
        "systems_used": sorted({fact.ref.split(":", 1)[0] for fact in facts}),
        "summary": summary,
        "sections": sections,
        "evidence": [{"ref_id": alias} for alias in evidence],
        "advice": advice,
        "closing": closing,
        # Capped and worded from the meanings' review status by normalize_reading.
        "confidence": {"level": "medium", "reason": ""},
        "safety": safety_for(question),
    }
    if draft.verdict:
        args["verdict"] = draft.verdict
    texts = [summary, *(part for s in sections for part in (s["title"], s["body"])), *advice]
    return args, problems, [*texts, closing]


def placeholders_in(section) -> list[str]:
    """R-numbers written as placeholders in a section; they are its references too."""
    return PLACEHOLDER.findall(f"{section.title}\n{section.body}")
