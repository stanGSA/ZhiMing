"""Closed-vocabulary checks the pipeline adds before submit_reading (plan §3.3).

Card names form a closed set of 78. Two wrong facts the output validators let through (P0.2,
docs/verification/p0-接受路径与误拒清单.md) are checked here against the draw: a spread position
paired with another card, and an undrawn card named as drawn without a 【】 or 牌 marker. Common
words that are also card names (力量, 太阳, 世界…) count as cards only when a position or a
marker makes them one, so ordinary prose is not mistaken for a card.

The check runs on the rendered text. A placeholder only fixes a card's name and orientation;
the position around it is still the model's, so "现在位的{{R1}}" with R1 drawn in the past
position renders as "现在位的【月亮】逆位" and is caught here like any written name.
"""

from __future__ import annotations

import re

from common.validation import validate_reading
from plugins.tarot.catalogue import DECK, SPREADS
from plugins.tarot.validation import drawn_cards

NAMES = "|".join(sorted((re.escape(name) for _, name in DECK), key=len, reverse=True))
OPEN, CLOSE = r"[【「《“\"]", r"[】」》”\"]"
POSITION_WORDS = {
    "选 A": r"选\s*A|A\s*(?:选项|方案|位)",
    "选 B": r"选\s*B|B\s*(?:选项|方案|位)",
    "当下提示": r"当下提示|当下",
}
# What may join a position to the card in it: “现在位是/为/的/抽到…”.
JOIN = r"(?:的牌是|的牌为|的|是|为|抽到了?|抽出了?|翻到了?|出现了?|落着|：|:)"
# What may join a card to its position: “【月亮】逆位在/落在/出现在现在位”.
PLACED = r"(?:在|落在|出现在|位于|处在|处于|放在)"
DRAWN = re.compile(rf"(?:抽到|抽出|抽中|翻到|翻出)了?(?:一张)?\s*{OPEN}?(?P<name>{NAMES})")


def position_pattern(label: str) -> re.Pattern:
    words = POSITION_WORDS.get(label, re.escape(label))
    return re.compile(
        rf"(?:{words})(?P<seat>位置?|的位置)?(?:上|里|中|这张牌)?\s*{JOIN}\s*"
        rf"(?P<open>{OPEN}?)(?P<name>{NAMES})(?P<tail>{CLOSE}?\s*(?:正位|逆位|牌)?)"
    )


def placed_pattern(label: str) -> re.Pattern:
    """A card named first and its position after it; the position must say 位."""
    words = POSITION_WORDS.get(label, re.escape(label))
    return re.compile(
        rf"(?P<open>{OPEN}?)(?P<name>{NAMES})(?P<tail>{CLOSE}?\s*(?:正位|逆位|牌)?)\s*"
        rf"{PLACED}\s*(?:{words})(?P<seat>位置?|的位置)"
    )


def tarot_problems(texts: list[str], cards: list[dict]) -> list[str]:
    if not cards:
        return []
    drawn = {card["name"] for card in cards}
    at = {card["label"]: card["name"] for card in cards}
    labels = {label for spread in SPREADS.values() for label in spread}
    problems = []
    for text in texts:
        for label in labels:
            matches = [
                *position_pattern(label).finditer(text),
                *placed_pattern(label).finditer(text),
            ]
            for match in matches:
                marked = bool(match["seat"] or match["open"] or match["tail"].strip())
                if not marked or match["name"] == at.get(label):
                    continue
                if label in at:
                    problems.append(
                        f"{label}位是【{at[label]}】，正文写成了【{match['name']}】：“{match[0]}”"
                    )
                elif match["name"] not in drawn:
                    problems.append(f"本次没有抽到【{match['name']}】：“{match[0]}”")
        for match in DRAWN.finditer(text):
            if match["name"] not in drawn:
                problems.append(f"本次没有抽到【{match['name']}】：“{match[0]}”")
    return list(dict.fromkeys(problems))


def reading_texts(reading) -> list[str]:
    return [
        reading.summary,
        *[part for s in reading.sections for part in (s.title, s.body)],
        *reading.advice,
        reading.closing,
        *[t.note for t in reading.timeline],
    ]


def verify_reading(reading, session) -> str | None:
    """The pipeline's check of a reading: the closed vocabulary, then the output validators."""
    problems = tarot_problems(reading_texts(reading), drawn_cards(session.state))
    if problems:
        return "；".join(problems)
    return validate_reading(reading, session)
