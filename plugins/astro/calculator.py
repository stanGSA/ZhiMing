import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

import swisseph as swe

from common.time_utils import NeedsInput, date_range, local_instant

EPHE = Path(__file__).resolve().parents[2] / "data/ephe"
BODIES = dict(
    zip(
        (
            "Sun",
            "Moon",
            "Mercury",
            "Venus",
            "Mars",
            "Jupiter",
            "Saturn",
            "Uranus",
            "Neptune",
            "Pluto",
        ),
        range(10),
        strict=True,
    )
)
BODY_ZH = dict(
    zip(
        BODIES,
        ("太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"),
        strict=True,
    )
)
SIGNS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
SIGN_ZH = (
    "白羊",
    "金牛",
    "双子",
    "巨蟹",
    "狮子",
    "处女",
    "天秤",
    "天蝎",
    "射手",
    "摩羯",
    "水瓶",
    "双鱼",
)
ASPECTS = {
    "conjunction": (0, 8),
    "opposition": (180, 8),
    "trine": (120, 8),
    "square": (90, 7),
    "sextile": (60, 5),
}
NATIVE_LOCK = RLock()


@lru_cache(maxsize=4)
def native_path(directory, signatures):
    """Swiss fopen needs an ASCII path on Windows; never change process cwd."""
    path = str(directory)
    if os.name != "nt" or path.isascii():
        return path
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    if (
        ctypes.windll.kernel32.GetShortPathNameW(path, buffer, len(buffer))
        and buffer.value.isascii()
    ):
        return buffer.value
    # Volumes with 8.3 names disabled need an isolated content-addressed native cache.
    parent = Path(tempfile.gettempdir()) / "zhiming-ephemeris"
    if not str(parent).isascii():
        raise RuntimeError(
            "Swiss requires an ASCII temporary directory when short paths are disabled"
        )
    digest = hashlib.sha256()
    sources = list(directory.glob("*.se1"))
    for source in sources:
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    target = parent / digest.hexdigest()
    target.mkdir(parents=True, exist_ok=True)
    for source in sources:
        destination = target / source.name
        if not destination.exists() or destination.read_bytes() != source.read_bytes():
            shutil.copyfile(source, destination)
    return str(target)


@contextmanager
def ephemeris_path():
    with NATIVE_LOCK:
        signatures = tuple(
            (p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in EPHE.glob("*.se1")
        )
        swe.set_ephe_path(native_path(EPHE, signatures))
        yield


def angular_delta(a, b):
    return (a - b + 180) % 360 - 180


def julian(utc):
    return swe.utc_to_jd(
        utc.year,
        utc.month,
        utc.day,
        utc.hour,
        utc.minute,
        utc.second + utc.microsecond / 1e6,
        swe.GREG_CAL,
    )


def position(tt, body):
    with ephemeris_path():
        coordinates, flags = swe.calc(tt, BODIES[body], swe.FLG_SWIEPH | swe.FLG_SPEED)
    if not flags & swe.FLG_SWIEPH:
        raise RuntimeError("Required Swiss ephemeris data missing; refusing silent fallback")
    return coordinates


def natal_chart(
    birth_local: str,
    tz: str,
    lat: float,
    lon: float,
    time_known: bool = True,
    fold: int | None = None,
):
    if not -90 < lat < 90 or not -180 <= lon <= 180:
        raise NeedsInput("invalid_coordinates", "请确认有效的出生经纬度。")
    if time_known and len(birth_local) <= 10:
        raise NeedsInput("missing_birth_time", "请补充出生钟表时间；若不知道请明确说明。")
    local = birth_local if time_known else birth_local[:10] + "T12:00:00"
    utc = local_instant(local, tz, fold)
    if not 1800 <= utc.year <= 2399:
        raise NeedsInput("ephemeris_range", "当前星历支持1800–2399年，请确认出生日期。")
    tt, ut1 = julian(utc)
    cusps, axes, house_system, warnings = None, None, None, []
    if time_known:
        try:
            c, a = swe.houses_ex(ut1, lat, lon, b"P")
            house_system = "Placidus"
        except swe.Error:
            c, a = swe.houses_ex(ut1, lat, lon, b"O")
            house_system = "Porphyry (fallback)"
            warnings.append("高纬度Placidus无定义，回退Porphyry宫制。")
        cusps = {i + 1: v for i, v in enumerate(c)}
        axes = dict(asc=a[0], mc=a[1], dsc=(a[0] + 180) % 360, ic=(a[1] + 180) % 360)
    else:
        warnings.append(
            "出生时间未知：中午12点为计算代理，宫位与四轴不可用；月亮与临界落座及精确行运日期存在时间不确定性。"
        )
    planets = []
    for body in BODIES:
        p = position(tt, body)
        house = None
        if cusps:
            house = next(
                i
                for i in range(1, 13)
                if (p[0] - cusps[i]) % 360 < (cusps[i % 12 + 1] - cusps[i]) % 360
            )
        sign = int(p[0] // 30)
        planets.append(
            dict(
                body=body,
                body_zh=BODY_ZH[body],
                lon=p[0],
                sign=SIGNS[sign],
                sign_zh=SIGN_ZH[sign],
                deg_in_sign=p[0] % 30,
                speed_deg_per_day=p[3],
                retrograde=p[3] < 0,
                house=house,
            )
        )
    aspects = []
    for a, b in combinations(planets, 2):
        angle = abs(angular_delta(a["lon"], b["lon"]))
        for name, (target, orb) in ASPECTS.items():
            if abs(angle - target) <= orb:
                aspects.append(
                    dict(a=a["body"], b=b["body"], type=name, angle=angle, orb=abs(angle - target))
                )
    return dict(
        planets=planets,
        cusps=cusps,
        axes=axes,
        house_system=house_system,
        asc=None
        if axes is None
        else dict(lon=axes["asc"], sign_zh=SIGN_ZH[int(axes["asc"] // 30)]),
        mc=None if axes is None else dict(lon=axes["mc"], sign_zh=SIGN_ZH[int(axes["mc"] // 30)]),
        aspects=aspects,
        utc=utc.isoformat(),
        jd_tt=tt,
        jd_ut1=ut1,
        time_known=time_known,
        uncertainty=warnings,
        input=dict(
            birth_local=birth_local, tz=tz, lat=lat, lon=lon, time_known=time_known, fold=fold
        ),
        convention="Swiss Ephemeris; geocentric apparent tropical longitude of date; TT for positions / UT1 houses",
    )


def bisect_root(function, a, b):
    fa = function(a)
    for _ in range(45):
        mid = (a + b) / 2
        fm = function(mid)
        if fa * fm <= 0:
            b = mid
        else:
            a, fa = mid, fm
    return (a + b) / 2


def transits(
    chart: dict,
    start: str,
    end: str,
    tz: str = "Asia/Shanghai",
    orb: float = 1.0,
    bodies: list[str] | None = None,
):
    a, b = date_range(start, end, tz, 3660)
    ta, tb = julian(a)[0], julian(b)[0]
    bodies = bodies or list(BODIES)
    if not 0 < orb <= 8 or not set(bodies) <= set(BODIES):
        raise NeedsInput("invalid_transits", "请确认行运行星及容许度（0至8度）。")
    # Six-hour samples limit lunar movement to <4 degrees; unwrap with discontinuity rejection.
    grid = [ta + i * 0.25 for i in range(int((tb - ta) / 0.25) + 1)]
    if grid[-1] < tb:
        grid.append(tb)
    events = []
    for body in bodies:
        coordinates = [position(t, body) for t in grid]
        stations = []
        for i in range(len(grid) - 1):
            if coordinates[i][3] * coordinates[i + 1][3] < 0:
                stations.append(
                    bisect_root(lambda t, body=body: position(t, body)[3], grid[i], grid[i + 1])
                )
        body_grid = sorted(set(grid + stations))
        sample_map = {t: p[0] for t, p in zip(grid, coordinates, strict=True)}
        sample_map.update({t: position(t, body)[0] for t in stations})
        samples = [sample_map[t] for t in body_grid]
        for natal in chart["planets"]:
            for aspect, (angle, _) in ASPECTS.items():
                for signed in {angle, -angle} if angle not in (0, 180) else {angle}:
                    target = (natal["lon"] + signed) % 360
                    residuals = [angular_delta(x, target) for x in samples]
                    roots = []
                    for i in range(len(body_grid) - 1):
                        left, right = residuals[i : i + 2]
                        if abs(left - right) < 180 and left * right <= 0:
                            roots.append(
                                bisect_root(
                                    lambda t, body=body, target=target: angular_delta(
                                        position(t, body)[0], target
                                    ),
                                    body_grid[i],
                                    body_grid[i + 1],
                                )
                            )
                    # Also detect a station touching the exact angle without a sign crossing.
                    for station in stations:
                        if abs(angular_delta(sample_map[station], target)) < 1e-7:
                            roots.append(station)
                    unique = []
                    for root in sorted(roots):
                        if not ta <= root < tb or any(abs(root - r) < 1e-5 for r in unique):
                            continue
                        unique.append(root)
                        fields = swe.jdet_to_utc(root)
                        sec = fields[5]
                        utc = datetime(*fields[:5], tzinfo=UTC) + timedelta(seconds=sec)
                        events.append(
                            dict(
                                transit_body=body,
                                natal_body=natal["body"],
                                aspect=aspect,
                                exact_utc=utc.isoformat(),
                                exact_date=utc.astimezone(ZoneInfo(tz)).date().isoformat(),
                                orb_deg=abs(angular_delta(position(root, body)[0], target)),
                                allowed_orb_deg=orb,
                                speed_deg_per_day=position(root, body)[3],
                                natal_lon=natal["lon"],
                                natal_sign=natal["sign_zh"],
                                natal_house=natal["house"],
                                jd_tt=root,
                                time_uncertain=not chart["time_known"],
                            )
                        )
    events.sort(key=lambda e: (e["exact_utc"], e["transit_body"], e["natal_body"], e["aspect"]))
    return dict(
        chart_id=chart.get("chart_id"),
        start=start,
        end=end,
        tz=tz,
        events=events,
        uncertainty=chart["uncertainty"],
        interval="date end inclusive; datetime end exclusive",
        event_definition="exact aspect crossings/touches in range; orb_deg is residual at exact time, allowed_orb_deg is interpretation tolerance",
    )
