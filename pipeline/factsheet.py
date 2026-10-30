"""The facts a reading may cite, numbered the way the model sees them (plan §3.1 ④).

Each fact carries the text code renders for it. The model writes {{R2}}; the reader sees
"【正义】逆位". Nothing here comes from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from harness.refs import short

# The knowledge base closes almost every card meaning with this sentence. It is a disclaimer,
# which the writer must not repeat, and it puts 必然 in front of a writer told not to use it.
CAVEAT = re.compile(r"这是象征性反思线索[^。]*。?")


@dataclass(frozen=True)
class Fact:
    alias: str  # the R-number the model cites
    ref: str  # the calculation's full reference
    label: str  # where it sits, e.g. the spread position
    text: str  # what code renders in place of {{alias}}
    line: str  # how the fact sheet presents it to the model


def orientation(card: dict) -> str:
    return "逆位" if card["reversed"] else "正位"


def card_ref(card: dict, reading_id: str) -> str:
    # Readings saved before cards carried their reference are numbered the same way.
    return card.get("ref_id") or f"tarot:{reading_id}:pos{card['pos']}:{card['meaning_key']}"


def shorten(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def tarot_facts(session) -> list[Fact]:
    state = session.state
    tarot = state.get("tarot_result") or {}
    facts = []
    for card in tarot.get("cards", []):
        ref = card_ref(card, tarot.get("reading_id") or state.get("active_reading_id"))
        if ref not in state.get("allowed_refs", ()):
            continue
        alias = short(ref, session)
        meaning = card.get("meaning") or {}
        text = f"【{card['name']}】{orientation(card)}"
        keywords = "、".join(meaning.get("keywords") or [])
        general = shorten(CAVEAT.sub("", meaning.get("text") or ""), 160)
        # “第二张牌” in a follow-up names the card by its place in the draw.
        line = (
            f"{alias}｜第{card['pos']}张·{card['label']}位｜{text}｜关键词：{keywords or '无'}"
            f"｜一般含义：{general or '无'}"
        )
        facts.append(Fact(alias, ref, card["label"], text, line))
    return facts
