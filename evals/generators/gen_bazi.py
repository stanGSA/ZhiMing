"""Generate evals/cases/bazi_boundary.yaml (50 cases).

Reference:   lunar_python (6tail, MIT) — the library the project plans to use.
Cross-check: an independent mini implementation in this file:
             year/month pillars from the Sun's apparent longitude (Swiss Ephemeris),
             day pillar from the Julian Day Number, hour pillar via 五鼠遁,
             ten gods and five-element counts from first principles.
Solar terms: every boundary case also records the term instant from both
             lunar_python and Swiss Ephemeris and the margin to the birth time.
"""
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import yaml

from lunar_python import Solar, Lunar  # noqa: E402
from swe import sun_lon, equation_of_time_minutes, _run, _ut_args, EPHE  # noqa: E402

OUT = sys.argv[1]
CST = timezone(timedelta(hours=8))
SH = ZoneInfo("Asia/Shanghai")

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
WX = "木火土金水"
GAN_WX = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
ZHI_WX = [4, 2, 0, 0, 2, 1, 1, 2, 3, 3, 2, 4]
TERM_LON = {"立春": 315, "惊蛰": 345, "清明": 15, "立夏": 45, "芒种": 75, "小暑": 105,
            "立秋": 135, "白露": 165, "寒露": 195, "立冬": 225, "大雪": 255, "小寒": 285}
TERM_KEY = {"立春": "立春", "小寒": "小寒"}


# ---------------------------------------------------------------- astronomy
def term_instant(name, year):
    """Instant (UTC) when the Sun's apparent longitude reaches the term's value."""
    target = TERM_LON[name]
    # rough date: 立春 ~ Feb 4; each term ~ 30.44 days apart
    order = ["小寒", "立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪"]
    approx = datetime(year, 1, 6, tzinfo=timezone.utc) + timedelta(days=30.44 * order.index(name))
    lo, hi = approx - timedelta(days=4), approx + timedelta(days=4)

    def f(t):
        return ((sun_lon(t) - target + 180) % 360) - 180

    for _ in range(45):
        mid = lo + (hi - lo) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return lo + (hi - lo) / 2


def moon_sun_elong(t):
    out = _run([*_ut_args(t), "-p01", "-fPl", "-eswe", f"-edir{EPHE}"]).split()
    sun, moon = float(out[1]), float(out[3])
    return ((moon - sun + 180) % 360) - 180


def new_moon_near(t):
    lo, hi = t - timedelta(days=3), t + timedelta(days=3)
    for _ in range(45):
        mid = lo + (hi - lo) / 2
        if moon_sun_elong(mid) < 0:
            lo = mid
        else:
            hi = mid
    return lo + (hi - lo) / 2


# ---------------------------------------------------------------- independent bazi
def jdn(d):
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def gz(i):
    return GAN[i % 10] + ZHI[i % 12]


def gz_index(stem, branch):
    for i in range(60):
        if i % 10 == stem and i % 12 == branch:
            return i


def shishen(dm, x):
    rel = (GAN_WX[x] - GAN_WX[dm]) % 5
    same = (dm % 2) == (x % 2)
    return [("比肩", "劫财"), ("食神", "伤官"), ("偏财", "正财"), ("七杀", "正官"), ("偏印", "正印")][rel][0 if same else 1]


def independent(civil, instant_utc, sect, hour_known=True):
    """civil: naive datetime used for day/hour (Beijing standard or true solar time).
    instant_utc: physical instant used for year/month (Sun longitude)."""
    lon = sun_lon(instant_utc)
    y = civil.year
    if civil.month <= 2 and 270 <= lon < 315:
        y -= 1
    if civil.month >= 11 and lon >= 315 and False:
        pass
    ys, yb = (y - 4) % 10, (y - 4) % 12
    m_off = int(((lon - 315) % 360) // 30)  # 0 = 寅
    mb = (2 + m_off) % 12
    ms = ((ys % 5) * 2 + 2 + m_off) % 10
    day_date = civil.date()
    late_zi = civil.hour == 23
    if late_zi and sect == 1:
        day_date = day_date + timedelta(days=1)
    di = (jdn(day_date) + 49) % 60
    res = {"year": gz(gz_index(ys, yb)), "month": gz(gz_index(ms, mb)), "day": gz(di)}
    if hour_known:
        hb = ((civil.hour + 1) // 2) % 12
        stem_day = di % 10
        if late_zi and sect == 2:
            stem_day = (di + 1) % 10  # 夜子时用次日日干起时
        hs = ((stem_day % 5) * 2 + hb) % 10
        res["time"] = GAN[hs] + ZHI[hb]
    return res, lon


# ---------------------------------------------------------------- lunar_python
def lp_bazi(civil, sect, hour_known=True, gender=None):
    s = Solar.fromYmdHms(civil.year, civil.month, civil.day, civil.hour, civil.minute, civil.second)
    e = s.getLunar().getEightChar()
    e.setSect(sect)
    pillars = {"year": e.getYear(), "month": e.getMonth(), "day": e.getDay()}
    if hour_known:
        pillars["time"] = e.getTime()
    dm = GAN.index(e.getDayGan())
    stems = [pillars[k][0] for k in pillars]
    branches = [pillars[k][1] for k in pillars]
    wx = {w: 0 for w in WX}
    for c in stems:
        wx[WX[GAN_WX[GAN.index(c)]]] += 1
    for c in branches:
        wx[WX[ZHI_WX[ZHI.index(c)]]] += 1
    ten = {"year": e.getYearShiShenGan(), "month": e.getMonthShiShenGan()}
    if hour_known:
        ten["time"] = e.getTimeShiShenGan()
    out = {
        "pillars": pillars,
        "day_master": e.getDayGan() + WX[GAN_WX[dm]],
        "ten_gods_stems": ten,
        "hidden_stems": {"year": e.getYearHideGan(), "month": e.getMonthHideGan(), "day": e.getDayHideGan(),
                         **({"time": e.getTimeHideGan()} if hour_known else {})},
        "nayin": {"year": e.getYearNaYin(), "month": e.getMonthNaYin(), "day": e.getDayNaYin(),
                  **({"time": e.getTimeNaYin()} if hour_known else {})},
        "wuxing_count": wx,
        "lunar_date": s.getLunar().toString(),
    }
    # independent check of ten gods
    ind_ten = {k: shishen(dm, GAN.index(pillars[k][0])) for k in ten}
    if gender is not None and hour_known:
        yun = e.getYun(1 if gender == "male" else 0)
        dy = yun.getDaYun()[1:9]
        out["dayun"] = {
            "gender": gender,
            "start_after": f"{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天",
            "start_solar": yun.getStartSolar().toYmd(),
            "forward": yun.isForward(),
            "sequence": [{"ganzhi": d.getGanZhi(), "start_year": d.getStartYear(), "start_age": d.getStartAge()} for d in dy],
            "convention": "lunar_python 默认起运算法（getYun 流派 1）",
        }
    return out, ind_ten, s.getLunar()


def lp_term(name, year):
    t = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()
    s = t[name]
    return datetime(s.getYear(), s.getMonth(), s.getDay(), s.getHour(), s.getMinute(), s.getSecond(), tzinfo=CST)


# ---------------------------------------------------------------- case builder
cases = []
checks = {"pillars_match": 0, "pillars_total": 0, "tengods_match": 0, "tengods_total": 0, "term_max_diff_s": 0.0}


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def add_case(cid, category, desc, *, clock, place="北京", lon=116.4074, lat=39.9042,
             gender="male", true_solar=False, hour_known=True, both_sects=False,
             term=None, expect_error=None, input_calendar="solar", lunar_input=None, note=None):
    case = {"id": cid, "category": category, "description": desc}
    inp = {"calendar": input_calendar}
    if lunar_input:
        inp["lunar_date"] = lunar_input
    inp.update({"birth_local_clock": clock.strftime("%Y-%m-%d %H:%M") if hour_known else clock.strftime("%Y-%m-%d"),
                "tz": "Asia/Shanghai", "place": place, "lat": lat, "lon": lon, "gender": gender,
                "time_known": hour_known, "true_solar_time": true_solar})
    case["input"] = inp
    if expect_error:
        case["expected"] = expect_error
        case["note"] = note
        cases.append(case)
        return case
    # clock (possibly DST) -> instant -> Beijing standard time
    instant = clock.replace(tzinfo=SH).astimezone(timezone.utc)
    std = instant.astimezone(CST).replace(tzinfo=None)
    derived = {"utc": instant.strftime("%Y-%m-%d %H:%M"), "beijing_standard_time": fmt(std)}
    civil = std
    if true_solar:
        lmt_shift = (lon - 120) * 4
        eot = equation_of_time_minutes(instant)
        civil = std + timedelta(minutes=lmt_shift + eot)
        derived["longitude_correction_min"] = round(lmt_shift, 2)
        derived["equation_of_time_min"] = round(eot, 2)
        derived["true_solar_time"] = fmt(civil)
        # margin to nearest 时辰 boundary (odd hours)
        mins = civil.hour * 60 + civil.minute + civil.second / 60
        b = min(abs(mins - (h * 60)) for h in range(-1, 26, 2))
        derived["margin_to_shichen_boundary_min"] = round(b, 1)
    case["derived"] = derived
    sects = [1, 2] if both_sects else [1]
    exp = {}
    for sect in sects:
        lp, ind_ten, lunar = lp_bazi(civil, sect, hour_known, gender if sect == 1 else None)
        ind, sunlon = independent(civil, instant, sect, hour_known)
        checks["pillars_total"] += 1
        if ind == lp["pillars"]:
            checks["pillars_match"] += 1
        else:
            print("MISMATCH", cid, sect, ind, lp["pillars"])
        checks["tengods_total"] += 1
        if ind_ten == lp["ten_gods_stems"]:
            checks["tengods_match"] += 1
        else:
            print("TENGOD MISMATCH", cid, ind_ten, lp["ten_gods_stems"])
        key = "next_day" if sect == 1 else "same_day"
        exp[key] = lp
        case.setdefault("cross_check", {})[f"independent_pillars_{key}"] = ind
    if both_sects:
        case["expected"] = {"by_zishi_rule": exp,
                            "zishi_rule_meaning": {
                                "next_day": "23:00 起即算次日：日柱换成次日，时柱为次日子时",
                                "same_day": "区分早晚子时：23–24 点日柱仍算当天，时柱用次日日干起子时"}}
    else:
        case["expected"] = exp["next_day"]
    if category == "夏令时":
        naive = clock
        lp_naive, _, _ = lp_bazi(naive, 1, hour_known)
        case["expected_if_dst_ignored"] = lp_naive["pillars"]
        case["derived"]["utc_offset_at_birth"] = str(clock.replace(tzinfo=SH).utcoffset())
    if true_solar:
        # also record what a tool would output if true solar time were (wrongly) ignored
        lp_off, _, _ = lp_bazi(std, 1, hour_known)
        case["expected_if_true_solar_off"] = lp_off["pillars"]
    case["cross_check"]["sun_apparent_longitude_deg"] = round(sunlon, 4)
    if term:
        name, yr = term
        t_swe = term_instant(name, yr).astimezone(CST)
        t_lp = lp_term(name, yr)
        diff = abs((t_swe - t_lp).total_seconds())
        checks["term_max_diff_s"] = max(checks["term_max_diff_s"], diff)
        case["cross_check"]["solar_term"] = {
            "name": name,
            "instant_lunar_python": t_lp.strftime("%Y-%m-%d %H:%M:%S"),
            "instant_swiss_ephemeris": t_swe.strftime("%Y-%m-%d %H:%M:%S"),
            "diff_seconds": round(diff, 1),
            "birth_minus_term_min": round((instant - t_swe).total_seconds() / 60, 1),
        }
    if note:
        case["note"] = note
    cases.append(case)
    return case


def at(instant_cst, minutes):
    """naive Beijing clock time = term instant + offset, floored to the minute"""
    t = instant_cst + timedelta(minutes=minutes)
    return t.replace(second=0, microsecond=0, tzinfo=None)


n = 0


def nid():
    global n
    n += 1
    return f"bazi-{n:02d}"


# 1) 立春换年：4 年 × 前后 15 分钟 = 8
genders = ["male", "female"]
for yr in (1990, 2000, 2008, 2024):
    t = term_instant("立春", yr).astimezone(CST)
    for off, side in ((-15, "前"), (15, "后")):
        add_case(nid(), "立春换年", f"{yr} 年立春{side} 15 分钟出生：年柱与月柱都应以立春时刻为界",
                 clock=at(t, off) if off > 0 else at(t, off), gender=genders[len(cases) % 2], term=("立春", yr))

# 2) 节气换月：5 个节 × 前后 10 分钟 = 10
for name, yr, place, lat, lon in (("惊蛰", 1995, "上海", 31.2304, 121.4737), ("清明", 2003, "广州", 23.1291, 113.2644),
                                  ("芒种", 2010, "武汉", 30.5928, 114.3055), ("白露", 2016, "南京", 32.0603, 118.7969),
                                  ("大雪", 2021, "沈阳", 41.8057, 123.4315)):
    t = term_instant(name, yr).astimezone(CST)
    for off, side in ((-10, "前"), (10, "后")):
        add_case(nid(), "节气换月", f"{yr} 年{name}{side} 10 分钟出生：月柱以{name}时刻为界，不看农历月份",
                 clock=at(t, off), place=place, lat=lat, lon=lon, gender=genders[len(cases) % 2], term=(name, yr))

# 3) 子时：8
zi = [
    (datetime(1993, 8, 17, 23, 20), "23:20 出生：两种子时规则的日柱不同", True),
    (datetime(1993, 8, 18, 0, 20), "00:20 出生（早子时）：两种规则结果相同", True),
    (datetime(2001, 2, 27, 22, 59), "22:59 出生：仍是亥时，不应被算成子时", False),
    (datetime(2001, 2, 27, 23, 0), "23:00 整出生：子时起点", True),
    (datetime(2015, 12, 31, 23, 40), "跨年夜 23:40：按“23 点换日”规则日柱进入 1 月 1 日，但年柱、月柱不变（还没到小寒/立春）", True),
    (datetime(2020, 6, 20, 23, 59), "23:59 出生：子时末尾附近", True),
    (datetime(2011, 5, 5, 23, 50), "立夏前夜 23:50：日柱可按次日算，但月柱仍是辰月（立夏在次日凌晨）", True),
    (datetime(1984, 3, 1, 23, 5), "闰年 2 月最后一天之后的 3 月 1 日 23:05", True),
]
for clk, desc, both in zi:
    add_case(nid(), "子时归属", desc, clock=clk, both_sects=both, gender=genders[len(cases) % 2])

# 4) 真太阳时：8（北京时间输入，开启真太阳时）
ts = [
    ("乌鲁木齐", 43.8256, 87.6168, datetime(1996, 5, 10, 8, 30), "钟表辰时，真太阳时落在卯时"),
    ("拉萨", 29.6520, 91.1721, datetime(2002, 9, 1, 13, 10), "钟表未时，真太阳时落在午时"),
    ("喀什", 39.4704, 75.9898, datetime(1999, 3, 20, 1, 30), "钟表凌晨 1:30，真太阳时退回到前一天 22 点多：日柱也要变"),
    ("成都", 30.5728, 104.0668, datetime(2005, 7, 15, 7, 20), "钟表辰时，真太阳时落在卯时"),
    ("西安", 34.3416, 108.9398, datetime(2010, 10, 10, 15, 20), "钟表申时，真太阳时落在未时"),
    ("哈尔滨", 45.8038, 126.5350, datetime(2013, 12, 25, 22, 50), "钟表亥时，真太阳时进入子时"),
    ("上海", 31.2304, 121.4737, datetime(2017, 11, 3, 10, 45), "经度修正只有约 6 分钟，主要是 11 月初约 +16 分钟的均时差把巳时推到午时"),
    ("广州", 23.1291, 113.2644, datetime(2018, 2, 11, 13, 5), "经度修正约 −27 分钟，再加 2 月约 −14 分钟的均时差，未时退到午时"),
]
for place, lat, lon, clk, desc in ts:
    add_case(nid(), "真太阳时", desc, clock=clk, place=place, lat=lat, lon=lon, true_solar=True,
             gender=genders[len(cases) % 2])

# 5) 1986–1991 夏令时：6
add_case(nid(), "夏令时", "1988 年夏令时钟表 23:40，标准时 22:40 是亥时；若忽略夏令时会被当成子时，按 23 点换日规则日柱也会错成次日",
         clock=datetime(1988, 7, 14, 23, 40), gender="female")
add_case(nid(), "夏令时", "1990 年夏令时钟表 07:10，标准时 06:10：卯时；忽略夏令时会算成辰时",
         clock=datetime(1990, 6, 10, 7, 10), gender="male")
add_case(nid(), "夏令时", "1987 年夏令时钟表 15:30，标准时 14:30：未时；忽略夏令时会算成申时",
         clock=datetime(1987, 8, 20, 15, 30), place="上海", lat=31.2304, lon=121.4737, gender="female")
add_case(nid(), "夏令时", "1991 年夏令时钟表 12:00，标准时 11:00：两者都在午时，作为对照用例",
         clock=datetime(1991, 5, 1, 12, 0), gender="male")
add_case(nid(), "夏令时", "1986-05-04 02:30：夏令时开始当天 02:00 直接跳到 03:00，这个钟表时间不存在",
         clock=datetime(1986, 5, 4, 2, 30),
         expect_error={"error": "nonexistent_local_time",
                       "behavior": "不排盘；提示用户该时间不存在，并追问钟表时间是否已按夏令时调整（ask_user）"},
         note="Asia/Shanghai 1986-05-04 02:00 → 03:00")
add_case(nid(), "夏令时", "1986-09-14 01:30：夏令时结束当天 02:00 回拨到 01:00，这个钟表时间出现两次",
         clock=datetime(1986, 9, 14, 1, 30),
         expect_error={"error": "ambiguous_local_time",
                       "candidates_beijing_standard_time": ["1986-09-14 00:30（夏令时下的 01:30）", "1986-09-14 01:30（回拨后的 01:30）"],
                       "behavior": "不直接排盘；追问用户是回拨前还是回拨后，或同时给出两种结果并说明差异（日柱相同，时柱一个是子时一个是丑时）"},
         note="Asia/Shanghai 1986-09-14 02:00(+9) → 01:00(+8)")

# 6) 农历闰月输入：6
leap = [(2023, -2, 15, "闰二月十五"), (2023, 2, 15, "二月十五（非闰，对照）"), (2020, -4, 8, "闰四月初八"),
        (2017, -6, 1, "闰六月初一"), (2012, -4, 15, "闰四月十五"), (2006, -7, 7, "闰七月初七")]
for y, m, d, label in leap:
    ln = Lunar.fromYmdHms(y, m, d, 10, 0, 0)
    sol = ln.getSolar()
    clk = datetime(sol.getYear(), sol.getMonth(), sol.getDay(), 10, 0)
    c = add_case(nid(), "农历闰月输入", f"用户给的是农历 {y} 年{label} 上午 10 点：必须先确认是否闰月，再转公历排盘",
                 clock=clk, input_calendar="lunar", lunar_input=f"{y}年{label.split('（')[0]} 10:00",
                 gender=genders[len(cases) % 2])
    c["expected"]["solar_date"] = clk.strftime("%Y-%m-%d")
    # independent check: the lunar month's first day == Beijing date of the new moon,
    # and a leap month contains no 中气 (Sun longitude multiple of 30°)
    first = Lunar.fromYmd(y, m, 1).getSolar()
    first_d = datetime(first.getYear(), first.getMonth(), first.getDay())
    nm = new_moon_near(datetime(first_d.year, first_d.month, first_d.day, tzinfo=CST).astimezone(timezone.utc))
    nm2 = new_moon_near(nm + timedelta(days=29.53))
    # 中气 = Sun longitude at a multiple of 30°; a month (by Beijing *date*,
    # from the new-moon day up to the day before the next new-moon day)
    # contains a 中气 if the crossing's Beijing date falls inside it.
    l1 = sun_lon(nm)
    target = (int(l1 // 30) + 1) * 30 % 360
    lo, hi = nm, nm2 + timedelta(days=2)
    for _ in range(45):
        mid = lo + (hi - lo) / 2
        if ((sun_lon(mid) - target + 180) % 360) - 180 < 0:
            lo = mid
        else:
            hi = mid
    zq = lo.astimezone(CST)
    has_zhongqi = nm.astimezone(CST).date() <= zq.date() < nm2.astimezone(CST).date()
    c["cross_check"]["lunar_month"] = {
        "first_day_lunar_python": first_d.strftime("%Y-%m-%d"),
        "new_moon_swiss_ephemeris_beijing": nm.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
        "first_day_matches_new_moon": nm.astimezone(CST).date() == first_d.date(),
        "next_new_moon_beijing": nm2.astimezone(CST).strftime("%Y-%m-%d %H:%M"),
        "first_zhongqi_after_new_moon_beijing": zq.strftime("%Y-%m-%d %H:%M"),
        "contains_zhongqi": has_zhongqi,
        "is_leap_month": m < 0,
        "leap_rule_consistent": (m < 0) == (not has_zhongqi),
    }

# 7) 春节与立春不一致：2
add_case(nid(), "春节与立春", "2023-01-25 已过春节（农历癸卯年正月初四），但还没到立春：年柱仍是壬寅",
         clock=datetime(2023, 1, 25, 9, 0), gender="female", term=("立春", 2023))
add_case(nid(), "春节与立春", "2021-02-08 已过立春但还没到春节（农历仍是庚子年腊月）：年柱已是辛丑",
         clock=datetime(2021, 2, 8, 16, 0), gender="male", term=("立春", 2021))

# 8) 时辰未知：2
add_case(nid(), "时辰未知", "只知道出生日期 1998-04-12：只排年、月、日三柱，时柱、大运起运时刻不输出",
         clock=datetime(1998, 4, 12, 12, 0), hour_known=False, gender="male")
add_case(nid(), "时辰未知", "只知道出生日期 2004-02-04（立春当天，立春时刻在 19:56 左右）：年柱、月柱无法确定，必须追问出生时间",
         clock=datetime(2004, 2, 4, 12, 0), hour_known=False, gender="female", term=("立春", 2004),
         note="时辰未知又恰逢节气当天时，三柱里的年柱 / 月柱都依赖具体时刻；按中午计算的结果只作参考，期望行为是 ask_user")

for c in cases:
    if c["id"] == "bazi-43":
        c["note"] = ("2020 年闰四月：夏至（6 月 21 日 05:43）与下一个朔日（6 月 21 日 14:41）在同一天，"
                     "按日期归入五月，所以闰四月没有中气。只按时刻比较会误判，这是闰月算法的经典陷阱")
    if c["id"] == "bazi-50":
        c["expected_behavior"] = "ask_user：询问出生时间；若用户仍不知道，同时给出节气前后两种年柱/月柱，并在 confidence 中说明"

doc = {
    "dataset": "bazi_boundary",
    "version": 1,
    "purpose": "八字排盘的边界测试：立春换年、节气换月、子时归属、真太阳时、1986–1991 夏令时、农历闰月输入、春节与立春错位、时辰未知",
    "generated_with": {
        "reference": "lunar_python（6tail/lunar-python，MIT）",
        "cross_check": [
            "独立实现：年柱/月柱由太阳视黄经（Swiss Ephemeris）判断，日柱由儒略日数计算，时柱用五鼠遁，十神按五行生克规则推导",
            "节气时刻：lunar_python 与 Swiss Ephemeris 各算一次并记录差值",
            "闰月：用 Swiss Ephemeris 求朔日与中气，验证农历月初一与闰月判定",
        ],
        "time": "钟表时间 → IANA 时区 Asia/Shanghai（含 1986–1991 夏令时）→ 北京标准时 UTC+8；开启真太阳时的用例再做经度与均时差修正",
    },
    "conventions": {
        "zishi_rule": "默认 next_day（23:00 起换日）；标注 both 的用例同时给出 same_day 结果",
        "true_solar_time": "真太阳时 = 北京标准时 + (经度 − 120°) × 4 分钟 + 均时差；所有柱都用修正后的时间",
        "dayun": "大运用 lunar_python 默认起运算法；不同流派起运岁数可能相差数月，测试时只比较本项目选定的流派",
        "ten_gods": "只列年、月、时三柱天干相对日主的十神",
    },
    "summary": {
        "cases": len(cases),
        "independent_pillar_agreement": f"{checks['pillars_match']}/{checks['pillars_total']}",
        "independent_ten_gods_agreement": f"{checks['tengods_match']}/{checks['tengods_total']}",
        "max_solar_term_diff_seconds_lunar_python_vs_swiss_ephemeris": round(checks["term_max_diff_s"], 1),
    },
    "notes": [
        "出生数据均为合成数据。",
        "节气边界用例与节气时刻至少相隔 10 分钟，远大于两种算法的节气时刻差，因此标准答案不受算法差异影响。",
        "“权威万年历人工核对”这一步仍建议做：抽 10 条与纸质或权威网站万年历比对。",
    ],
    "cases": cases,
}
from yamlio import dump
dump(doc, OUT)
print(doc["summary"])
