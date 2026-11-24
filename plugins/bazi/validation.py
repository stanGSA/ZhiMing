"""Bazi output checks: every 干支 and pillar must come from this reading's calculations.

Whether the answer repeats a computed fact the question asked for (日主, 起运日期, 首步大运) is
recorded as a warning, not a rejection. 喜用神 and 补五行 advice are allowed as traditional
inference; the prompts ask for them to be argued from the computed chart.
"""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from common.evidence import calculation_evidence_texts
from common.facts import section_texts
from common.output_policy import warn
from harness.models import ValidationMessage

PILLAR_KEYS = {"年": "year", "月": "month", "日": "day", "时": "time"}
PILLAR_CLAIM = re.compile(
    r"(?:(?P<flow>流[年月日时])(?:的?(?P<flow_name>[年月日时])?柱)?|"
    r"(?:(?P<explicit_y>\d{4})年的?年柱|"
    r"(?P<temporal_y>今年|明年|去年)的?年柱|"
    r"(?P<temporal_m>本月|下月|这个月|下个月|上月|上个月)的?月柱|"
    r"(?P<temporal_d>今天|今日|明天|明日|昨天|昨日)的?日柱)|"
    r"(?P<scope>候选|原局|本命|出生|流期)?(?:的)?(?P<name>[年月日时])柱)"
    r"\s*(?:是|为|：|:)?\s*(?P<value>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)


def _resolve_anchor_date(state: dict, bazi: dict, daily: dict) -> date | None:
    for candidate in (
        state.get("calendar_anchor"),
        (bazi.get("dayun") or {}).get("as_of"),
        daily.get("date"),
    ):
        if isinstance(candidate, str) and len(candidate) >= 10:
            try:
                return date.fromisoformat(candidate[:10])
            except ValueError:
                pass
    question = state.get("question") or ""
    m_day = re.search(r"(?:今天|今日)[（(]?\s*(\d{4})[-年/.](\d{1,2})[-月/.](\d{1,2})", question)
    if m_day:
        try:
            return date(*map(int, m_day.groups()))
        except ValueError:
            pass
    m_month = re.search(r"(?:本月|这个月)[（(]?\s*(\d{4})[-年/.](\d{1,2})月?", question)
    if m_month:
        try:
            y, m = map(int, m_month.groups())
            return date(y, m, 15)
        except ValueError:
            pass
    for word, delta in (("今年", 0), ("明年", -1), ("去年", 1)):
        m_year = re.search(rf"{word}[（(]?\s*(\d{{4}})年", question)
        if m_year:
            try:
                return date(int(m_year.group(1)) + delta, 6, 15)
            except ValueError:
                pass
    return None


def _period_local_bounds(period: dict, tz_info: ZoneInfo) -> tuple[datetime, datetime] | None:
    start_utc = period.get("start_utc")
    end_utc = period.get("end_utc")
    if not start_utc or not end_utc:
        return None
    try:
        return (
            datetime.fromisoformat(start_utc).astimezone(tz_info),
            datetime.fromisoformat(end_utc).astimezone(tz_info),
        )
    except ValueError:
        return None


def _overlapping_periods(
    periods: list[dict], tz_info: ZoneInfo, win_start: datetime, win_end: datetime
) -> list[dict]:
    matched = []
    for p in periods:
        bounds = _period_local_bounds(p, tz_info)
        if bounds is not None and bounds[0] < win_end and bounds[1] > win_start:
            matched.append(p)
    return matched


def _temporal_flow_candidates(
    match: re.Match,
    passage: str,
    periods: list[dict],
    daily: dict,
    anchor: date | None,
    tz_info: ZoneInfo,
) -> list[dict]:
    explicit_y = match.group("explicit_y")
    temp_y = match.group("temporal_y")
    temp_m = match.group("temporal_m")
    temp_d = match.group("temporal_d")
    clause = passage[max(0, match.start() - 20) : min(len(passage), match.end() + 20)]

    if explicit_y or temp_y:
        if explicit_y:
            target_year = int(explicit_y)
        elif anchor is not None:
            target_year = anchor.year + {"今年": 0, "明年": 1, "去年": -1}[temp_y]
        else:
            return []
        if re.search(r"立春前|(?<!\d)1月|一月", clause):
            return _overlapping_periods(
                periods,
                tz_info,
                datetime(target_year, 1, 1, tzinfo=tz_info),
                datetime(target_year, 2, 5, 23, 59, 59, tzinfo=tz_info),
            )
        # Main stem-branch year of target_year starts after LiChun (~Feb 4); do not let the
        # previous stem-branch year's Jan tail satisfy "明年" or "今年".
        main = _overlapping_periods(
            periods,
            tz_info,
            datetime(target_year, 2, 10, tzinfo=tz_info),
            datetime(target_year, 12, 31, 23, 59, 59, tzinfo=tz_info),
        )
        if main:
            return main
        if temp_y == "今年" and anchor is not None and anchor < date(target_year, 2, 5):
            return _overlapping_periods(
                periods,
                tz_info,
                datetime(target_year, 1, 1, tzinfo=tz_info),
                datetime(target_year, 2, 5, 23, 59, 59, tzinfo=tz_info),
            )
        return []

    if temp_m:
        if anchor is None:
            return []
        offset = {"本月": 0, "这个月": 0, "下月": 1, "下个月": 1, "上月": -1, "上个月": -1}[temp_m]
        target_year, idx = divmod(anchor.year * 12 + anchor.month - 1 + offset, 12)
        target_month = idx + 1
        # All 12 Jie boundaries fall on the 4th–9th; 10th–28th uniquely identifies that month's main pillar.
        main = _overlapping_periods(
            periods,
            tz_info,
            datetime(target_year, target_month, 10, tzinfo=tz_info),
            datetime(target_year, target_month, 28, 23, 59, 59, tzinfo=tz_info),
        )
        if main:
            return main
        if temp_m in ("本月", "这个月") and anchor.day < 9:
            return _overlapping_periods(
                periods,
                tz_info,
                datetime(target_year, target_month, 1, tzinfo=tz_info),
                datetime(target_year, target_month, 9, 23, 59, 59, tzinfo=tz_info),
            )
        return []

    if temp_d:
        offset = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "昨天": -1, "昨日": -1}[temp_d]
        day_segments = (daily.get("day") or {}).get("segments") or []
        if anchor is None:
            if offset == 0 and day_segments:
                return [{"pillars": {"day": s["pillar"]}} for s in day_segments]
            return []
        target_day = anchor + timedelta(days=offset)
        noon = datetime(target_day.year, target_day.month, target_day.day, 12, 0, tzinfo=tz_info)
        matched = _overlapping_periods(periods, tz_info, noon, noon + timedelta(minutes=1))
        if re.search(r"晚子时|夜子时|23点|23:00", clause):
            late = datetime(
                target_day.year, target_day.month, target_day.day, 23, 30, tzinfo=tz_info
            )
            matched.extend(
                _overlapping_periods(periods, tz_info, late, late + timedelta(minutes=1))
            )
        if offset == 0 and day_segments and daily.get("date") in (None, target_day.isoformat()):
            matched.extend({"pillars": {"day": s["pillar"]}} for s in day_segments)
        return matched

    return []


def validate_output(reading, state):
    parts = [
        reading.summary,
        *section_texts(reading),
        *reading.advice,
        reading.closing,
        *[t.period + " " + t.note for t in reading.timeline],
        *reading.resonances,
        *[t.how_to_read for t in reading.tensions],
        *[side for t in reading.tensions for side in t.sides],
        *[t.theme for t in reading.tensions],
        *reading.followups,
        reading.confidence.reason,
        reading.safety.note,
    ]
    text = " ".join([*parts, *[e.reading for e in reading.evidence]])
    # Exact facts rendered from a matching calculation reference already have a known
    # scope. In particular, period:...:年柱:丁未 is a flow year, not a natal year.
    # A reference alone never exempts model-authored or altered evidence from checks.
    canonical = calculation_evidence_texts(state)
    claims = [
        *parts,
        *[e.reading for e in reading.evidence if canonical.get(e.ref_id) != e.reading],
    ]
    daily = state.get("daily_result") or {}
    bazi = state.get("bazi_result") or daily.get("bazi") or {}
    question = state.get("question", "")
    if bazi:
        if "日主" in question and bazi.get("day_master") and bazi["day_master"] not in text:
            warn(state, "原问题要求说明日主，回答中没有写出")
        dayun = bazi.get("dayun")
        if state.get("response_mode") != "followup" and re.search(
            r"起运日期|起运时间|什么时候.*(?:起运|走大运)|何时.*(?:起运|走大运)", question
        ):
            if dayun:
                date = dayun["start_solar"]
                year, month, day = map(int, date.split("-"))
                if date not in text and f"{year}年{month}月{day}日" not in text:
                    warn(state, "原问题要求起运日期，回答中没有写出计算出的日期")
            elif not re.search(r"未提供|未知|无法|不能|不排", text):
                warn(state, "无法排大运时宜说明原因")
        if (
            state.get("response_mode") != "followup"
            and re.search(r"首步大运|首运|第一步大运", question)
            and dayun
            and dayun["sequence"][0]["ganzhi"] not in text
        ):
            warn(state, "原问题要求首步大运，回答中没有写出")
    comparisons = {
        result["scope"]: result
        for result in state.get("calculations", {}).values()
        if result.get("scope") in ("dayun_first", "dayun_current")
    }
    comparisons.update(state.get("bazi_comparison_results", {}))
    periods = (state.get("bazi_period_result") or {}).get("periods", [])
    periods = [
        *periods,
        *[p for result in comparisons.values() for p in result.get("periods", [])],
    ]
    gz = set(g for g in bazi.get("pillars", {}).values() if g)
    for candidate in bazi.get("alternatives", []):
        gz.update(candidate.values())
    gz.update(d["ganzhi"] for d in (bazi.get("dayun") or {}).get("sequence", []))
    for p in periods:
        gz.update(p["pillars"].values())
    gz.update(segment["pillar"] for segment in (daily.get("day") or {}).get("segments", []))
    for value in re.findall(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", text):
        if value not in gz:
            return ValidationMessage(
                f"本次工具结果没有该干支，不能编造（冲突片段：“{value}”）",
                retry_key=f"unknown_ganzhi:{value}",
            )
    tz_name = (
        (state.get("bazi_period_result") or {}).get("tz")
        or state.get("timeframe_tz")
        or state.get("calendar_timezone")
        or "Asia/Shanghai"
    )
    try:
        tz_info = ZoneInfo(tz_name)
    except Exception:
        tz_info = ZoneInfo("Asia/Shanghai")
    anchor = _resolve_anchor_date(state, bazi, daily)
    # The daily fortune's day pillars are flow days as well.
    flows = [
        *periods,
        *({"pillars": {"day": s["pillar"]}} for s in (daily.get("day") or {}).get("segments", [])),
    ]
    for passage in claims:
        for match in PILLAR_CLAIM.finditer(passage):
            flow = match.group("flow")
            explicit_y = match.group("explicit_y")
            temp_y = match.group("temporal_y")
            temp_m = match.group("temporal_m")
            temp_d = match.group("temporal_d")
            is_temporal = bool(explicit_y or temp_y or temp_m or temp_d)
            scope, name, value = match.group("scope", "name", "value")
            pillar_char = (
                flow[-1]
                if flow
                else (
                    "年" if (explicit_y or temp_y) else "月" if temp_m else "日" if temp_d else name
                )
            )
            key = PILLAR_KEYS[pillar_char]
            if is_temporal:
                candidates = _temporal_flow_candidates(
                    match, passage, periods, daily, anchor, tz_info
                )
                if not any(p["pillars"].get(key) == value for p in candidates):
                    return ValidationMessage(
                        f"流期柱位与对应日期干支不符，请核对今年/明年/本月/今日与本次计算的日期区间（冲突片段：“{match.group(0)}”）",
                        retry_key=f"flow_pillar:{key}:{value}",
                    )
            elif flow or scope == "流期":
                if (flow and match["flow_name"] not in (None, flow[-1])) or not any(
                    p["pillars"].get(key) == value for p in flows
                ):
                    return ValidationMessage(
                        f"流期柱位与干支不符，请使用本次对应流年、流月或流日的计算结果（冲突片段：“{match.group(0)}”）",
                        retry_key=f"flow_pillar:{key}:{value}",
                    )
            elif scope == "候选" and any(c.get(key) == value for c in bazi.get("alternatives", [])):
                continue
            elif bazi.get("pillars", {}).get(key) != value:
                return ValidationMessage(
                    f"原局柱位与干支不符，请区分出生原局与流年、流月、流日（冲突片段：“{match.group(0)}”）",
                    retry_key=f"natal_pillar:{key}:{value}",
                )
    if (
        bazi
        and not bazi.get("time_known")
        and any(re.search(r"时柱(?:是|为|：|:|\s*[甲乙丙丁戊己庚辛壬癸])", p) for p in claims)
    ):
        return ValidationMessage("出生时辰未知，禁止编造时柱", retry_key="unknown_time_pillar")
    return None
