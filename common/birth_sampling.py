"""Stratified birth time periods, DST-safe sampling, and client-side redaction.

This module sits purely on the web boundary: the agent runtime, plugins, and LLM only ever
see a concrete birth clock time, while browser views, readings, and exports only ever show
the user's chosen time period name.
"""

from __future__ import annotations

import copy
import re
import secrets
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from common.time_utils import NeedsInput, local_instant

TimePeriod = Literal[
    "",
    "early_morning",
    "morning_early",
    "forenoon",
    "noon",
    "afternoon",
    "dusk",
    "evening",
    "late_night",
    "unknown",
]

# Ordered period definitions: (key, Chinese display label, start_minute, end_minute inclusive).
TIME_PERIOD_SPECS: tuple[tuple[str, str, int, int], ...] = (
    ("early_morning", "凌晨", 0, 4 * 60 + 59),
    ("morning_early", "早晨", 5 * 60, 7 * 60 + 59),
    ("forenoon", "上午", 8 * 60, 10 * 60 + 59),
    ("noon", "中午", 11 * 60, 13 * 60 + 59),
    ("afternoon", "下午", 14 * 60, 16 * 60 + 59),
    ("dusk", "傍晚", 17 * 60, 18 * 60 + 59),
    ("evening", "晚间", 19 * 60, 21 * 60 + 59),
    ("late_night", "深夜", 22 * 60, 23 * 60 + 59),
    ("unknown", "完全不记得", 0, 23 * 60 + 59),
)

TIME_PERIODS: dict[str, tuple[str, int, int]] = {
    key: (label, start, end) for key, label, start, end in TIME_PERIOD_SPECS
}

PERIOD_LABELS: dict[str, str] = {key: label for key, label, _, _ in TIME_PERIOD_SPECS}
LABEL_TO_PERIOD: dict[str, str] = {label: key for key, label, _, _ in TIME_PERIOD_SPECS}

_ALL_PERIOD_PREFIXES = "凌晨|早上|早晨|上午|中午|下午|傍晚|晚上|晚间|深夜|午夜|半夜"
_PM_PREFIXES = "下午|傍晚|晚上|晚间|深夜"
_MIDNIGHT_PREFIXES = "凌晨|午夜|半夜"
_PUBLIC_PERIOD_EVIDENCE = re.compile(
    r"公历\s+\d{4}-\d{2}-\d{2}\s+("
    + "|".join(re.escape(label) for label in PERIOD_LABELS.values())
    + r")"
)

_CN_DIGITS = "零一二三四五六七八九"


def period_label(period: str | None) -> str:
    """Pure Chinese period name without any numeric clock range."""
    if period and period in PERIOD_LABELS:
        return PERIOD_LABELS[period]
    return PERIOD_LABELS["unknown"]


def _format_minute(total_minutes: int) -> str:
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def _effective_tz(tz: str | None) -> str:
    if tz:
        try:
            ZoneInfo(tz)
            return tz
        except ZoneInfoNotFoundError:
            pass
    return "Asia/Shanghai"


def is_valid_clock_minute(birth_date: date, hhmm: str, tz: str | None = None) -> bool:
    """True when (birth_date, hhmm) maps to a single unambiguous instant in tz."""
    zone_name = _effective_tz(tz)
    try:
        local_instant(f"{birth_date.isoformat()}T{hhmm}:00", zone_name, fold=None)
        return True
    except NeedsInput:
        return False


def _day_has_dst_transition(birth_date: date, zone_name: str) -> bool:
    """Fast O(1) probe to detect whether any DST offset shift occurs near birth_date."""
    zone = ZoneInfo(zone_name)
    prev_day = birth_date - timedelta(days=1)
    next_day = birth_date + timedelta(days=1)
    probes = (
        datetime(prev_day.year, prev_day.month, prev_day.day, 23, 0, tzinfo=zone, fold=0),
        datetime(birth_date.year, birth_date.month, birth_date.day, 0, 0, tzinfo=zone, fold=0),
        datetime(birth_date.year, birth_date.month, birth_date.day, 0, 0, tzinfo=zone, fold=1),
        datetime(birth_date.year, birth_date.month, birth_date.day, 12, 0, tzinfo=zone, fold=0),
        datetime(birth_date.year, birth_date.month, birth_date.day, 12, 0, tzinfo=zone, fold=1),
        datetime(birth_date.year, birth_date.month, birth_date.day, 23, 59, tzinfo=zone, fold=0),
        datetime(birth_date.year, birth_date.month, birth_date.day, 23, 59, tzinfo=zone, fold=1),
        datetime(next_day.year, next_day.month, next_day.day, 1, 0, tzinfo=zone, fold=0),
    )
    offsets = {dt.utcoffset() for dt in probes}
    return len(offsets) > 1


def sample_birth_time(
    birth_date: date,
    period: str,
    tz: str | None = None,
    chooser: Callable[[Sequence[str]], str] = secrets.choice,
) -> str:
    """Randomly sample one DST-valid HH:MM inside the requested period."""
    key = period if period in TIME_PERIODS else "unknown"
    _, start_min, end_min = TIME_PERIODS[key]
    zone_name = _effective_tz(tz)
    candidates = [_format_minute(m) for m in range(start_min, end_min + 1)]
    if _day_has_dst_transition(birth_date, zone_name):
        valid = [hhmm for hhmm in candidates if is_valid_clock_minute(birth_date, hhmm, zone_name)]
        if not valid:
            # Extreme fallback: search the entire day if an entire window fell in a shift.
            valid = [
                _format_minute(m)
                for m in range(0, 24 * 60)
                if is_valid_clock_minute(birth_date, _format_minute(m), zone_name)
            ]
        candidates = valid or ["12:00"]
    return chooser(candidates)


def _cn_number_variants(value: int) -> list[str]:
    if value == 0:
        return ["零", "〇"]
    if value < 10:
        variants = [_CN_DIGITS[value]]
        if value == 2:
            variants.append("两")
        return variants
    tens, ones = divmod(value, 10)
    if tens == 1:
        return ["十" + ("" if ones == 0 else _CN_DIGITS[ones])]
    return [_CN_DIGITS[tens] + "十" + ("" if ones == 0 else _CN_DIGITS[ones])]


def _minute_cn_variants(minute: int) -> list[str]:
    variants = [f"{minute:02d}"]
    if minute < 10:
        variants.extend([str(minute), f"零{minute}", f"零{_CN_DIGITS[minute]}"])
    variants.extend(_cn_number_variants(minute))
    if minute == 30:
        variants.append("半")
    elif minute == 15:
        variants.extend(["一刻", "1刻"])
    elif minute == 45:
        variants.extend(["三刻", "3刻"])
    # Longer alternatives first so regex matches greedy phrases like "三十七" before shorter forms.
    return sorted(set(variants), key=len, reverse=True)


def _hour_patterns(hour: int) -> str:
    variants = [f"{hour:02d}", str(hour), *_cn_number_variants(hour)]
    return "|".join(re.escape(v) for v in sorted(set(variants), key=len, reverse=True))


def redact_sampled_time_text(text: str, sampled_hhmm: str | None, period: str = "unknown") -> str:
    """Scrub a sampled HH:MM (and Chinese clock variants) from user-facing prose."""
    if not text or not sampled_hhmm or not re.fullmatch(r"\d{2}:\d{2}", sampled_hhmm):
        return text
    hour, minute = map(int, sampled_hhmm.split(":"))
    label = period_label(period)
    replacement = "" if period == "unknown" else label

    h24_digit = f"0?{hour}" if hour < 10 else str(hour)
    h24_all = _hour_patterns(hour)
    mm = f"{minute:02d}"

    patterns: list[re.Pattern[str]] = []

    # 1. 24-hour colon format (e.g. 09:37, 9:37, 上午 09:37, 09:37:00), protecting 23:00/0:00 换日.
    patterns.append(
        re.compile(
            rf"(?<!换日·)(?<!换日 · )(?:(?:{_ALL_PERIOD_PREFIXES})\s*)?"
            rf"(?<!\d){h24_digit}[:：]{mm}(?::00)?(?!\d)(?!\s*换日)"
        )
    )

    # 2. 24-hour Chinese clock format (e.g. 9点37分, 09时37分, 九点半, 9点整).
    if minute != 0:
        bare_date_clock = None
        m_alt = "|".join(re.escape(v) for v in _minute_cn_variants(minute))
        patterns.append(
            re.compile(
                rf"(?:(?:{_ALL_PERIOD_PREFIXES})\s*)?"
                rf"(?<![\d一二两三四五六七八九十])(?:{h24_all})[点时時]\s*(?:{m_alt})分?(?!\d)"
            )
        )
    else:
        patterns.append(
            re.compile(
                rf"(?:(?:{_ALL_PERIOD_PREFIXES})\s*)?"
                rf"(?<![\d一二两三四五六七八九十])(?:{h24_all})[点时時]\s*(?:整|00分?|零零分?)(?!\s*换日)"
            )
        )
        # Bare "X点" immediately after a calendar date (never touch "0点换日" / "23点换日").
        bare_date_clock = re.compile(
            rf"((?:\d{{4}}[-年/.]\d{{1,2}}[-月/.]\d{{1,2}}[日号]?|\d{{1,2}}月\d{{1,2}}[日号]))"
            rf"\s*(?:(?:{_ALL_PERIOD_PREFIXES})\s*)?"
            rf"(?:{h24_all})[点时時](?!\s*换日)(?![\d零〇一二三四五六七八九十半刻整])"
        )

    # 3. 12-hour period-prefixed variants (e.g. 下午3:42 / 下午3点42分 for 15:42; 凌晨12:15 for 00:15).
    if hour == 0 or hour >= 13:
        h12 = 12 if hour == 0 else hour - 12
        prefixes = _MIDNIGHT_PREFIXES if hour == 0 else _PM_PREFIXES
        h12_digit = f"0?{h12}" if h12 < 10 else str(h12)
        h12_all = _hour_patterns(h12)
        patterns.append(
            re.compile(rf"(?:{prefixes})\s*(?<!\d){h12_digit}[:：]{mm}(?::00)?(?!\d)(?!\s*换日)")
        )
        if minute != 0:
            m_alt = "|".join(re.escape(v) for v in _minute_cn_variants(minute))
            patterns.append(
                re.compile(
                    rf"(?:{prefixes})\s*(?<![\d一二两三四五六七八九十])(?:{h12_all})[点时時]\s*(?:{m_alt})分?(?!\d)"
                )
            )
        else:
            patterns.append(
                re.compile(
                    rf"(?:{prefixes})\s*(?<![\d一二两三四五六七八九十])(?:{h12_all})[点时時](?:\s*(?:整|00分?|零零分?))?(?!\s*换日)"
                )
            )

    cleaned = text
    for pattern in patterns:
        cleaned = pattern.sub(replacement, cleaned)
    if bare_date_clock is not None:
        cleaned = bare_date_clock.sub(lambda m: m.group(1) + replacement, cleaned)

    # Remove internal evidence tag if ever copied into prose/history.
    cleaned = cleaned.replace("（出生时间确定）", "").replace("(出生时间确定)", "")

    # Tidy punctuation & adjacent duplicate period labels.
    if replacement:
        escaped = re.escape(replacement)
        cleaned = re.sub(rf"{escaped}(?:\s*{escaped})+", replacement, cleaned)
        cleaned = re.sub(rf"{escaped}\s*[（(]\s*{escaped}\s*[）)]", replacement, cleaned)
    cleaned = re.sub(r"[（(]\s*[）)]", "", cleaned)
    cleaned = re.sub(r"([日号])\s+([，,。；;、）)])", r"\1\2", cleaned)
    cleaned = re.sub(r"(\d{4}-\d{2}-\d{2})\s+([，,。；;、）)])", r"\1\2", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip() if text.strip() == text else cleaned


def _redact_strings(value: Any, sampled_hhmm: str | None, period: str) -> Any:
    if not sampled_hhmm:
        return value
    if isinstance(value, str):
        return redact_sampled_time_text(value, sampled_hhmm, period)
    if isinstance(value, list):
        return [_redact_strings(item, sampled_hhmm, period) for item in value]
    if isinstance(value, dict):
        return {k: _redact_strings(v, sampled_hhmm, period) for k, v in value.items()}
    return value


def _extract_hhmm_from_birth_local(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"[T\s](\d{2}:\d{2})", value)
    return match.group(1) if match else None


def _scrub_chart_result_dict(res: dict[str, Any]) -> None:
    """Remove exact sampled clock time fields from a bazi/astro chart result dict in place."""
    if isinstance(res.get("input"), dict):
        birth_local = res["input"].get("birth_local")
        if isinstance(birth_local, str) and len(birth_local) >= 10:
            res["input"]["birth_local"] = birth_local[:10]
        res["input"]["time_known"] = False
    for key in ("civil_time", "utc", "jd_tt", "jd_ut1", "solar_correction_minutes"):
        if key in res:
            res[key] = None


def sanitize_chart_for_client(
    chart: dict[str, Any] | None,
    public_birth: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a client-safe copy of a /api/chart payload without revealing sampled HH:MM."""
    if chart is None:
        return None
    sanitized = copy.deepcopy(chart)
    sanitized["birth"] = dict(public_birth)
    if public_birth.get("unknown_time") and isinstance(sanitized.get("result"), dict):
        _scrub_chart_result_dict(sanitized["result"])
    return sanitized


def sanitize_calculations_for_client(
    calculations: dict[str, Any] | None,
    public_birth: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(calculations, dict):
        return calculations
    sanitized = copy.deepcopy(calculations)
    if not public_birth.get("unknown_time"):
        return sanitized
    for value in sanitized.values():
        if (
            isinstance(value, dict)
            and isinstance(value.get("input"), dict)
            and "birth_local" in value["input"]
        ):
            _scrub_chart_result_dict(value)
    return sanitized


def _reading_sampled_time(reading: dict[str, Any]) -> str | None:
    context = reading.get("birth_context") or {}
    if isinstance(context, dict) and context.get("_sampled_time"):
        return str(context["_sampled_time"])
    calculations = reading.get("calculations") or {}
    if isinstance(calculations, dict):
        for key in ("bazi_result", "natal_result"):
            item = calculations.get(key)
            if isinstance(item, dict) and isinstance(item.get("input"), dict):
                found = _extract_hhmm_from_birth_local(item["input"].get("birth_local"))
                if found:
                    return found
    return None


def sanitize_reading_for_client(reading: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip private sampling metadata and scrub sampled HH:MM from a reading payload."""
    if reading is None:
        return None
    sanitized = copy.deepcopy(reading)
    sampled_hhmm = _reading_sampled_time(sanitized)
    context = sanitized.get("birth_context")
    public_birth: dict[str, Any] = {}
    if isinstance(context, dict):
        context.pop("_sampled_time", None)
        if isinstance(context.get("birth"), dict):
            public_birth = context["birth"]
    if not public_birth.get("unknown_time"):
        return sanitized
    period = str(public_birth.get("time_period") or "unknown")
    if "calculations" in sanitized:
        sanitized["calculations"] = sanitize_calculations_for_client(
            sanitized["calculations"], public_birth
        )
    if sampled_hhmm:
        for field in ("question", "output", "responses", "specialist_reports", "review_notes"):
            if field in sanitized and sanitized[field] is not None:
                sanitized[field] = _redact_strings(sanitized[field], sampled_hhmm, period)
    return sanitized


def _sanitize_profile_snapshot(
    profile: dict[str, Any],
    *,
    unknown_time: bool,
    period: str,
) -> dict[str, Any]:
    cleaned = copy.deepcopy(profile)
    if not unknown_time:
        return cleaned
    birth_dt = cleaned.get("birth_local_dt")
    if isinstance(birth_dt, str) and len(birth_dt) >= 10:
        cleaned["birth_local_dt"] = birth_dt[:10]
    cleaned["time_known"] = False
    cleaned["time_period"] = period if period in PERIOD_LABELS else "unknown"
    cleaned["time_period_label"] = period_label(period)
    return cleaned


def sanitize_export_for_client(
    payload: dict[str, Any],
    resolved_birth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sanitize a /api/export payload so no sampled HH:MM leaks while keeping period names."""
    sanitized = copy.deepcopy(payload)
    public_birth = sanitized.get("birth") if isinstance(sanitized.get("birth"), dict) else {}
    unknown = bool(public_birth.get("unknown_time"))
    current_period = str(public_birth.get("time_period") or "unknown")

    if unknown and isinstance(sanitized.get("birth"), dict):
        sanitized["birth"]["time"] = ""
        sanitized["birth"]["time_period"] = current_period
        sanitized["birth"]["time_period_label"] = period_label(current_period)

    if isinstance(sanitized.get("profile"), dict) and unknown:
        sanitized["profile"] = _sanitize_profile_snapshot(
            sanitized["profile"], unknown_time=True, period=current_period
        )

    # Collect all known sampled (hhmm, period) pairs for defensive redaction of legacy history entries.
    known_samples: list[tuple[str, str]] = []
    if isinstance(resolved_birth, dict) and resolved_birth.get("resolved_time"):
        known_samples.append(
            (
                str(resolved_birth["resolved_time"]),
                str(resolved_birth.get("time_period") or current_period),
            )
        )

    readings = sanitized.get("readings")
    if isinstance(readings, list):
        clean_readings = []
        for item in readings:
            if isinstance(item, dict):
                ctx = item.get("birth_context") or {}
                if isinstance(ctx, dict) and ctx.get("_sampled_time"):
                    b = ctx.get("birth") if isinstance(ctx.get("birth"), dict) else {}
                    known_samples.append(
                        (
                            str(ctx["_sampled_time"]),
                            str(b.get("time_period") or "unknown"),
                        )
                    )
                clean_readings.append(sanitize_reading_for_client(item))
            else:
                clean_readings.append(item)
        sanitized["readings"] = clean_readings

    history = sanitized.get("profile_history")
    if isinstance(history, list):
        for entry in history:
            if not isinstance(entry, dict):
                continue
            evidence = str(entry.get("evidence") or "")
            matched = _PUBLIC_PERIOD_EVIDENCE.search(evidence)
            if matched and "出生时间确定" not in evidence:
                label = matched.group(1)
                period = LABEL_TO_PERIOD.get(label, "unknown")
                if isinstance(entry.get("profile"), dict):
                    entry["profile"] = _sanitize_profile_snapshot(
                        entry["profile"], unknown_time=True, period=period
                    )
                continue
            # Defensive fallback for any pre-upgrade history entry that recorded a sampled HH:MM.
            for hhmm, period in known_samples:
                if hhmm in evidence or (
                    isinstance(entry.get("profile"), dict)
                    and str(entry["profile"].get("birth_local_dt") or "").endswith(hhmm)
                ):
                    entry["evidence"] = redact_sampled_time_text(evidence, hhmm, period)
                    if isinstance(entry.get("profile"), dict):
                        entry["profile"] = _sanitize_profile_snapshot(
                            entry["profile"], unknown_time=True, period=period
                        )
                    break

    return sanitized
