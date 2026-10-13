import re

from common.facts import public_texts
from plugins.tarot.catalogue import DECK


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
        opposite = "正位" if card["reversed"] else "逆位"
        if re.search(rf"{re.escape(card['name'])}(?:】|」|》)?\s*{opposite}", evidence.reading):
            return f"牌面方向错误，应为{orientation}"
    # Any visible text: a drawn card may only be named with an orientation it was drawn in.
    for part in public_texts(reading):
        for name, found in orientations.items():
            for said in re.findall(rf"{re.escape(name)}(?:】|」|》)?\s*(正位|逆位)", part):
                if said not in found:
                    return f"牌面方向错误：{name}应为{'、'.join(sorted(found))}"
    return None
