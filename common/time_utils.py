from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class NeedsInput(ValueError):
    def __init__(self, code: str, question: str, candidates=None):
        super().__init__(question)
        self.code, self.question, self.candidates = code, question, candidates or []

    def result(self):
        return dict(
            status="needs_input", code=self.code, question=self.question, candidates=self.candidates
        )


def local_instant(local: str, tz: str, fold: int | None = None) -> datetime:
    try:
        civil = datetime.fromisoformat(local)
        zone = ZoneInfo(tz)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise NeedsInput(
            "invalid_datetime", "请确认有效的公历日期、出生时间和 IANA 时区。"
        ) from exc
    if civil.tzinfo is not None:
        raise NeedsInput("offset_local_time", "请提供无偏移的当地钟表时间，时区单独填写。")
    valid = {}
    for f in (0, 1):
        utc = civil.replace(tzinfo=zone, fold=f).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == civil:
            valid[f] = utc
    if not valid:
        raise NeedsInput(
            "nonexistent_local_time",
            "该当地时间因夏令时跳时不存在，请确认原始钟表时间及夏令时记录。",
        )
    if len(set(valid.values())) == 2 and fold is None:
        raise NeedsInput(
            "ambiguous_local_time",
            "该当地时间出现两次，请确认回拨前（fold=0）还是回拨后（fold=1）。",
            [dict(fold=f, utc=t.isoformat()) for f, t in valid.items()],
        )
    return valid[fold if fold is not None else 0]


def date_range(start: str, end: str, tz: str, max_days: int = 366):
    """Date inputs include the end day; datetime inputs use [start, end)."""

    def instant(value):
        try:
            parsed = datetime.fromisoformat(value)
            zone = ZoneInfo(tz)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise NeedsInput("invalid_datetime", "请确认日期范围和IANA时区。") from exc
        if parsed.tzinfo is None:
            return local_instant(value, tz)
        if parsed.astimezone(zone).replace(tzinfo=None) != parsed.replace(tzinfo=None):
            raise NeedsInput("offset_timezone_mismatch", "日期偏移与指定IANA时区的历史规则不一致。")
        return parsed.astimezone(UTC)

    a = instant(start)
    b = instant(end)
    if len(end) == 10:
        b = local_instant((datetime.fromisoformat(end) + timedelta(days=1)).isoformat(), tz)
    if not a < b or (b - a).total_seconds() > max_days * 86400:
        raise NeedsInput("invalid_range", f"请提供递增日期范围，最多 {max_days} 天。")
    return a, b
