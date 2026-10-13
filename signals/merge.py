"""Cross-system merge: resonance and tension between systems, computed in code.

Signals are grouped by horizon first and by theme second; different horizons never offset
each other (a long-term trait is not overturned by one card). Timing signals are compared
only where their real date intervals intersect, so a solar-term month is aligned with a
transit date by instants, not by a "November" label.

Within one group each system gets a strength-weighted mean valence. Two systems with
opposite directions whose strongest agreeing signals both reach ``tension_strength`` form a
tension; two or more systems in the same direction form a resonance. User weights only
change the combined valence of a group, never whether a tension exists, so a preference
cannot hide a disagreement.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_RULE = {
    "system": "merge",
    "version": 3,
    "direction_threshold": 0.05,
    "tension_strength": 0.4,
    "resonance_strength": 0.3,
    "weight_bounds": [0.5, 2.0],
    "max_refs_per_side": 3,
    "theme_labels": {
        "career": "事业",
        "relationship": "感情关系",
        "self": "自我状态",
        "finance": "财务",
    },
    "system_labels": {
        "astro": "占星",
        "bazi": "八字",
        "tarot": "塔罗",
        "name": "姓名",
        "dream": "解梦",
    },
}
HORIZON_LABELS = {"trait": "长期倾向", "timing": "时段", "moment": "当下", "psyche": "心理"}
DIRECTION_LABELS = {1: "偏正向", -1: "偏负向", 0: "中性"}
NEUTRAL = 1e-9
MAX_WINDOWS_SHOWN = 5


def fingerprint(signals: list[dict]) -> str:
    """Stable identity of a signal set, used to tell whether a merge is still current."""
    keys = sorted((s["ref_id"], s["theme"], s["valence"], s["strength"]) for s in signals)
    return hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).hexdigest()[:16]


def interval(timeframe: str | None, tz: str) -> tuple[datetime, datetime] | None:
    """Half-open instant interval of a signal timeframe; None means the whole reading range."""
    if not timeframe:
        return None
    zone = ZoneInfo(tz)

    def point(text: str, end: bool) -> datetime:
        if len(text) == 10:
            day = date.fromisoformat(text) + timedelta(days=1 if end else 0)
            return datetime.combine(day, time(0), zone)
        value = datetime.fromisoformat(text)
        return value if value.tzinfo else value.replace(tzinfo=zone)

    if "/" in timeframe:
        start, end = timeframe.split("/", 1)
        return point(start, False), point(end, len(end) == 10)
    return point(timeframe, False), point(timeframe, True)


def window_label(start: datetime, end: datetime, tz: str) -> str:
    zone = ZoneInfo(tz)
    first = start.astimezone(zone)
    last = (end - timedelta(microseconds=1)).astimezone(zone)

    def show(value: datetime) -> str:
        midnight = value.time() == time(0) or value.time() == time(23, 59, 59, 999999)
        return value.date().isoformat() if midnight else value.strftime("%Y-%m-%d %H:%M")

    head, tail = show(first), show(last)
    return head if head == tail else f"{head}/{tail}"


def side(system: str, signals: list[dict], rule: dict) -> dict:
    """One system's view inside a group: strength-weighted direction and the refs behind it."""
    # An exact 0 in theme_map means "no directional content", not "balanced": it must not
    # dilute the directional facts of the same system.
    weighted = [s for s in signals if s["strength"] > 0 and abs(s["valence"]) > NEUTRAL]
    total = sum(s["strength"] for s in weighted)
    valence = sum(s["strength"] * s["valence"] for s in weighted) / total if total else 0.0
    threshold = rule["direction_threshold"]
    direction = 0 if abs(valence) < threshold else (1 if valence > 0 else -1)
    agreeing = sorted(
        (s for s in weighted if direction and s["valence"] * direction >= threshold),
        key=lambda s: (-s["strength"] * abs(s["valence"]), s["ref_id"]),
    )
    keywords = []
    for signal in agreeing:
        keywords.extend(k for k in signal.get("keywords", []) if k not in keywords)
    return dict(
        system=system,
        label=rule["system_labels"].get(system, system),
        valence=round(valence, 4),
        direction=direction,
        strength=round(max((s["strength"] for s in agreeing), default=0.0), 4),
        refs=list(dict.fromkeys(s["ref_id"] for s in agreeing))[: rule["max_refs_per_side"]],
        keywords=keywords[:4],
        reviewed=all(s.get("reviewed", False) for s in agreeing),
    )


def classify(sides: list[dict], rule: dict) -> str | None:
    strong = {
        d: [s for s in sides if s["direction"] == d and s["strength"] >= rule["tension_strength"]]
        for d in (1, -1)
    }
    if strong[1] and strong[-1]:
        return "tension"
    for d in (1, -1):
        agreeing = [
            s for s in sides if s["direction"] == d and s["strength"] >= rule["resonance_strength"]
        ]
        opposed = [s for s in sides if s["direction"] == -d]
        if len(agreeing) >= 2 and not opposed:
            return "resonance"
    return None


def side_text(entry: dict) -> str:
    words = "、".join(entry["keywords"]) or "无明显关键词"
    return f"{entry['system']}: {DIRECTION_LABELS[entry['direction']]}（{words}）"


def segments(signals: list[dict], tz: str) -> list[tuple[datetime | None, datetime | None, list]]:
    """Split timing signals at every interval boundary; each piece lists the signals covering it."""
    spans = [(interval(s.get("timeframe"), tz), s) for s in signals]
    if all(span is None for span, _ in spans):
        return [(None, None, signals)]
    bounds = sorted({p for span, _ in spans if span for p in span})
    pieces = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        covering = [s for span, s in spans if span is None or (span[0] < end and start < span[1])]
        if covering:
            pieces.append((start, end, covering))
    return pieces


SIGN = {1: "+", -1: "-"}


def fold(pieces: list[dict], applied: dict, rule: dict, tz: str) -> tuple[list[dict], list[dict]]:
    """Aggregate the per-piece sides of one window by duration.

    Directions are identical across the pieces (that is why they were folded); valence is the
    duration-weighted mean, strength the maximum, ``reviewed`` only if every piece was
    reviewed. Each piece's own numbers are kept in ``segments`` for the saved table.
    """

    def duration(piece):
        if piece["start"] is None:
            return 1.0
        # Same-ZoneInfo subtraction uses wall-clock time, losing DST's 23/25-hour days.
        return (piece["end"].astimezone(UTC) - piece["start"].astimezone(UTC)).total_seconds()

    total = sum(duration(p) for p in pieces)
    folded = []
    for index, first in enumerate(pieces[0]["sides"]):
        column = [p["sides"][index] for p in pieces]
        refs = list(dict.fromkeys(r for s in column for r in s["refs"]))
        words = list(dict.fromkeys(k for s in column for k in s["keywords"]))
        folded.append(
            dict(
                first,
                valence=round(
                    sum(duration(p) * s["valence"] for p, s in zip(pieces, column, strict=True))
                    / total,
                    4,
                ),
                strength=max(s["strength"] for s in column),
                refs=refs[: rule["max_refs_per_side"]],
                keywords=words[:4],
                reviewed=all(s["reviewed"] for s in column),
            )
        )
    segments_out = []
    if len(pieces) > 1:
        for piece in pieces:
            weight = sum(applied[s["system"]] for s in piece["sides"])
            segments_out.append(
                dict(
                    window=window_label(piece["start"], piece["end"], tz),
                    valences={s["system"]: s["valence"] for s in piece["sides"]},
                    combined_valence=round(
                        sum(applied[s["system"]] * s["valence"] for s in piece["sides"]) / weight,
                        4,
                    ),
                )
            )
    return folded, segments_out


def merge_signals(
    signals: list[dict],
    rule: dict | None = None,
    weights: dict[str, float] | None = None,
    tz: str = "Asia/Shanghai",
) -> dict:
    rule = {**DEFAULT_RULE, **(rule or {})}
    low, high = rule["weight_bounds"]
    systems = sorted({s["system"] for s in signals})
    applied = {
        system: min(high, max(low, float((weights or {}).get(system, 1.0)))) for system in systems
    }
    groups = []
    by_key: dict[tuple[str, str], list[dict]] = {}
    for signal in signals:
        by_key.setdefault((signal["horizon"], signal["theme"]), []).append(signal)
    for (horizon, theme), members in sorted(by_key.items()):
        if len({s["system"] for s in members}) < 2:
            continue
        pieces = segments(members, tz) if horizon == "timing" else [(None, None, members)]
        previous = None
        for start, end, covering in pieces:
            per_system: dict[str, list[dict]] = {}
            for signal in covering:
                per_system.setdefault(signal["system"], []).append(signal)
            if len(per_system) < 2:
                previous = None
                continue
            sides = [side(system, items, rule) for system, items in sorted(per_system.items())]
            kind = classify(sides, rule)
            signature = (kind, tuple((s["system"], s["direction"]) for s in sides))
            piece = dict(start=start, end=end, sides=sides)
            # Adjacent pieces with the same verdict and directions are one window; their
            # numbers are kept per piece and aggregated by duration below.
            if previous and previous["signature"] == signature and previous["end"] == start:
                previous["end"] = end
                previous["pieces"].append(piece)
                continue
            previous = dict(
                horizon=horizon,
                theme=theme,
                start=start,
                end=end,
                kind=kind,
                pieces=[piece],
                signature=signature,
            )
            groups.append(previous)
    items: dict[tuple, dict] = {}
    for group in groups:
        if group["kind"] is None:
            continue
        sides, segments_out = fold(group["pieces"], applied, rule, tz)
        total = sum(applied[s["system"]] for s in sides)
        combined = sum(applied[s["system"]] * s["valence"] for s in sides) / total
        active = [s for s in sides if s["direction"]]
        # One item per direction pattern: windows where the directions are reversed (astro
        # positive here, negative there) are separate items, so every window listed under an
        # item really has that item's sides.
        pattern = tuple((s["system"], s["direction"]) for s in active)
        key = (group["kind"], group["horizon"], group["theme"], pattern)
        item = items.setdefault(
            key,
            dict(
                id=f"{group['kind']}:{group['horizon']}:{group['theme']}:"
                + "/".join(f"{system}{SIGN[d]}" for system, d in pattern),
                kind=group["kind"],
                horizon=group["horizon"],
                horizon_label=HORIZON_LABELS.get(group["horizon"], group["horizon"]),
                theme=group["theme"],
                theme_label=rule["theme_labels"].get(group["theme"], group["theme"]),
                pattern={system: d for system, d in pattern},
                windows=[],
            ),
        )
        item["windows"].append(
            dict(
                window=window_label(group["start"], group["end"], tz) if group["start"] else None,
                sides=sides,
                side_texts=[side_text(s) for s in active],
                combined_valence=round(combined, 4),
                # The weaker side bounds how clear the disagreement or agreement is.
                clarity=round(min(s["strength"] for s in active), 4),
                segments=segments_out,
            )
        )
    tensions, resonances = [], []
    for item in items.values():
        windows = item["windows"]
        refs: dict[str, list[str]] = {}
        keywords: dict[str, list[str]] = {}
        strength: dict[str, float] = {}
        for window in windows:
            for entry in window["sides"]:
                if entry["direction"]:
                    system = entry["system"]
                    merged = refs.get(system, []) + entry["refs"]
                    refs[system] = list(dict.fromkeys(merged))[: rule["max_refs_per_side"]]
                    words = keywords.get(system, []) + entry["keywords"]
                    keywords[system] = list(dict.fromkeys(words))[:4]
                    strength[system] = max(strength.get(system, 0.0), entry["strength"])
        summary_sides = [
            dict(system=system, direction=item["pattern"][system], keywords=keywords[system])
            for system in sorted(item["pattern"])
        ]
        item.update(
            systems=sorted(refs),
            refs=refs,
            side_texts=[side_text(s) for s in summary_sides],
            strength=strength,
        )
        if item["kind"] == "tension":
            tensions.append(item)
        else:
            item["confidence"] = "high" if len(item["pattern"]) >= 3 else "medium"
            resonances.append(item)
    return dict(
        merge_version=rule["version"],
        signal_fingerprint=fingerprint(signals),
        systems=systems,
        weights=applied,
        weighted=any(value != 1.0 for value in applied.values()),
        tz=tz,
        tensions=tensions,
        resonances=resonances,
        compared_groups=len(groups),
    )


def model_view(merged: dict) -> dict:
    """Compact projection for the orchestrator: what to disclose, not every number."""

    def item(entry):
        windows = [w["window"] for w in entry["windows"] if w["window"]]
        view = dict(
            id=entry["id"],
            theme=entry["theme"],
            theme_label=entry["theme_label"],
            horizon=entry["horizon"],
            sides=entry["side_texts"],
            refs=entry["refs"],
        )
        if windows:
            # Every window listed here has exactly the directions in ``sides``.
            view["windows"] = windows[:MAX_WINDOWS_SHOWN]
            view["window_count"] = len(windows)
        if "confidence" in entry:
            view["confidence"] = entry["confidence"]
        return view

    return dict(
        systems=merged["systems"],
        weights=merged["weights"],
        tensions=[item(t) for t in merged["tensions"]],
        resonances=[item(r) for r in merged["resonances"]],
        note="每条tension都必须写进submit_reading.tensions：theme用此处theme，sides分别写明两边体系怎么说，"
        "how_to_read说明如何同时看待；timeline只用windows中的实际日期。同一主题在不同日期方向相反时"
        "是两条tension，各自写明对应日期，不能互相套用。不能只讲好听的一边。",
    )


def date_forms(label: str) -> set[str]:
    """Ways a window's start date may be written: 2026-11-03, 11-03, 11月3日, 11月03日."""
    day = date.fromisoformat(label[:10])
    return {
        day.isoformat(),
        day.strftime("%m-%d"),
        f"{day.month}月{day.day}日",
        f"{day.month}月{day.day:02d}日",
    }


def undisclosed(merged: dict, reading) -> list[dict]:
    """Tensions the reading does not disclose with both sides.

    A tension is disclosed when some entry in ``reading.tensions`` names its theme (code or
    Chinese label), mentions every opposing system (code or label) across its sides and says
    how to read it. When the same theme has tensions in opposite directions on different
    dates, a theme alone cannot tell them apart: the entry must also name one of that
    tension's dates.
    """
    labels = {**DEFAULT_RULE["system_labels"]}
    tensions = merged.get("tensions", [])
    patterns: dict[tuple[str, str], int] = {}
    for tension in tensions:
        key = (tension["horizon"], tension["theme"])
        patterns[key] = patterns.get(key, 0) + 1
    missing = []
    for tension in tensions:
        names = {tension["theme"], tension["theme_label"]}
        dates = set()
        if patterns[(tension["horizon"], tension["theme"])] > 1:
            for window in tension["windows"]:
                if window["window"]:
                    dates |= date_forms(window["window"])
        disclosed = False
        for entry in reading.tensions:
            if not any(name and name in entry.theme for name in names):
                continue
            text = " ".join(entry.sides)
            if len(entry.sides) < 2 or not entry.how_to_read.strip():
                continue
            if not all(
                system in text or labels.get(system, system) in text
                for system in tension["systems"]
            ):
                continue
            visible_text = " ".join((entry.theme, text, entry.how_to_read))
            if dates and not any(d in visible_text for d in dates):
                continue
            disclosed = True
        if not disclosed:
            missing.append(tension)
    return missing
