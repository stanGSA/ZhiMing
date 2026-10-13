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
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_RULE = {
    "system": "merge",
    "version": 1,
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
            # Adjacent pieces with the same verdict and directions are one window.
            if previous and previous["signature"] == signature and previous["end"] == start:
                previous["end"] = end
                for old, new in zip(previous["sides"], sides, strict=True):
                    old["refs"] = list(dict.fromkeys(old["refs"] + new["refs"]))[
                        : rule["max_refs_per_side"]
                    ]
                    old["strength"] = max(old["strength"], new["strength"])
                    old["keywords"] = list(dict.fromkeys(old["keywords"] + new["keywords"]))[:4]
                continue
            previous = dict(
                horizon=horizon,
                theme=theme,
                start=start,
                end=end,
                kind=kind,
                sides=sides,
                signature=signature,
            )
            groups.append(previous)
    items: dict[tuple[str, str, str], dict] = {}
    for group in groups:
        if group["kind"] is None:
            continue
        sides = group["sides"]
        total = sum(applied[s["system"]] for s in sides)
        combined = sum(applied[s["system"]] * s["valence"] for s in sides) / total
        active = [s for s in sides if s["direction"]]
        item = items.setdefault(
            (group["kind"], group["horizon"], group["theme"]),
            dict(
                id=f"{group['kind']}:{group['horizon']}:{group['theme']}",
                kind=group["kind"],
                horizon=group["horizon"],
                horizon_label=HORIZON_LABELS.get(group["horizon"], group["horizon"]),
                theme=group["theme"],
                theme_label=rule["theme_labels"].get(group["theme"], group["theme"]),
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
            )
        )
    tensions, resonances = [], []
    for item in items.values():
        windows = item["windows"]
        strongest = max(windows, key=lambda w: (w["clarity"], -windows.index(w)))
        refs: dict[str, list[str]] = {}
        for window in windows:
            for entry in window["sides"]:
                if entry["direction"]:
                    merged = refs.get(entry["system"], []) + entry["refs"]
                    refs[entry["system"]] = list(dict.fromkeys(merged))[: rule["max_refs_per_side"]]
        item.update(
            systems=sorted(refs),
            refs=refs,
            side_texts=strongest["side_texts"],
            strongest_window=strongest["window"],
        )
        if item["kind"] == "tension":
            tensions.append(item)
        else:
            item["confidence"] = (
                "high" if any(len(w["side_texts"]) >= 3 for w in windows) else "medium"
            )
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
        "how_to_read说明如何同时看待；timeline只用windows中的实际日期。不能只讲好听的一边。",
    )


def undisclosed(merged: dict, reading) -> list[dict]:
    """Tensions the reading does not disclose with both sides.

    A tension is disclosed when some entry in ``reading.tensions`` names its theme (code or
    Chinese label) and mentions every opposing system (code or label) across its sides.
    """
    labels = {**DEFAULT_RULE["system_labels"]}
    missing = []
    for tension in merged.get("tensions", []):
        names = {tension["theme"], tension["theme_label"]}
        disclosed = False
        for entry in reading.tensions:
            if not any(name and name in entry.theme for name in names):
                continue
            text = " ".join(entry.sides)
            if len(entry.sides) >= 2 and all(
                system in text or labels.get(system, system) in text
                for system in tension["systems"]
            ):
                disclosed = disclosed or bool(entry.how_to_read.strip())
        if not disclosed:
            missing.append(tension)
    return missing
