"""Astrology output validation against calculated entities, including cited transits."""

import re

from common.facts import section_texts
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


DATE = re.compile(r"(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})日?|(?<!\d)(\d{1,2})月(\d{1,2})日")


def date_value(text, match, limit):
    """(MM-DD or YYYY-MM-DD, written as UTC) for one date match; labels end at ``limit``."""
    year, month, day, short_month, short_day = match.groups()
    value = (
        f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        if year
        else f"{int(short_month):02d}-{int(short_day):02d}"
    )
    before = text[max(0, match.start() - 18) : match.start()]
    after = text[match.end() : min(limit, match.end() + 12)]
    labels = re.findall(r"UTC|当地|北京时间", before)
    utc = (labels[-1] == "UTC" if labels else False) or bool(re.match(r"\s*[（(]?UTC", after))
    return value, utc


def preceding_event_date(text, position):
    dates = list(DATE.finditer(text[:position]))
    return date_value(text, dates[-1], position) if dates else None


def public_parts(reading):
    return [
        reading.summary,
        *section_texts(reading),
        *[e.reading for e in reading.evidence],
        *reading.advice,
        reading.closing,
        *reading.resonances,
        *[t.how_to_read for t in reading.tensions],
        *[side for t in reading.tensions for side in t.sides],
        *[t.period + " " + t.note for t in reading.timeline],
        *reading.followups,
        reading.safety.note,
    ]


def validate_output(reading, state):
    daily = state.get("daily_result") or {}
    natal = state.get("natal_result") or daily.get("natal") or {}
    positions = {p["body_zh"]: p for p in natal.get("planets", [])}
    # Daily fortune events are exact transits too; validate them like compute_transits.
    events = (state.get("transit_result") or {}).get("events", []) + daily.get("events", [])
    interpretations = (state.get("transit_result") or {}).get("interpretations", []) + daily.get(
        "interpretations", []
    )
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
        assertions = list(aspect_assertions(text))
        for position, source, target, aspect in assertions:
            when = preceding_event_date(text, position)
            is_transit = bool(cited or temporal or when or "行运" in text)
            if not is_transit:
                if not natal_aspect(natal, source, target, aspect):
                    return "本命行星相位与本次计算不符"
                continue
            matching = same_event([cited] if cited else events, source, target, aspect)
            if not matching:
                return "行运星、本命星与相位须匹配同一计算事件"
            if when and not on_date(matching, when):
                return "行运日期与所述相位不符，不能编造或混用UTC与当地日期"
        if cited and not assertions:
            when = preceding_event_date(text, len(text))
            if when and not on_date([cited], when):
                return "行运日期与引用事件不符"
        when = trailing_event_date(text, assertions)
        if when and matching and not on_date(matching, when):
            return "行运日期与所述相位不符，不能编造或混用UTC与当地日期"
        error = orb_error(text, matching)
        if error:
            return error
    for title, body, refs in section_parts(reading):
        error = check_section(title, body, refs, event_refs, events, natal)
        if error:
            return error
    return None


# A date-only sentence speaks about the event under discussion when it names the aspect itself.
EVENT_DATE_CONTEXT = re.compile(r"相位|行运|精确|容许度")


def trailing_event_date(text, assertions):
    """A date written after the last relation of a sentence about that relation.

    "木星拱太阳，精确日期是11月12日" dates the relation before it. Only a date that names the
    aspect itself (相位/行运/精确/容许度) is bound, so "…，10月8日寒露后换月" is not.
    """
    if not assertions:
        return None
    last = max(position for position, *_ in assertions)
    tail = text[last:]
    if not EVENT_DATE_CONTEXT.search(tail):
        return None
    return preceding_event_date(tail, len(tail))


def natal_aspect(natal, source, target, aspect) -> bool:
    return any(
        {a["a"], a["b"]} == {source, target} and a["type"] == aspect
        for a in natal.get("aspects", [])
    )


def same_event(events, source, target, aspect):
    return [
        e
        for e in events
        if e["transit_body"] == source and e["natal_body"] == target and e["aspect"] == aspect
    ]


def on_date(events, when) -> bool:
    day, utc = when
    key = "exact_utc" if utc else "exact_date"
    return any(e[key][:10].endswith(day) for e in events)


def orb_error(text, matching):
    for orb in re.findall(r"(?:容许度|残差)\s*(?:为|是|约|:|：)?\s*(\d+(?:\.\d+)?)", text):
        if matching and not any(
            abs(float(orb) - e["orb_deg"]) <= 0.01 or abs(float(orb) - e["allowed_orb_deg"]) <= 0.01
            for e in matching
        ):
            return "行运容许度与本次计算不符"
    return None


def section_parts(reading):
    """(title, body, ref_ids) for each analysis layer; the closing is a layer without refs."""
    parts = [(s.title, s.body, list(s.ref_ids)) for s in getattr(reading, "sections", [])]
    if getattr(reading, "closing", ""):
        parts.append(("", reading.closing, []))
    return parts


def bound_dates(clause, assertions):
    """Pair each relation of one clause with the dates written for it.

    A date before a relation (back to the previous relation) dates it, and dates after the
    last relation date the last one: "11月5日木星拱太阳" and "木星拱太阳在11月5日精确" both
    bind 11月5日 to the relation. Clauses are checked separately, so in "木星拱太阳在11月5日
    精确，土星刑月亮在11月20日精确" each date stays with its own relation.
    """
    dates = [(m.start(), date_value(clause, m, len(clause))) for m in DATE.finditer(clause)]
    starts = sorted({item[0] for item in assertions})
    for item in assertions:
        index = starts.index(item[0])
        low = starts[index - 1] if index else -1
        last = index + 1 == len(starts)
        yield item, [when for at, when in dates if low < at < item[0] or (last and at > item[0])]


def check_section(title, body, refs, event_refs, events, natal):
    """Check one analysis layer against the transit events it cites, clause by clause.

    The layer's ref_ids bind its relations the way an evidence ref binds one item: a relation
    must match one of the cited events, and its dates and orb must be that event's. A title
    such as “行运木星拱本命太阳” sets the transit context for the body. A clause that only
    dates “这一相位” (相位/行运/精确/容许度) is checked against the relation matched last.
    """
    cited = [event_refs[ref] for ref in refs if ref in event_refs]
    transit_layer = bool(cited) or "行运" in title
    pool = cited or events
    current = []
    sentences = [title, *re.split(r"[。；;！!？?\n]", body)]
    for sentence in (normalize_positions(s) for s in sentences if s.strip()):
        said_transit = "行运" in sentence
        for clause in (c for c in re.split(r"[，,：:]", sentence) if c.strip()):
            assertions = list(aspect_assertions(clause))
            for (_, source, target, aspect), dates in bound_dates(clause, assertions):
                explicit = bool(dates or said_transit)
                natal_ok = natal_aspect(natal, source, target, aspect)
                if not (explicit or transit_layer):
                    if not natal_ok:
                        return "本命行星相位与本次计算不符"
                    continue
                found = same_event(pool, source, target, aspect)
                if not found:
                    # A natal relation may sit in a transit layer when the sentence does not
                    # say it is a transit.
                    if natal_ok and not explicit:
                        continue
                    return (
                        "段落中的行运相位须匹配本段ref_ids引用的计算事件"
                        if cited
                        else "行运星、本命星与相位须匹配同一计算事件"
                    )
                if any(not on_date(found, when) for when in dates):
                    return "行运日期与所述相位不符，不能编造或混用UTC与当地日期"
                current = found
            if not assertions and (current or cited) and EVENT_DATE_CONTEXT.search(clause):
                for match in DATE.finditer(clause):
                    if not on_date(current or cited, date_value(clause, match, len(clause))):
                        return "行运日期与引用事件不符"
            error = orb_error(clause, current or cited)
            if error:
                return error
    return None
