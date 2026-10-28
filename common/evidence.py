"""Render omitted evidence text from the current calculation, without model invention."""


def fact_text(item):
    # The appendix records facts, while interpretation stays in authored sections.
    from plugins.astro.calculator import BODY_ZH, SIGN_ZH, SIGNS

    labels = {
        **BODY_ZH,
        **dict(zip(SIGNS, SIGN_ZH, strict=True)),
        "day_master": "日主",
        "dayun": "起运及首步大运",
        "year": "年柱",
        "month": "月柱",
        "day": "日柱",
        "time": "时柱",
        "conjunction": "合相",
        "opposition": "对分相",
        "square": "四分相",
        "trine": "三分相",
        "sextile": "六分相",
        "zishi": "子时换日",
        "next_day": "23点换日",
        "same_day": "0点换日",
        "gan": "天干",
        "zhi": "地支",
        "symbol": "意象",
        "convention": "约定",
    }
    text = str(item["fact"])
    if text.startswith("transit:"):
        text = "行运（UTC）：" + text[len("transit:") :]
    for token, label in labels.items():
        import re

        text = re.sub(
            rf"(?<![A-Za-z_]){re.escape(token)}(?![A-Za-z_])", lambda _, label=label: label, text
        )
    return text


def calculation_evidence_texts(state):
    """Canonical rendered facts, indexed by their calculation-owned references."""
    texts = {}

    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            ref = value.get("ref_id")
            if ref and value.get("fact"):
                texts.setdefault(ref, fact_text(value))
            elif ref and "reversed" in value and value.get("name"):
                texts[ref] = (
                    f"{value.get('label', '')}：【{value['name']}】{'逆位' if value['reversed'] else '正位'}。"
                )
            for item in value.values():
                collect(item)

    collect(state.get("calculations", {}))
    collect(state.get("tarot_result", {}))
    return {ref: text[:500] for ref, text in texts.items()}


def fill_evidence(reading, state):
    texts = calculation_evidence_texts(state)
    for item in reading.evidence:
        if not item.reading and item.ref_id in texts:
            item.reading = texts[item.ref_id]
    return any(not item.reading for item in reading.evidence)
