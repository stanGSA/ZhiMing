"""Thin wrapper around the compiled swetest binary (Swiss Ephemeris)."""
import os
import subprocess
from datetime import datetime, timezone

SWETEST = os.environ.get("SWETEST", "swetest")          # Swiss Ephemeris 命令行程序
EPHE = os.environ.get("SE_EPHE_PATH", "data/ephe")      # sepl_18.se1 / semo_18.se1 所在目录

PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
           "Uranus", "Neptune", "Pluto"]
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGNS_ZH = ["白羊", "金牛", "双子", "巨蟹", "狮子", "处女", "天秤", "天蝎",
            "射手", "摩羯", "水瓶", "双鱼"]


def _run(args):
    out = subprocess.run([SWETEST, *args, "-head"], capture_output=True,
                         text=True, check=True).stdout
    return out


def _ut_args(ut: datetime):
    ut = ut.astimezone(timezone.utc)
    secs = ut.second + ut.microsecond / 1e6
    return [f"-b{ut.day}.{ut.month}.{ut.year}",
            f"-ut{ut.hour}:{ut.minute:02d}:{secs:06.3f}"]


def planets(ut: datetime, engine="swe"):
    """Return {name: (lon, speed)}; engine 'swe' = SE files, 'mos' = Moshier."""
    eng = ["-eswe", f"-edir{EPHE}"] if engine == "swe" else ["-emos"]
    out = _run([*_ut_args(ut), "-p0123456789", "-fPls", *eng])
    res = {}
    for line in out.strip().splitlines():
        name = line[:16].strip()
        vals = line[16:].split()
        res[name] = (float(vals[0]), float(vals[1]))
    return res


def houses(ut: datetime, lat: float, lon: float, hsys="P", engine="swe"):
    eng = ["-eswe", f"-edir{EPHE}"] if engine == "swe" else ["-emos"]
    out = _run([*_ut_args(ut), "-p0", f"-house{lon},{lat},{hsys}", "-fPl", *eng])
    cusps, asc, mc = {}, None, None
    for line in out.strip().splitlines():
        name = line[:16].strip()
        try:
            val = float(line[16:].split()[0])
        except (IndexError, ValueError):
            continue
        if name.startswith("house"):
            cusps[int(name.split()[1])] = val
        elif name == "Ascendant":
            asc = val
        elif name == "MC":
            mc = val
    return cusps, asc, mc


def sun_lon(ut: datetime, engine="swe"):
    eng = ["-eswe", f"-edir{EPHE}"] if engine == "swe" else ["-emos"]
    out = _run([*_ut_args(ut), "-p0", "-fPl", *eng])
    return float(out.strip().split()[-1])


def sun_ra(ut: datetime):
    """Apparent right ascension of the Sun in degrees (for equation of time)."""
    out = _run([*_ut_args(ut), "-p0", "-fPa", "-eswe", f"-edir{EPHE}"])
    return float(out.strip().split()[-1])


def equation_of_time_minutes(ut: datetime):
    """Apparent minus mean solar time, in minutes (Meeus 28.3, nutation term
    in RA neglected, error < 2 seconds)."""
    ut = ut.astimezone(timezone.utc)
    jd = (ut - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400
    t = jd / 36525
    l0 = (280.46646 + 36000.76983 * t + 0.0003032 * t * t) % 360
    e = l0 - 0.0057183 - sun_ra(ut)
    e = (e + 180) % 360 - 180
    return 4 * e


def sign_of(lon):
    i = int(lon // 30) % 12
    return SIGNS[i], SIGNS_ZH[i], lon - 30 * (lon // 30)


def armc_and_obliquity(ut: datetime, lat: float, lon: float):
    out = _run([*_ut_args(ut), "-p0", f"-house{lon},{lat},P", "-fPl", "-eswe", f"-edir{EPHE}"])
    armc = None
    for line in out.splitlines():
        if line.startswith("ARMC"):
            armc = float(line[16:].split()[0])
    obl = float(_run([*_ut_args(ut), "-po", "-fPl", "-eswe", f"-edir{EPHE}"]).split()[-1])
    return armc, obl


def placidus_independent(armc, obl, lat):
    """Independent implementation of MC / Asc / Placidus cusps from ARMC and
    true obliquity (used only as a cross-check of the house formulas)."""
    from math import radians as rad, degrees as deg, sin, cos, tan, asin, atan2
    e, f, R = rad(obl), rad(lat), armc

    def lam(ra):
        a = rad(ra)
        return deg(atan2(sin(a), cos(a) * cos(e))) % 360

    def dec(lmb):
        return asin(sin(e) * sin(rad(lmb)))

    mc = lam(R)
    a = rad(R)
    asc = deg(atan2(cos(a), -(sin(a) * cos(e) + tan(f) * sin(e)))) % 360

    def cusp(frac, above):
        ra = R + (frac * 90 if above else 180 - frac * 90)
        for _ in range(100):
            ad = deg(asin(max(-1, min(1, tan(f) * tan(dec(lam(ra)))))))
            if above:
                ra_new = R + frac * (90 + ad)
            else:
                ra_new = R + 180 - frac * (90 - ad)
            if abs(ra_new - ra) < 1e-10:
                break
            ra = ra_new
        return lam(ra)

    c = {10: mc, 1: asc, 11: cusp(1 / 3, True), 12: cusp(2 / 3, True),
         2: cusp(2 / 3, False), 3: cusp(1 / 3, False)}
    for k in (10, 11, 12, 1, 2, 3):
        c[(k + 6 - 1) % 12 + 1] = (c[k] + 180) % 360
    return c
