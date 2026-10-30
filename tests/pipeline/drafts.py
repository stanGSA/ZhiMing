"""Scripted drafts for the pipeline's writing call, shared by its tests and the replays.

A callable draft reads the fact sheet it was given, so a draft can name the drawn cards (or
name them wrongly) without the test knowing the draw in advance.
"""

import copy
import re

from harness.models import ModelResponse

QUESTION = "只用塔罗，抽三张牌帮我看看近期事业状态。"
FACT_LINE = re.compile(r"^(R\d+)｜(.+?)位｜【(.+?)】(正位|逆位)｜", re.M)


class Composer:
    """Returns the scripted drafts in order; a callable draft reads the fact sheet it was given."""

    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.seen = []

    async def chat(self, messages, tools):
        self.seen.append((copy.deepcopy(messages), tools))
        draft = self.drafts.pop(0)
        if isinstance(draft, Exception):
            raise draft
        if callable(draft):
            draft = draft(messages)
        if isinstance(draft, ModelResponse):
            return draft
        return ModelResponse(text=draft, input_tokens=120, output_tokens=60, finish_reason="stop")


def cards_in(messages) -> dict:
    """alias -> (position, card name, orientation), read from the fact sheet."""
    sheet = messages[1]["content"]
    return {m[1]: (m[2], m[3], m[4]) for m in FACT_LINE.finditer(sheet)}


def good(messages) -> str:
    aliases = list(cards_in(messages))
    layers = "\n".join(
        f"【分层】第{i}层：这张牌提醒你的事\n这一层的{{{{{alias}}}}}提示你先理清手头的事，"
        f"再一步步推进，遇到阻力时放慢节奏。\n【引用】{alias}"
        for i, alias in enumerate(aliases, 1)
    )
    return (
        "【表态】平稳\n【摘要】近期事业整体平稳，可以按计划推进。先把手头积压的事理顺，再看新的机会。\n"
        f"{layers}\n【建议】\n- 先理顺：把积压的事列出来逐一处理。\n- 再推进：每周选一件最重要的事推进。\n"
        "【收尾】一步一步来，节奏会越来越顺。"
    )


def followup_answer(messages) -> str:
    second = list(cards_in(messages))[1]
    return (
        f"【表态】描述\n【摘要】第二张牌{{{{{second}}}}}说的是你现在的状态：先稳住，再推进。\n"
        f"【分层】现在位想告诉你的事\n{{{{{second}}}}}在现在位，提示你眼下更需要耐心。\n"
        f"【引用】{second}"
    )


def wrong_orientation(messages) -> str:
    alias, (label, name, side) = list(cards_in(messages).items())[1]
    other = "正位" if side == "逆位" else "逆位"
    return good(messages).replace(
        f"这一层的{{{{{alias}}}}}", f"{label}位是【{name}】{other}，这一层的{{{{{alias}}}}}"
    )


def swapped_positions(messages) -> str:
    aliases = list(cards_in(messages))
    return good(messages).replace(
        f"这一层的{{{{{aliases[0]}}}}}",
        f"过去位是{{{{{aliases[2]}}}}}，这一层的{{{{{aliases[0]}}}}}",
    )


def unknown_refs(messages) -> str:
    """Cites numbers the fact sheet never gave, as the recorded tarot failure chain did."""
    return good(messages).replace("【收尾】", "【引用】R4 R5\n【收尾】")


DRAFTS = {
    "good": good,
    "followup_answer": followup_answer,
    "wrong_orientation": wrong_orientation,
    "swapped_positions": swapped_positions,
    "unknown_refs": unknown_refs,
}
