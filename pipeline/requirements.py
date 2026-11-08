"""What a calculation needs before it runs, checked by code (plan §3.5, P3.1).

The table below gathers what the prompts (common/domain_rules.py, agents/specialists.py) and the
Guard used to ask of the model. Each row is enforced here or by the calculator itself:
missing data and confirmations become a templated question that ends the turn; the next
message resumes the run (pipeline/runner.py, ``Intent.kind == "input"``). As the plan says,
the calculators keep their own confirmation logic: a NeedsInput they raise is turned into the
same kind of question, and the user's answer is read by the same input_evidence functions the
tools already use.

P3's first system is astro. Its consultation timezone follows the owner's decision of
2026-11-07: someone born abroad who asks about a range of dates and has not said where they live
now gets the birth place's timezone, and the reading says so.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from common.input_evidence import DATE, question_range
from common.location import consultation_timezone_evidence
from common.time_utils import NeedsInput
from plugins.context import confirmed_timezone

# §3.5 as data: (system, question type) → what is required and what must be confirmed.
# ``where``: who enforces each part (this module, the calculator, or the agent loop for now).
REQUIREMENTS = {
    ("astro", "trait"): dict(
        required=("出生日期", "出生时间（未知时须说明）", "出生地点"),
        confirm=("出生时间未知时不解读宫位和四轴",),
        where="birth_ready（资料是否齐全）；compute_natal_chart 的 NeedsInput（时间、地点、新疆钟表时区）",
    ),
    ("bazi", "trait"): dict(
        required=(
            "出生日期",
            "出生地点（经度和出生钟表时区）",
            "出生时间（未知时须说明，只排三柱）",
        ),
        confirm=(
            "海外出生：日柱时柱按真太阳时还是固定UTC+8",
            "新疆出生：钟表时间是北京时间还是新疆时间",
            "农历生日：是不是闰月",
            "时辰未知且出生当天交节：补时间，或确认展示候选",
        ),
        where="birth_ready / pipeline.birth（资料与文字出生资料）；compute_bazi 的 NeedsInput",
    ),
    ("bazi", "dayun"): dict(
        required=("同原局", "性别"),
        confirm=("真太阳时修正跨节气：确认按物理时刻起运",),
        where="Bazi.compute（性别，未知时追问）；compute_bazi 的 NeedsInput",
    ),
    ("bazi", "timing"): dict(
        required=("同原局", "时间范围（流月、流日 ≤ 366 天，流年 ≤ 3660 天）"),
        confirm=(
            "区间时区：说明了就用；北京时间出生默认北京时间；其余追问（不沿用星盘的出生地默认）",
        ),
        where="asked_range（时间范围）；compute_bazi_period 的 NeedsInput（区间时区）",
    ),
    ("astro", "timing"): dict(
        required=("出生日期", "出生时间（未知时须说明）", "出生地点", "时间范围（≤ 3660 天）"),
        confirm=(
            "咨询时区：说明了现居地或时区就用它；海外出生且未说明现居地时默认出生地时区并注明",
        ),
        where="asked_range（时间范围）；period_choice（咨询时区）；compute_transits 的 NeedsInput",
    ),
}

# Clocks that are China's own: elsewhere a birth is overseas (plugins/direct.py, bazi tools).
DOMESTIC_CLOCKS = ("Asia/Shanghai", "Asia/Urumqi", "Etc/GMT-8")
# A residence or consultation place stated in words. When it is not resolved to a timezone
# (consultation_timezone_evidence), the user is asked; it is never replaced by the default.
RESIDENCE = re.compile(
    r"住在|居住|定居|常住|移居|搬到|搬去|搬走|搬离|不住|回国|现居|现住|"
    r"在国外|在海外|在国内|国外生活|海外生活|(?:现在|目前)人在|人在[^，,。；;]{1,8}(?:生活|工作|读书|上学)|"
    r"时区|UTC|GMT|当地时间|北京时间|按.{0,8}时间"
)
# A question about a span of time; one without a range that code can read is asked for it.
# Suitability on its own (我适合做设计吗) is a natal question, “现在适合……” a timing one.
TIMING_WORDS = re.compile(
    r"运势|运气|运程|(?:事业|感情|财|桃花|学业|工作|考试|健康)运|时机|什么时候|何时|哪天|哪个月|几月|"
    r"最近|近期|近来|这段时间|这阵子|接下来|未来|今年|明年|后年|本月|这个月|下个?月|本周|这周|下周|"
    r"今天|明天|后天|(?:现在|目前|眼下)(?:适合|适不适合|能不能|可不可以)"
)
UNCLEAR_RANGE = "想看哪一段时间？可以说“下个月”“2026年12月”或“12月1日到12月15日”。"
TOO_LONG = "时间范围太长了：行运最多按十年计算，请缩小到具体的年份或月份。"
TOO_LONG_BAZI = "时间范围太长了：流年最多按十年计算，请缩小到具体的年份或月份。"
# Bazi words that ask about a span of time on their own (流年 without a year is asked for one).
BAZI_TIMING = re.compile(r"流年|流月|流日|今年运|明年运|运程")
# Worded around common.tools.REASK: an ask may not name a birth field the profile holds.
BIRTH_FORM = (
    "看星盘需要完整的出生资料：请在页面上的出生信息表里补全日期、时间和地点"
    "（时间不知道可以选未知），填好后发送“继续”。"
)
WEEKDAYS = "一二三四五六日天"
NUMBERS = {
    "一": 1,
    "两": 2,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


@dataclass(frozen=True)
class Period:
    start: str
    end: str
    tz: str
    defaulted: bool = False  # the birth place's timezone stands in for an unstated residence

    def note(self, place: str | None) -> str:
        if not self.defaulted:
            return ""
        where = f"出生地{place}" if place else "出生地"
        return (
            f"日期按{where}的时区（{self.tz}）计算；如果你现在住在别处，"
            "告诉我所在城市，可以按当地时间重新计算。"
        )


def birth_ready(session) -> bool:
    """Whether the profile or the birth form holds a birth date, a place and its clock."""
    binding = getattr(session, "birth_binding", None)
    if binding:
        bound = binding.get("profile") or {}
        return bool(
            bound.get("birth_local_dt") and bound.get("tz") and bound.get("lat") is not None
        )
    profile = session.profile
    return bool(
        profile.get("birth_local_dt") and profile.get("tz") and profile.get("lat") is not None
    )


def _number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if text in NUMBERS:
        return NUMBERS[text]
    if len(text) == 2 and text[0] == "十":
        return 10 + NUMBERS.get(text[1], 0)
    return None


def _months_after(day: date, months: int) -> date:
    year, index = divmod(day.year * 12 + day.month - 1 + months, 12)
    month = index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def asked_range(text: str, anchor: str | None) -> tuple[str, str] | None:
    """The range of dates a question asks about, read by code; None when it names none.

    question_range (the Guard's own reading) comes first, so a range it finds is the range the
    calculation is checked against. The rest are the common ways a range is said in Chinese.
    """
    found = question_range(text, anchor)
    if found:
        return found
    today = date.fromisoformat(anchor) if anchor else None
    cleaned = re.sub(r"(?:出生|生于|生日)[^，,。；;]{0,24}", "", text)
    # 2026年12月1日到12月15日 / 12月1日到15日: the second date may omit the year and month.
    full = rf"{DATE}\s*(?:至|到|—|~|～|–|-)\s*(?:(\d{{4}})年)?(?:(\d{{1,2}})月)?(\d{{1,2}})[日号]"
    match = re.search(full, cleaned)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()
        try:
            start = date(int(y1), int(m1), int(d1))
            end = date(int(y2 or y1), int(m2 or m1), int(d2))
        except ValueError:
            return None
        return (start.isoformat(), end.isoformat()) if end >= start else None
    # A weekday range such as “下周三到周五”; the second weekday shares the first's week.
    weekday_range = re.search(
        rf"(这|本|下)(?:个)?(?:周|星期|礼拜)([{WEEKDAYS}])\s*(?:至|到|—|~|～|–)\s*"
        rf"(?:(?:这|本|下)(?:个)?(?:周|星期|礼拜))?(?:周|星期|礼拜)?([{WEEKDAYS}])",
        cleaned,
    )
    if weekday_range and today is not None:
        monday = (
            today - timedelta(days=today.weekday()) + timedelta(days=7 * (weekday_range[1] == "下"))
        )
        start = monday + timedelta(days=min(WEEKDAYS.index(weekday_range[2]), 6))
        end = monday + timedelta(days=min(WEEKDAYS.index(weekday_range[3]), 6))
        if end < start:
            end += timedelta(days=7)
        return start.isoformat(), end.isoformat()
    if today is None:
        return None
    single = re.search(DATE, cleaned)
    if single:
        try:
            day = date(*map(int, single.groups())).isoformat()
        except ValueError:
            return None
        return day, day
    short = re.search(
        r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]\s*(?:至|到|—|~|～|–|-)\s*(?:(\d{1,2})月)?(\d{1,2})[日号]",
        cleaned,
    )
    if short:
        m1, d1, m2, d2 = short.groups()
        year = today.year if int(m1) >= today.month else today.year + 1
        try:
            start = date(year, int(m1), int(d1))
            end = date(year, int(m2 or m1), int(d2))
        except ValueError:
            return None
        return (start.isoformat(), end.isoformat()) if end >= start else None
    ahead = re.search(
        r"(?:接下来|未来|之后)的?([一两二三四五六七八九十\d]{1,2})个?(月|星期|礼拜|周)", cleaned
    )
    if ahead:
        count = _number(ahead[1])
        if not count:
            return None
        end = (
            _months_after(today, count) - timedelta(days=1)
            if ahead[2] == "月"
            else today + timedelta(days=7 * count - 1)
        )
        return today.isoformat(), end.isoformat()
    for word, offset in (("今天", 0), ("明天", 1), ("后天", 2)):
        if word in cleaned and not re.search(r"今天|明天|后天", cleaned.replace(word, "", 1)):
            day = today + timedelta(days=offset)
            return day.isoformat(), day.isoformat()
    week = re.search(rf"(这|本|下)(?:个)?(?:周|星期|礼拜)([{WEEKDAYS}])?", cleaned)
    if week:
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7 * (week[1] == "下"))
        if week[2]:
            day = monday + timedelta(days=min(WEEKDAYS.index(week[2]), 6))
            return day.isoformat(), day.isoformat()
        return monday.isoformat(), (monday + timedelta(days=6)).isoformat()
    year = None
    if re.search(r"今年", cleaned):
        year = today.year
    elif re.search(r"明年", cleaned):
        year = today.year + 1
    else:
        stated = re.search(r"(?<!\d)(\d{4})年(?!\d{1,2}月)", cleaned)
        if stated:
            year = int(stated[1])
    month = re.search(
        r"(?<!\d)(\d{1,2}|[一二三四五六七八九十]|十[一二])月(?!\d{1,2}[日号])", cleaned
    )
    if month and year is None:
        value = _number(month[1])
        if value and 1 <= value <= 12:
            year = today.year if value >= today.month else today.year + 1
            last = calendar.monthrange(year, value)[1]
            return f"{year:04d}-{value:02d}-01", f"{year:04d}-{value:02d}-{last:02d}"
    if year is not None:
        if month:
            value = _number(month[1])
            if value and 1 <= value <= 12:
                last = calendar.monthrange(year, value)[1]
                return f"{year:04d}-{value:02d}-01", f"{year:04d}-{value:02d}-{last:02d}"
        if "上半年" in cleaned:
            return f"{year:04d}-01-01", f"{year:04d}-06-30"
        if "下半年" in cleaned:
            return f"{year:04d}-07-01", f"{year:04d}-12-31"
        return f"{year:04d}-01-01", f"{year:04d}-12-31"
    return None


def is_timing(text: str) -> bool:
    return bool(TIMING_WORDS.search(text))


def overseas(tz: str | None) -> bool:
    return bool(tz) and tz not in DOMESTIC_CLOCKS


def period_choice(session, chart: dict, start: str, end: str) -> Period:
    """The consultation timezone of an astro range, or NeedsInput to ask for it.

    In order: a timezone the user stated for this question; the profile's saved consultation
    timezone; a birth in Beijing time; a stated residence that is not resolved is asked about;
    an overseas birth without a stated residence takes the birth place's timezone (owner,
    2026-11-07); anything else (a Xinjiang clock, UTC+8 written as such) is asked, as
    plugins.context.period_timezone asks it.
    """
    birth_tz = (chart.get("input") or {}).get("tz")
    confirmed = confirmed_timezone(session, birth_tz)
    if confirmed:
        return Period(start, end, confirmed)
    saved = session.profile.get("consultation_tz")
    if saved:
        return Period(start, end, saved)
    if birth_tz == "Asia/Shanghai":
        return Period(start, end, birth_tz)
    index = session.state.get("question_message_index", 0)
    texts = session.user_messages[index:] if index >= 0 else session.user_messages[-1:]
    stated = any(
        RESIDENCE.search(strip_birth_note(text))
        or consultation_timezone_evidence(text, session, birth_tz)
        for text in texts
    )
    if overseas(birth_tz) and not stated:
        return Period(start, end, birth_tz, defaulted=True)
    raise NeedsInput(
        "confirm_period_timezone",
        "这段日期按哪个城市的时间来看？可以说“按多伦多时间”或“按北京时间”。",
    )


BIRTH_NOTE = re.compile(r"\n*我在出生信息表中填写的资料：[^\n]*")


def strip_birth_note(text: str) -> str:
    """The web page appends the birth form; its place is the birth place, not a residence."""
    return BIRTH_NOTE.sub("", text or "")


def bazi_question_type(question: str, text: str, anchor: str | None) -> str:
    """“dayun” for a luck-cycle overview, “timing” for a range of dates, else “trait”.

    ``text`` is the question and its answers with birth dates removed (pipeline.birth). A
    luck-cycle question that also asks about a period is a timing question, as
    plugins.bazi.intent.dayun_overview decides for the agent loop.
    """
    from plugins.bazi.intent import dayun_overview

    if dayun_overview(question) and asked_range(text, anchor) is None:
        return "dayun"
    if asked_range(text, anchor) is not None or is_timing(question) or BAZI_TIMING.search(question):
        return "timing"
    return "trait"
