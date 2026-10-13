"""Astrology output validation against calculated entities, including cited transits."""

import re

from common.input_evidence import chinese_number
from plugins.astro.calculator import BODY_ZH, SIGN_ZH

ASPECT_WORDS = {
    "conjunction": r"合相|合本命|合(?=太阳|月亮|水星|金星|火星|木星|土星|天王星|海王星|冥王星)",
    "opposition": r"对分|对冲|冲相|冲本命|冲(?=太阳|月亮|水星|金星|火星|木星|土星|天王星|海王星|冥王星)",
    "trine": r"三分|拱相|拱",
    "square": r"四分|刑相|刑",
    "sextile": r"六分|六合",
}
AXES = {"上升": "asc", "天顶": "mc", "下降": "dsc", "天底": "ic"}
BODY_PATTERN = "|".join([*BODY_ZH.values(), *AXES])


def normalize_positions(text):
    signs = "|".join(SIGN_ZH)
    house = r"(?:第)?[零一二三四五六七八九十\d]+宫"
    # Both “本命太阳狮子第4宫” and “本命狮子第4宫太阳” describe the Sun.
    return re.sub(
        rf"((?:{signs})(?:座)?(?:{house})?|{house})(?:的)?({BODY_PATTERN})",
        lambda m: m[2] + m[1],
        text,
    )


def aspect_assertions(text):
    body = "|".join(BODY_ZH.values())
    aliases = {
        "合相": "conjunction",
        "合": "conjunction",
        "对分": "opposition",
        "对冲": "opposition",
        "冲相": "opposition",
        "冲": "opposition",
        "三分": "trine",
        "拱相": "trine",
        "拱": "trine",
        "四分": "square",
        "刑相": "square",
        "刑": "square",
        "六分": "sextile",
        "六合": "sextile",
    }
    # “冲突” is ordinary prose, whereas “冲/对冲/冲相” assert an aspect.
    aspect = "|".join(word + ("(?!突)" if word == "冲" else "") for word in aliases)
    names = {zh: key for key, zh in BODY_ZH.items()}
    patterns = [
        (
            rf"((?:{body})(?:[、和与](?:{body}))*)\s*(?:分别|呈|形成|构成)?\s*({aspect})(?:相)?\s*(?:本命)?\s*({body})",
            False,
        ),
        (
            rf"({body})\s*(?:与|和)\s*(?:本命)?({body})\s*(?:呈|形成|构成)?\s*({aspect})(?:相)?",
            True,
        ),
    ]
    candidates = []
    for pattern, reversed_order in patterns:
        for match in re.finditer(pattern, text):
            left, relation, right = match.groups()
            if reversed_order:
                relation, right = right, relation
            candidates.append((match.start(), match.end(), left, right, relation))
    # Do not reinterpret the target of “木星合太阳” as the subject of
    # “太阳与水星刑水星” in a coordinated sequence of independent relations.
    end = -1
    for start, stop, left, right, relation in sorted(candidates, key=lambda c: (c[0], -c[1])):
        if start < end:
            continue
        end = stop
        for source in re.findall(body, left):
            yield start, names[source], names[right], aliases[relation]


def preceding_event_date(text, position):
    pattern = r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})日?|(?<!\d)(\d{1,2})月(\d{1,2})日"
    dates = list(re.finditer(pattern, text[:position]))
    if not dates:
        return None
    match = dates[-1]
    year, month, day, short_month, short_day = match.groups()
    value = (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        if year
        else f"{int(short_month):02d}-{int(short_day):02d}"
    )
    before = text[max(0, match.start() - 18) : match.start()]
    after = text[match.end() : min(position, match.end() + 12)]
    labels = re.findall(r"UTC|当地|北京时间", before)
    utc = (labels[-1] == "UTC" if labels else False) or bool(re.match(r"\s*[（(]?UTC", after))
    return value, utc


def public_parts(reading):
    return [
        reading.summary,
        *[e.reading for e in reading.evidence],
        *reading.advice,
        *reading.resonances,
        *[t.how_to_read for t in reading.tensions],
        *[side for t in reading.tensions for side in t.sides],
        *[t.period + " " + t.note for t in reading.timeline],
        *reading.followups,
        reading.safety.note,
    ]


def validate_output(reading, state):
    natal = state.get("natal_result") or {}
    positions = {p["body_zh"]: p for p in natal.get("planets", [])}
    events = (state.get("transit_result") or {}).get("events", [])
    interpretations = (state.get("transit_result") or {}).get("interpretations", [])
    event_refs = {}
    for item in interpretations:
        for event in events:
            key = f"transit:{event['exact_utc']}:{event['transit_body']}:{event['natal_body']}:{event['aspect']}"
            if item["fact"] == key:
                event_refs[item["ref_id"]] = event

    for text in public_parts(reading):
        # Negative statements explain uncertainty and are not affirmative axis claims.
        for sentence in re.split(r"[。；;\n]", normalize_positions(text)):
            negative = bool(
                re.search(r"无法|不能|不使用|不解读|不确定|未知|不提供|不可用", sentence)
            )
            if natal and not natal.get("time_known") and not negative:
                if re.search(
                    r"上升(?!期|空间|趋势|通道|机会|幅度|潜力)|天顶|下降点|天底|(?:第)?[一二三四五六七八九十\d]+宫",
                    sentence,
                ):
                    return "出生时间未知，不能使用宫位或四轴解读"
            matches = list(re.finditer(BODY_PATTERN, sentence))
            for i, body in enumerate(matches):
                tail = sentence[
                    body.end() : matches[i + 1].start() if i + 1 < len(matches) else len(sentence)
                ]
                # A transit body is not a claim about the natal body's position.
                transit_context = bool(re.search(r"行运\s*$", sentence[: body.start()]))
                sign = re.search("|".join(SIGN_ZH), tail[:24])
                houses = re.findall(r"(?:第)?([零一二三四五六七八九十\d]+)宫", tail[:30])
                if transit_context and (sign or houses):
                    return "行运星落座宫位未作为本次事实提供，请仅陈述已计算相位"
                name = body.group()
                if sign:
                    actual = positions.get(name, {}).get("sign_zh")
                    if name in AXES and natal.get("axes"):
                        actual = SIGN_ZH[int(natal["axes"][AXES[name]] // 30)]
                    if actual != sign.group():
                        return "行星落座或四轴与本次计算不符"
                for house in houses:
                    if positions.get(name, {}).get("house") != chinese_number(house):
                        return "宫位不可用或与本次计算不符"

    # Bind each relation independently; a timeline may legitimately contain several events.
    claims = [(e.reading, event_refs.get(e.ref_id), False) for e in reading.evidence]
    claims += [(t.note, None, True) for t in reading.timeline]
    claims += [(reading.summary, None, False)]
    for original, cited, temporal in claims:
        text = normalize_positions(original)
        matching = [cited] if cited else []
        for position, source, target, aspect in aspect_assertions(text):
            when = preceding_event_date(text, position)
            is_transit = bool(cited or temporal or when or "行运" in text)
            if not is_transit:
                if not any(
                    {a["a"], a["b"]} == {source, target} and a["type"] == aspect
                    for a in natal.get("aspects", [])
                ):
                    return "本命行星相位与本次计算不符"
                continue
            matching = [
                e
                for e in ([cited] if cited else events)
                if e["transit_body"] == source
                and e["natal_body"] == target
                and e["aspect"] == aspect
            ]
            if not matching:
                return "行运星、本命星与相位须匹配同一计算事件"
            if when:
                day, utc = when
                key = "exact_utc" if utc else "exact_date"
                if not any(e[key][:10].endswith(day) for e in matching):
                    return "行运日期与所述相位不符，不能编造或混用UTC与当地日期"
        if cited and not list(aspect_assertions(text)):
            when = preceding_event_date(text, len(text))
            if when and not cited["exact_utc" if when[1] else "exact_date"][:10].endswith(when[0]):
                return "行运日期与引用事件不符"
        for orb in re.findall(r"(?:容许度|残差)\s*(?:为|是|约|:|：)?\s*(\d+(?:\.\d+)?)", text):
            if matching and not any(
                abs(float(orb) - e["orb_deg"]) <= 0.01
                or abs(float(orb) - e["allowed_orb_deg"]) <= 0.01
                for e in matching
            ):
                return "行运容许度与本次计算不符"
    return None
