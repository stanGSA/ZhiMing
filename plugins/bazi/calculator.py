import re
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache

import swisseph as swe
from lunar_python import Lunar, Solar
from lunar_python.util import LunarUtil

from common.time_utils import NeedsInput, date_range, local_instant

GAN, ZHI, WX = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥", "木火土金水"
GAN_WX, ZHI_WX = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4], [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]
CST = timezone(timedelta(hours=8))
CONVENTION = "lunar_python 默认起运算法（getYun 流派 1）"
JIE = (
    "小寒",
    "立春",
    "惊蛰",
    "清明",
    "立夏",
    "芒种",
    "小暑",
    "立秋",
    "白露",
    "寒露",
    "立冬",
    "大雪",
)


def solar(dt):
    return Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def as_datetime(s):
    return datetime(
        s.getYear(), s.getMonth(), s.getDay(), s.getHour(), s.getMinute(), s.getSecond(), tzinfo=CST
    )


@lru_cache(maxsize=128)
def terms(year):
    table = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()
    return tuple(sorted(as_datetime(table[name]) for name in JIE))


def ten_god(day_stem, other_stem):
    d, x = GAN.index(day_stem), GAN.index(other_stem)
    relation, same = (GAN_WX[x] - GAN_WX[d]) % 5, (d % 2) == (x % 2)
    return (
        ("比肩", "劫财"),
        ("食神", "伤官"),
        ("偏财", "正财"),
        ("七杀", "正官"),
        ("偏印", "正印"),
    )[relation][0 if same else 1]


def parse_lunar(text, leap_month):
    match = re.fullmatch(
        r"(\d{4})年(闰)?(正|冬|腊|[一二三四五六七八九十]+)月(初[一二三四五六七八九十]|十[一二三四五六七八九]?|廿[一二三四五六七八九]?|三十|\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?",
        text,
    )
    if not match:
        raise NeedsInput(
            "invalid_lunar", "请提供农历年月日、是否闰月以及钟表时刻，例如2023年闰二月十五 10:00。"
        )
    year, leap, month, day, hour, minute = match.groups()
    numbers = dict(zip("一二三四五六七八九", range(1, 10), strict=True))

    def number(value):
        if value.isdigit():
            return int(value)
        if value in ("正", "冬", "腊"):
            return {"正": 1, "冬": 11, "腊": 12}[value]
        value = value.removeprefix("初")
        if value.startswith("廿"):
            return 20 + numbers.get(value[1:], 0)
        if value.startswith("三十"):
            return 30
        if value.startswith("十"):
            return 10 + numbers.get(value[1:], 0)
        return numbers[value]

    if leap_month is None and not leap:
        raise NeedsInput("confirm_leap_month", "请确认农历生日是普通月还是闰月。")
    if leap and leap_month is False:
        raise NeedsInput("lunar_conflict", "农历文字标注闰月，与闰月开关冲突，请确认。")
    month_number, day_number = number(month), number(day)
    try:
        lunar = Lunar.fromYmdHms(
            int(year),
            -month_number if leap or leap_month else month_number,
            day_number,
            int(hour or 12),
            int(minute or 0),
            0,
        )
        converted = as_datetime(lunar.getSolar()).replace(tzinfo=None)
    except Exception as exc:
        raise NeedsInput("invalid_lunar", "农历日期或闰月不存在，请核对。") from exc
    return converted.isoformat(sep=" "), bool(hour)


def civil_time(utc, lon, true_solar_time):
    standard = utc.astimezone(CST).replace(tzinfo=None)
    if not true_solar_time:
        return standard, 0.0
    jd = swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + utc.second / 3600)
    # Swiss time_equ returns apparent-minus-mean solar time in days.
    shift = (lon - 120) * 4 + swe.time_equ(jd) * 1440
    return standard + timedelta(minutes=shift), shift


def core(utc, lon, true_solar_time, zishi_rule, time_known):
    civil, shift = civil_time(utc, lon, true_solar_time)
    lunar = solar(civil).getLunar()
    e = lunar.getEightChar()
    e.setSect(1 if zishi_rule == "next_day" else 2)
    physical = solar(utc.astimezone(CST)).getLunar().getEightChar()
    pillars = dict(year=physical.getYear(), month=physical.getMonth(), day=e.getDay())
    if time_known:
        pillars["time"] = e.getTime()
    count = dict.fromkeys(WX, 0)
    for gz in pillars.values():
        count[WX[GAN_WX[GAN.index(gz[0])]]] += 1
        count[WX[ZHI_WX[ZHI.index(gz[1])]]] += 1
    hidden = {k: list(LunarUtil.ZHI_HIDE_GAN[gz[1]]) for k, gz in pillars.items()}
    return dict(
        pillars=pillars,
        day_master=pillars["day"][0] + WX[GAN_WX[GAN.index(pillars["day"][0])]],
        ten_gods_stems={
            k: ten_god(pillars["day"][0], gz[0]) for k, gz in pillars.items() if k != "day"
        },
        hidden_stems=hidden,
        hidden_ten_gods={
            k: [ten_god(pillars["day"][0], g) for g in stems] for k, stems in hidden.items()
        },
        nayin={k: LunarUtil.NAYIN[gz] for k, gz in pillars.items()},
        wuxing_count=count,
        lunar_date=lunar.toString(),
        civil_time=civil.isoformat(sep=" "),
        solar_correction_minutes=shift,
    ), e


def compute_bazi(
    birth_local: str | None,
    tz: str,
    lon: float,
    gender: str | None = None,
    time_known=True,
    true_solar_time=False,
    zishi_rule="next_day",
    fold=None,
    calendar="solar",
    lunar_date=None,
    calendar_confirmed=False,
    leap_month=None,
    accept_uncertain=False,
    dayun_time_basis="civil",
):
    if dayun_time_basis not in ("civil", "physical"):
        raise NeedsInput(
            "invalid_dayun_basis", "请确认起运按civil修正钟表口径或physical物理时刻口径。"
        )
    if zishi_rule not in ("next_day", "same_day") or not -180 <= lon <= 180:
        raise NeedsInput("invalid_convention", "请确认经度与子时规则。")
    if gender not in (None, "male", "female"):
        raise NeedsInput("invalid_gender", "大运顺逆算法需要明确male/female；不提供则不排大运。")
    if calendar == "lunar":
        if not calendar_confirmed:
            raise NeedsInput("confirm_calendar", "请确认这是农历生日，并确认是否闰月。")
        birth_local, has_hour = parse_lunar(lunar_date or "", leap_month)
        if time_known and not has_hour:
            raise NeedsInput("missing_birth_time", "请补充出生时刻；不知道则只排能确定的三柱。")
    if not birth_local:
        raise NeedsInput(
            "missing_birth_date", "请提供出生日期、出生地点与出生时间（不知道请说明）。"
        )
    if time_known and len(birth_local) <= 10:
        raise NeedsInput("missing_birth_time", "请补充出生钟表时间或明确说明时辰未知。")
    local = birth_local if time_known else birth_local[:10] + "T12:00:00"
    utc = local_instant(local, tz, fold)
    if not 1900 <= utc.year <= 2100:
        raise NeedsInput("calendar_range", "当前八字历法验收范围为1900–2100年，请确认日期。")
    result, e = core(utc, lon, true_solar_time, zishi_rule, time_known)
    uncertainty = []
    if not time_known:
        first = local_instant(birth_local[:10] + "T00:00:00", tz)
        last = local_instant(
            (datetime.fromisoformat(birth_local[:10]) + timedelta(days=1)).isoformat(), tz
        ) - timedelta(microseconds=1)
        # Physical Jie boundaries, plus corrected local day changes, cannot be guessed at noon.
        alternatives = []
        samples = [first, last]
        samples += [
            t.astimezone(UTC) + timedelta(seconds=offset)
            for y in range(first.year - 1, last.year + 2)
            for t in terms(y)
            if first <= t <= last
            for offset in (-1, 1)
        ]
        for sample in samples:
            alt = core(sample, lon, true_solar_time, zishi_rule, False)[0]["pillars"]
            # Unknown-hour same civil date can include the late Zi variant. Report it separately;
            # three-pillar MVP convention uses date at noon for day, never implies an actual hour.
            if alt not in alternatives:
                alternatives.append(alt)
        year_month = {(x["year"], x["month"]) for x in alternatives}
        if len(year_month) > 1:
            if not accept_uncertain:
                raise NeedsInput(
                    "unknown_time_at_term",
                    "出生日期包含换年/换月节气，年柱月柱不能唯一确定，请补充出生时间；仍不知道可确认展示候选。",
                    alternatives,
                )
            result["alternatives"] = alternatives
            result["pillars"] = {
                k: v if len({x[k] for x in alternatives}) == 1 else None
                for k, v in result["pillars"].items()
            }
            result["day_master"] = (
                None if result["pillars"]["day"] is None else result["day_master"]
            )
            # Do not attach noon-only facts to unknown pillars.
            for field in ("ten_gods_stems", "hidden_stems", "hidden_ten_gods", "nayin"):
                result[field] = {
                    k: v for k, v in result[field].items() if result["pillars"].get(k) is not None
                }
            result["wuxing_count"] = None
        elif true_solar_time and len({x["day"] for x in alternatives}) > 1:
            raise NeedsInput(
                "unknown_solar_day",
                "真太阳时修正可能跨日，出生时间未知时日柱不能确定，请补充时刻或关闭真太阳时。",
                alternatives,
            )
        uncertainty.append(
            "时辰未知：仅日期中午代理的三柱，不输出时柱和精确起运；23点换日规则下晚子时另有次日日柱可能。"
        )
    dayun = None
    if time_known and gender:
        physical = solar(utc.astimezone(CST)).getLunar().getEightChar()
        if dayun_time_basis == "civil" and (e.getYear(), e.getMonth()) != (
            physical.getYear(),
            physical.getMonth(),
        ):
            raise NeedsInput(
                "confirm_dayun_time_basis",
                "真太阳时钟表修正跨过节气，默认修正钟表起运口径会与物理年/月柱冲突。请确认改用physical物理时刻起运，或暂不排大运。",
            )
        yun = (physical if dayun_time_basis == "physical" else e).getYun(
            1 if gender == "male" else 0, 1
        )
        dayun = dict(
            gender=gender,
            start_after=f"{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天",
            start_solar=yun.getStartSolar().toYmd(),
            forward=yun.isForward(),
            sequence=[
                dict(ganzhi=d.getGanZhi(), start_year=d.getStartYear(), start_age=d.getStartAge())
                for d in yun.getDaYun()[1:9]
            ],
            convention=CONVENTION,
        )
    if not gender:
        uncertainty.append("性别未提供，未排大运。")
    return {
        **result,
        "dayun": dayun,
        "utc": utc.isoformat(),
        "solar_date": birth_local[:10],
        "time_known": time_known,
        "uncertainty": uncertainty,
        "conventions": dict(
            year="立春时刻换年",
            month="十二节时刻换月（物理时刻，不平移节气）",
            day_hour="北京时间固定UTC+8；开启真太阳时则改为出生地视太阳时",
            zishi_rule=zishi_rule,
            dayun=CONVENTION,
            dayun_time_basis=dayun_time_basis,
            dayun_time_explanation="civil沿用参考集getYun1修正钟表日期对节气的折算；physical用物理出生时刻转固定UTC+8。真太阳时跨节气须先确认physical，不静默改顺逆。",
            wuxing="天干与地支主五行简单计数，非旺衰权重",
            useful_god="MVP不判喜用神",
        ),
        "input": dict(
            birth_local=birth_local,
            tz=tz,
            lon=lon,
            gender=gender,
            time_known=time_known,
            true_solar_time=true_solar_time,
            zishi_rule=zishi_rule,
            fold=fold,
            dayun_time_basis=dayun_time_basis,
        ),
    }


def relations(ganzhi, natal):
    result = []
    for name, original in natal.items():
        if not original:
            continue
        stem_pair = frozenset((ganzhi[0], original[0]))
        branch_pair = frozenset((ganzhi[1], original[1]))
        for kind, pairs in {
            "天干合": ("甲己", "乙庚", "丙辛", "丁壬", "戊癸"),
            "天干冲": ("甲庚", "乙辛", "丙壬", "丁癸"),
            "地支六合": ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"),
            "地支冲": ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"),
            "地支害": ("子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"),
            "地支破": ("子酉", "丑辰", "寅亥", "卯午", "巳申", "未戌"),
            "地支刑": ("子卯", "寅巳", "巳申", "申寅", "丑戌", "戌未", "未丑"),
        }.items():
            pair = stem_pair if kind.startswith("天干") else branch_pair
            if any(pair == frozenset(p) for p in pairs):
                result.append(dict(type=kind, natal_pillar=name, natal_ganzhi=original))
        if ganzhi[1] == original[1] and ganzhi[1] in "辰午酉亥":
            result.append(dict(type="自刑", natal_pillar=name, natal_ganzhi=original))
    branches = set(gz[1] for gz in natal.values() if gz) | {ganzhi[1]}
    for kind, groups in {
        "三合": ("申子辰", "亥卯未", "寅午戌", "巳酉丑"),
        "三会": ("寅卯辰", "巳午未", "申酉戌", "亥子丑"),
    }.items():
        for group in groups:
            if ganzhi[1] in group and set(group) <= branches:
                result.append(dict(type=kind, branches=group))
    return result


def bazi_period(chart, start, end, granularity="month", tz="Asia/Shanghai"):
    if granularity not in ("year", "month", "day"):
        raise NeedsInput("invalid_granularity", "请选择年/月/日粒度。")
    if not chart["day_master"]:
        raise NeedsInput("uncertain_day_master", "原局日主无法确定，需要先确认出生时刻。")
    a, b = date_range(start, end, tz, 3660 if granularity == "year" else 366)
    cuts = {a, b}
    for year in range(a.year - 1, b.year + 2):
        for t in terms(year):
            if a < t < b and (granularity != "year" or t.month == 2):
                cuts.add(t.astimezone(UTC))
    if granularity == "day":
        # Daily pillars use the chart's declared civil convention; correct solar rollover by solving.
        base = (a.astimezone(CST) - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for i in range((b - a).days + 5):
            boundary = base + timedelta(
                days=i, hours=-1 if chart["input"]["zishi_rule"] == "next_day" else 0
            )
            t = boundary.astimezone(UTC)
            if chart["input"]["true_solar_time"]:
                for _ in range(5):
                    civil = civil_time(t, chart["input"]["lon"], True)[0]
                    t -= civil - boundary.replace(tzinfo=None)
            if a < t < b:
                cuts.add(t)
    cuts = sorted(cuts)
    periods = []
    for left, right in zip(cuts[:-1], cuts[1:], strict=True):
        instant = left + (right - left) / 2
        c = core(
            instant,
            chart["input"]["lon"],
            chart["input"]["true_solar_time"],
            chart["input"]["zishi_rule"],
            True,
        )[0]
        # Never silently group different day pillars across terms; all cuts are retained.
        names = {"year": ["year"], "month": ["year", "month"], "day": ["year", "month", "day"]}[
            granularity
        ]
        pillars = {name: c["pillars"][name] for name in names}
        periods.append(
            dict(
                start_utc=left.isoformat(),
                end_utc=right.isoformat(),
                pillars=pillars,
                ten_gods={k: ten_god(chart["day_master"][0], gz[0]) for k, gz in pillars.items()},
                relations={k: relations(gz, chart["pillars"]) for k, gz in pillars.items()},
            )
        )
    return dict(
        bazi_id=chart.get("bazi_id"),
        start=start,
        end=end,
        tz=tz,
        granularity=granularity,
        periods=periods,
        conventions=chart["conventions"],
        interval="date end inclusive; datetime end exclusive",
    )
