"""Generate evals/cases/reference_charts.yaml.

Reference values: Swiss Ephemeris with SE files (sepl_18 / semo_18, DE431-based).
Cross-check:      Swiss Ephemeris Moshier analytic theory (independent theory).
"""
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import yaml
from swe import planets, houses, sign_of, PLANETS, armc_and_obliquity, placidus_independent

OUT = sys.argv[1]

CASES = [
    # id, label, local datetime, tz, place, lat, lon, note
    ("chart-01", "19 世纪末 / 伦敦 GMT", (1900, 3, 21, 6, 0), "Europe/London", "London", 51.5074, -0.1278,
     "早期年份；伦敦当时使用 GMT"),
    ("chart-02", "北京 / 中午过后", (1949, 10, 1, 15, 0), "Asia/Shanghai", "北京", 39.9042, 116.4074,
     "中国标准时间 UTC+8"),
    ("chart-03", "上海 / 1987 夏令时", (1987, 6, 15, 8, 30), "Asia/Shanghai", "上海", 31.2304, 121.4737,
     "1987 年中国实行夏令时，本地钟表时间为 UTC+9；不按 IANA 时区换算会差 1 小时"),
    ("chart-04", "纽约 / 跨年前夜", (1995, 12, 31, 23, 45), "America/New_York", "New York", 40.7128, -74.0060,
     "本地日期与 UT 日期不同（UT 已是次日）"),
    ("chart-05", "新加坡 / 赤道附近", (2000, 1, 1, 0, 0), "Asia/Singapore", "Singapore", 1.3521, 103.8198,
     "低纬度；本地午夜对应 UT 前一天 16:00"),
    ("chart-06", "北京 / 夜间", (2008, 8, 8, 20, 8), "Asia/Shanghai", "北京", 39.9042, 116.4074,
     "常规用例"),
    ("chart-07", "悉尼 / 南半球 + 夏令时", (2012, 2, 29, 12, 0), "Australia/Sydney", "Sydney", -33.8688, 151.2093,
     "南半球；当日为澳洲夏令时 UTC+11；闰日"),
    ("chart-08", "雷克雅未克 / 高纬度", (2019, 3, 20, 22, 0), "Atlantic/Reykjavik", "Reykjavik", 64.1466, -21.9426,
     "接近春分；高纬度但仍低于极圈，Placidus 可用"),
    ("chart-09", "孟买 / 半小时时区 + 水星逆行", (2024, 4, 8, 12, 0), "Asia/Kolkata", "Mumbai", 19.0760, 72.8777,
     "UTC+5:30；当天水星逆行，用于检查逆行标记"),
    ("chart-10", "特罗姆瑟 / 极圈内", (1975, 1, 15, 3, 0), "Europe/Oslo", "Tromsø", 69.6492, 18.9553,
     "纬度 69.6° 在北极圈内，Placidus 宫制在此无定义；期望工具明确报告并回退到指定宫制（此处给出 Porphyry 结果）"),
]

ASPECTS = [("conjunction", 0, 8), ("opposition", 180, 8), ("trine", 120, 8),
           ("square", 90, 7), ("sextile", 60, 5)]


def r(x, n=4):
    return round(x, n)


def aspects(pos):
    res = []
    names = list(pos)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = abs(pos[a] - pos[b]) % 360
            d = 360 - d if d > 180 else d
            for name, ang, orb in ASPECTS:
                if abs(d - ang) <= orb:
                    res.append({"a": a, "b": b, "type": name, "angle": r(d, 3),
                                "orb": r(abs(d - ang), 3)})
    return res


def build_case(cid, label, ldt, tzname, place, lat, lon, note, time_known=True):
    tz = ZoneInfo(tzname)
    local = datetime(*ldt, tzinfo=tz)
    ut = local.astimezone(timezone.utc)
    p_swe = planets(ut, "swe")
    p_mos = planets(ut, "mos")
    plist, maxdiff = [], 0.0
    for name in PLANETS:
        lon_, spd = p_swe[name]
        diff = abs(((lon_ - p_mos[name][0]) + 180) % 360 - 180)
        maxdiff = max(maxdiff, diff)
        sign, sign_zh, deg = sign_of(lon_)
        plist.append({"body": name, "lon": r(lon_), "sign": sign, "sign_zh": sign_zh,
                      "deg_in_sign": r(deg), "speed_deg_per_day": r(spd),
                      "retrograde": spd < 0})
    case = {
        "id": cid,
        "label": label,
        "input": {
            "birth_local": local.strftime("%Y-%m-%d %H:%M"),
            "tz": tzname,
            "place": place,
            "lat": lat,
            "lon": lon,
            "time_known": time_known,
        },
        "derived": {
            "utc_offset": str(local.utcoffset()),
            "ut": ut.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "expected": {"planets": plist},
        "cross_check": {"method": "Swiss Ephemeris SE files vs Moshier",
                        "max_abs_diff_deg": r(maxdiff, 6)},
        "note": note,
    }
    pos = {p["body"]: p["lon"] for p in plist}
    if time_known:
        polar = abs(lat) > 66.56
        hsys = "O" if polar else "P"
        cusps, asc, mc = houses(ut, lat, lon, hsys, "swe")
        armc, obl = armc_and_obliquity(ut, lat, lon)
        if polar:
            # Porphyry: trisect each quadrant between the angles
            ind = {1: asc, 10: mc}
            q1 = (asc - mc) % 360          # MC -> ASC
            q2 = (mc + 180 - asc) % 360    # ASC -> IC
            ind[11] = (mc + q1 / 3) % 360
            ind[12] = (mc + 2 * q1 / 3) % 360
            ind[2] = (asc + q2 / 3) % 360
            ind[3] = (asc + 2 * q2 / 3) % 360
            for k in (10, 11, 12, 1, 2, 3):
                ind[(k + 6 - 1) % 12 + 1] = (ind[k] + 180) % 360
        else:
            ind = placidus_independent(armc, obl, lat)
        case["expected"]["house_system"] = "Placidus" if not polar else "Porphyry (fallback)"
        if polar:
            case["expected"]["placidus_defined"] = False
        case["expected"]["cusps"] = {k: r(v) for k, v in sorted(cusps.items())}
        case["expected"]["asc"] = {"lon": r(asc), "sign_zh": sign_of(asc)[1]}
        case["expected"]["mc"] = {"lon": r(mc), "sign_zh": sign_of(mc)[1]}
        case["cross_check"]["houses_method"] = "Swiss Ephemeris 宫位 vs 独立实现的宫位公式（同一 ARMC 与真黄赤交角）"
        case["cross_check"]["houses_max_abs_diff_deg"] = r(
            max(abs(((cusps[k] - ind[k]) + 180) % 360 - 180) for k in range(1, 13)), 6)
        # house placement of each planet
        cl = [cusps[i] for i in range(1, 13)]
        for p in plist:
            for i in range(12):
                a, b = cl[i], cl[(i + 1) % 12]
                span = (b - a) % 360
                if (p["lon"] - a) % 360 < span:
                    p["house"] = i + 1
                    break
    else:
        case["expected"]["cusps"] = None
        case["expected"]["asc"] = None
        case["expected"]["mc"] = None
        case["expected"]["rule"] = "出生时间未知：按本地中午 12:00 起盘；宫位、上升、天顶必须为 null，月亮位置误差可达 ±6.5°，解读不得引用宫位"
    case["expected"]["aspects"] = aspects(pos)
    return case


cases = [build_case(*c) for c in CASES]
cases.append(build_case("chart-11", "时间未知 / 成都", (1990, 7, 7, 12, 0), "Asia/Shanghai", "成都",
                        30.5728, 104.0668,
                        "用户不知道出生时间；工具应按中午起盘，并且不输出宫位与四轴", time_known=False))

doc = {
    "dataset": "reference_charts",
    "version": 1,
    "purpose": "西方占星排盘的确定性测试：行星黄经、星座、逆行、Placidus 宫位、上升/天顶、主要相位",
    "generated_with": {
        "reference": "Swiss Ephemeris（aloistr/swisseph，SE 星历文件 sepl_18.se1 / semo_18.se1）",
        "cross_check": "行星：同一库的 Moshier 解析星历（独立理论）；宫位：独立实现的 MC / 上升 / Placidus（Porphyry）公式",
        "frame": "地心、视位置、回归黄道（tropical）",
        "time": "本地时间按 IANA 时区换算为 UT（Python zoneinfo）",
    },
    "tolerance": {"planet_lon_deg": 0.01, "cusp_deg": 0.01},
    "aspect_orbs_deg": {name: orb for name, _, orb in ASPECTS},
    "notes": [
        "出生数据为合成数据，不对应真实人物：星历精度测试与输入是谁无关，用合成数据可避免处理真实个人信息。",
        "相位容许度是本数据集的约定，项目若改用其他容许度，需要重新生成 aspects 字段。",
        "计划中写的是用 Skyfield 交叉验证；生成本文件的环境无法下载 JPL 星历，因此改用 SE 文件 vs Moshier。项目环境就绪后，建议在 tests/ 中再加一道 Skyfield 校验。",
    ],
    "cases": cases,
}

from yamlio import dump
dump(doc, OUT)
print("cases:", len(cases))
for c in cases:
    print(c["id"], c["derived"]["ut"], c["cross_check"])
