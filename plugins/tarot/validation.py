import re

from common.facts import negated_at, public_texts
from plugins.tarot.catalogue import DECK

ORIENTATION_GAP = r"[\s【】「」《》“”\"'（）()]*"
CLAUSE = re.compile(r"[。！？；;\n]")
DRAW_CONTEXT = re.compile(
    r"本次|此次|这次|本轮|今天|今日|每日一牌|这张|抽到|抽出|抽中|翻出|翻到|结果|提示牌|位置"
)
# “这次不是这种情况” denies that a general meaning applies to this draw.
NEGATED_DRAW = re.compile(r"(?:本次|此次|这次|本轮|这张)(?:并)?(?:不是|并非|不属于|不同于?|不适用)")
DEFINITION = re.compile(
    ORIENTATION_GAP
    + r"(?:一般|通常|往往|常常)?(?:是|表示|象征|代表|意味着|的(?:牌义|含义|意思)(?:是|为))"
)


def orientation_error(text: str, name: str, expected: set[str]) -> str | None:
    mentions = list(re.finditer(rf"{re.escape(name)}{ORIENTATION_GAP}(正位|逆位)", text))
    # “本次正义是逆位” names the drawn orientation as clearly as “正义逆位”.
    stated = rf"{re.escape(name)}{ORIENTATION_GAP}(?:是|为){ORIENTATION_GAP}(正位|逆位)"
    has_expected = any(m[1] in expected for m in [*mentions, *re.finditer(stated, text)])
    for mention in mentions:
        # “是正义逆位，不是正义正位” denies the other orientation.
        if mention[1] in expected or negated_at(text, mention.start()):
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
            and not DRAW_CONTEXT.search(NEGATED_DRAW.sub("", clause))
        ):
            continue
        wanted = "、".join(sorted(expected))
        return (
            f"牌面方向错误：{name}本次应为{wanted}；冲突片段“{clause[:120]}”。"
            "请修正该片段中的本次牌面断言；对照释义须明确为一般牌义，勿重新抽牌。"
        )
    return None


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
        explicit = re.search(
            rf"(?:【|「|《){re.escape(name)}(?:】|」|》)|{re.escape(name)}(?:正位|逆位|牌)", text
        )
        # Full minor-arcana names are unambiguous; common major names need card context.
        if (
            explicit or (name.startswith(("权杖", "圣杯", "宝剑", "星币")) and name in text)
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
