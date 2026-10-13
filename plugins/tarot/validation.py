import re

from plugins.tarot.catalogue import DECK


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
    cards_by_ref = {c["ref_id"]: c for c in (state.get("tarot_result") or {}).get("cards", [])}
    for evidence in reading.evidence:
        if evidence.ref_id not in cards_by_ref:
            continue
        card = cards_by_ref[evidence.ref_id]
        orientation = "逆位" if card["reversed"] else "正位"
        opposite = "正位" if card["reversed"] else "逆位"
        if (
            f"{card['name']}{opposite}" in evidence.reading
            or f"{card['name']}】{opposite}" in evidence.reading
        ):
            return f"牌面方向错误，应为{orientation}"
    return None
