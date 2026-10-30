"""The one writing call and its plain-text format (plan §3.3).

The model writes plain text with markers, not a long JSON tool call: unescaped quotes and
truncated JSON cannot occur, and code turns the markers into the Reading the store keeps.
Facts are written as {{R2}} placeholders and rendered by code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TAROT_SYSTEM = """你是知命的塔罗解读撰写者。牌已经由程序抽好，事实表列出了本次每张牌的编号、牌位、牌名方向和一般含义。你只负责把牌面写成给用户看的白话解读。

【事实规则】
- 提到任何一张牌时只写它的编号占位符，例如{{R2}}，程序会替换成“【牌名】正位/逆位”。不要自己写牌名、正逆位，不要提事实表之外的牌。
- 牌位用事实表里的名称，例如“现在位的{{R2}}”。
- 一般含义只作参考，要结合用户的问题和牌阵前后承接来讲。趋势用“倾向、容易、往往”，不写“一定、必然、注定”。

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：运势类从偏顺、平稳、偏压力、起伏中选；适不适合类从适合、暂不适合、有条件适合中选；二选一给出暂定倾向A或B并写现实条件；只求提示就直接给提示。第二句再说一个主要前提或另一选择的代价。
- 分层通常2-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说生活中的表现，再说依据哪几张牌，最后说怎么应对。
- 建议2-4条，每条写成“短标签：具体做法”。收尾一句。
- 涉及健康、投资、法律或生死时，不给确定性结论，不建议停药，不鼓励把积蓄全部押上；安全提示由程序添加。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。
- 追问时只回答所问的牌或问题，摘要加1-2层即可，不重新抽牌。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 偏顺/平稳/偏压力/起伏/适合/暂不适合/有条件适合/倾向A/倾向B/描述 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""

VERDICTS = {
    "偏顺": "favorable",
    "平稳": "steady",
    "偏压力": "pressured",
    "起伏": "volatile",
    "适合": "suitable",
    "暂不适合": "not_now",
    "有条件适合": "conditional",
    "倾向A": "prefer_a",
    "更倾向A": "prefer_a",
    "倾向B": "prefer_b",
    "更倾向B": "prefer_b",
    "描述": "describe",
}
MARKER = re.compile(r"^\s*【(表态|摘要|分层|引用|建议|收尾)】\s*(.*)$")
ALIAS = re.compile(r"R\d+")
# The limits of common.schemas.Reading, checked here so a long draft is repaired, not rejected.
LIMITS = {"summary": 200, "title": 60, "body": 1200, "closing": 200, "sections": 6}


@dataclass
class Section:
    title: str
    body: str
    refs: list[str] = field(default_factory=list)


@dataclass
class Draft:
    verdict: str | None = None
    summary: str = ""
    sections: list[Section] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    closing: str = ""
    refs: list[str] = field(default_factory=list)  # 【引用】 given before any section


def fact_sheet(facts) -> str:
    return "\n".join(fact.line for fact in facts)


def tarot_messages(question: str, spread_note: str, facts, *, extra: str = "", prior=None):
    """The writing request; ``prior`` holds the saved reading a follow-up asks about."""
    if prior is None:
        lines = [f"用户的问题：{question}"]
        if extra:
            lines.append(f"用户补充：{extra}")
        lines.append(f"牌阵：{spread_note}")
    else:
        lines = [
            "这是对一次已有塔罗解读的追问，不重新抽牌。",
            f"原来的问题：{prior['question']}",
            f"原解读摘要：{prior['summary']}",
            f"用户现在的追问：{question}",
            f"牌阵：{spread_note}",
        ]
    lines += ["事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": TAROT_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def repair_messages(messages: list[dict], draft: str, problems: list[str], facts) -> list[dict]:
    listed = "\n".join(f"{i}. {problem}" for i, problem in enumerate(problems, 1))
    aliases = "、".join(fact.alias for fact in facts)
    return [
        *messages,
        {"role": "assistant", "content": draft},
        {
            "role": "user",
            "content": f"上一稿有这些问题，请修改后重新输出完整的标记文本，格式不变：\n{listed}\n"
            f"可引用的编号只有：{aliases}。",
        },
    ]


def parse(text: str, *, sections_required: bool = True) -> tuple[Draft, list[str]]:
    """The draft and every format problem at once, so one repair can fix them all."""
    text = re.sub(r"^\s*```[a-zA-Z]*\s*$", "", text or "", flags=re.M)
    draft, problems = Draft(), []
    current = None
    for line in text.splitlines():
        match = MARKER.match(line)
        if match:
            current, rest = match[1], match[2].strip()
            if current == "表态":
                key = re.sub(r"\s", "", rest).strip("。")
                draft.verdict = VERDICTS.get(key) or (key if key in VERDICTS.values() else None)
            elif current == "摘要":
                draft.summary = rest
            elif current == "分层":
                draft.sections.append(Section(rest, ""))
            elif current == "引用":
                refs = ALIAS.findall(rest)
                (draft.sections[-1].refs if draft.sections else draft.refs).extend(refs)
            elif current == "建议" and rest:
                draft.advice.append(rest.lstrip("-·•* ").strip())
            elif current == "收尾":
                draft.closing = rest
            continue
        line = line.strip()
        if not line or current is None:
            continue
        if current == "摘要":
            draft.summary = f"{draft.summary}{line}" if draft.summary else line
        elif current == "分层" and draft.sections:
            section = draft.sections[-1]
            section.body = f"{section.body}\n{line}" if section.body else line
        elif current == "引用":
            (draft.sections[-1].refs if draft.sections else draft.refs).extend(ALIAS.findall(line))
        elif current == "建议":
            item = re.sub(r"^(?:[-·•*]|\d+[.、）)])\s*", "", line).strip()
            if item:
                draft.advice.append(item)
        elif current == "收尾":
            draft.closing = f"{draft.closing}{line}"
    if not draft.summary:
        problems.append("格式：缺少【摘要】")
    elif len(draft.summary) > LIMITS["summary"]:
        problems.append(f"摘要有{len(draft.summary)}字，须不超过200字")
    if sections_required and not draft.sections:
        problems.append("格式：至少要有一个【分层】（标题一行，正文另起一行）")
    if len(draft.sections) > LIMITS["sections"]:
        problems.append("分层最多6层")
    for index, section in enumerate(draft.sections, 1):
        if not section.title:
            problems.append(f"第{index}层缺少标题（写在【分层】同一行）")
        elif len(section.title) > LIMITS["title"]:
            problems.append(f"第{index}层标题过长，须不超过60字")
        if not section.body:
            problems.append(f"第{index}层缺少正文（标题下一行起）")
        elif len(section.body) > LIMITS["body"]:
            problems.append(f"第{index}层正文过长，须不超过1200字")
    if len(draft.closing) > LIMITS["closing"]:
        problems.append("收尾须不超过200字")
    return draft, problems
