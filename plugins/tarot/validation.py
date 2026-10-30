import re

from common.facts import public_texts
from plugins.tarot.catalogue import DECK

ORIENTATION_GAP = r"[\s【】「」《》“”\"'（）()]*"
CLAUSE = re.compile(r"[。！？；;\n]")
DRAW_CONTEXT = re.compile(
    r"本次|此次|这次|本轮|今天|今日|每日一牌|这张|抽到|抽出|抽中|翻出|翻到|结果|提示牌|位置"
)
# Major arcana named like ordinary words. Quoting one is often emphasis (保持「节制」) or another
# system's term (【太阳】四分本命月亮), so a quoted mention needs card context to name a card.
WORD_NAMES = frozenset({"力量", "正义", "节制", "星星", "月亮", "太阳", "审判", "世界", "恋人"})
CARD_USE = re.compile(
    ORIENTATION_GAP + r"(?:正位|逆位|牌|象征|代表|意味|寓意|预示|暗示|提示|提醒|显示|指向|说明|"
    r"的(?:牌义|含义|意思|能量|讯息))"
)
DRAWN = re.compile(r"抽到|抽出|抽中|翻出|翻到|这张|每日一牌|牌面|牌阵|提示牌")
PHRASE = re.compile(r"[。！？；;，,\n]")
DEFINITION = re.compile(
    ORIENTATION_GAP
    + r"(?:一般|通常|往往|常常)?(?:是|表示|象征|代表|意味着|的(?:牌义|含义|意思)(?:是|为))"
)


def orientation_error(text: str, name: str, expected: set[str]) -> str | None:
    mentions = list(re.finditer(rf"{re.escape(name)}{ORIENTATION_GAP}(正位|逆位)", text))
    has_expected = any(m[1] in expected for m in mentions)
    for mention in mentions:
        if mention[1] in expected:
            continue
        start = max((m.end() for m in CLAUSE.finditer(text, 0, mention.start())), default=0)
        end = CLAUSE.search(text, mention.end())
        end = end.start() if end else len(text)
        clause = text[start:end]
        # A named, correct orientation must accompany a general definition of the other
        # orientation. Current-draw assertions remain errors even when phrased as definitions.
        if (
            has_expected
            and DEFINITION.match(text, mention.end())
            and not DRAW_CONTEXT.search(clause)
        ):
            continue
        wanted = "、".join(sorted(expected))
        return (
            f"牌面方向错误：{name}本次应为{wanted}；冲突片段“{clause[:120]}”。"
            "请修正该片段中的本次牌面断言；对照释义须明确为一般牌义，勿重新抽牌。"
        )
    return None


def names_card(text: str, name: str) -> bool:
    """Whether the text names this card rather than a word spelt like it."""
    if re.search(rf"{re.escape(name)}(?:正位|逆位|牌)", text):
        return True
    for quoted in re.finditer(rf"(?:【|「|《){re.escape(name)}(?:】|」|》)", text):
        if name not in WORD_NAMES or CARD_USE.match(text, quoted.end()):
            return True
        start = max((m.end() for m in PHRASE.finditer(text, 0, quoted.start())), default=0)
        end = PHRASE.search(text, quoted.end())
        if DRAWN.search(text, start, end.start() if end else len(text)):
            return True
    return False


def drawn_cards(state) -> list[dict]:
    """Every card of this reading: the draw and the daily fortune's card of the day."""
    cards = list((state.get("tarot_result") or {}).get("cards", []))
    daily = (state.get("daily_result") or {}).get("card")
    if daily:
        cards.append(daily)
    return cards


def validate_output(reading, state):
    text = reading.model_dump_json()
    actual = set(state["facts"])
    for _, name in DECK:
        # Full minor-arcana names are unambiguous; common major names need card context.
        if (
            names_card(text, name)
            or (name.startswith(("权杖", "圣杯", "宝剑", "星币")) and name in text)
        ) and name not in actual:
            return f"正文提到未抽出的牌：{name}"
    cards = drawn_cards(state)
    orientations = {}
    for card in cards:
        orientations.setdefault(card["name"], set()).add("逆位" if card["reversed"] else "正位")
    by_ref = {c["ref_id"]: c for c in cards if c.get("ref_id")}
    for evidence in reading.evidence:
        card = by_ref.get(evidence.ref_id)
        if card is None:
            continue
        orientation = "逆位" if card["reversed"] else "正位"
        error = orientation_error(evidence.reading, card["name"], {orientation})
        if error:
            return error
    # Check every public field, allowing explicit definitions alongside the actual draw.
    for part in public_texts(reading):
        for name, found in orientations.items():
            error = orientation_error(part, name, found)
            if error:
                return error
    return None
