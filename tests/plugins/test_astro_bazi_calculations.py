from datetime import timedelta

import pytest
import yaml
from skyfield.api import Loader, load_file

from app import ROOT
from common.location import Gazetteer, LocationInput
from common.time_utils import NeedsInput, local_instant
from plugins.astro.calculator import ASPECTS, angular_delta, natal_chart, position, transits
from plugins.bazi.calculator import bazi_period, compute_bazi, relations, ten_god, terms

CHARTS = yaml.safe_load((ROOT / "evals/cases/reference_charts.yaml").read_text(encoding="utf-8"))[
    "cases"
]
BAZI = yaml.safe_load((ROOT / "evals/cases/bazi_boundary.yaml").read_text(encoding="utf-8"))[
    "cases"
]


def chart_input(case):
    return {k: v for k, v in case["input"].items() if k != "place"}


def bazi_input(case):
    d = case["input"]
    args = dict(
        birth_local=d["birth_local_clock"],
        tz=d["tz"],
        lon=d["lon"],
        gender=d.get("gender"),
        time_known=d["time_known"],
        true_solar_time=d["true_solar_time"],
    )
    if d["calendar"] == "lunar":
        args.update(
            birth_local=None,
            calendar="lunar",
            lunar_date=d["lunar_date"],
            calendar_confirmed=True,
            leap_month="闰" in d["lunar_date"],
        )
    return args


@pytest.mark.parametrize("case", CHARTS, ids=lambda c: c["id"])
def test_all_reference_charts(case):
    chart = natal_chart(**chart_input(case))
    expected = case["expected"]
    for actual, ref in zip(chart["planets"], expected["planets"], strict=True):
        assert actual["body"] == ref["body"]
        assert abs(angular_delta(actual["lon"], ref["lon"])) < 0.01
        assert actual["sign"] == ref["sign"]
        assert actual["retrograde"] == ref["retrograde"]
        assert actual["house"] == ref.get("house")
        assert abs(actual["speed_deg_per_day"] - ref["speed_deg_per_day"]) < 0.001
    if expected.get("cusps") is None:
        assert chart["axes"] is None and chart["cusps"] is None
        assert chart["asc"] is None and chart["mc"] is None
    else:
        assert chart["house_system"] == expected["house_system"]
        for house, value in expected["cusps"].items():
            assert abs(angular_delta(chart["cusps"][house], value)) < 0.01
        for axis in ("asc", "mc"):
            assert abs(angular_delta(chart[axis]["lon"], expected[axis]["lon"])) < 0.01
    assert {(a["a"], a["b"], a["type"]) for a in chart["aspects"]} == {
        (a["a"], a["b"], a["type"]) for a in expected["aspects"]
    }


@pytest.fixture(scope="module")
def skyfield():
    loader = Loader(str(ROOT / "data/skyfield"))
    ts = loader.timescale(builtin=True)
    kernel = load_file(str(ROOT / "data/ephe/de440s.bsp"))
    yield ts, kernel
    kernel.close()


@pytest.mark.parametrize("case", CHARTS, ids=lambda c: c["id"])
def test_independent_skyfield_all_planets(case, skyfield):
    ts, kernel = skyfield
    chart = natal_chart(**chart_input(case))
    # Identical TT instant, Earth center, apparent tropical ecliptic/equinox of date.
    # Skyfield/JPL light time/aberration/nutation are independent of Swiss positions.
    t = ts.tt_jd(chart["jd_tt"])
    earth = kernel["earth"].at(t)
    for planet in chart["planets"]:
        name = planet["body"].lower()
        body = kernel[name if name in ("sun", "moon") else name + " barycenter"]
        longitude = earth.observe(body).apparent().ecliptic_latlon(epoch=t)[1].degrees
        assert abs(angular_delta(longitude, planet["lon"])) < 0.01, (
            case["id"],
            name,
            longitude,
            planet["lon"],
        )


@pytest.mark.parametrize("case", BAZI, ids=lambda c: c["id"])
def test_all_bazi_boundaries(case):
    expected = case["expected"]
    if expected.get("error") or case.get("expected_behavior"):
        code = expected.get("error") or "unknown_time_at_term"
        with pytest.raises(NeedsInput) as error:
            compute_bazi(**bazi_input(case))
        assert error.value.code == code
        if code == "unknown_time_at_term":
            result = compute_bazi(**bazi_input(case), accept_uncertain=True)
            assert len(result["alternatives"]) >= 2
            assert result["pillars"]["year"] is None and result["pillars"]["month"] is None
        return
    variants = expected.get("by_zishi_rule", {"next_day": expected})
    for rule, reference in variants.items():
        result = compute_bazi(**bazi_input(case), zishi_rule=rule)
        for key, value in reference.items():
            assert result[key] == value, (case["id"], rule, key, result[key], value)
        if not case["input"]["time_known"]:
            assert "time" not in result["pillars"] and result["dayun"] is None


@pytest.mark.parametrize(
    "local,tz,code",
    [
        ("1986-05-04 02:30", "Asia/Shanghai", "nonexistent_local_time"),
        ("1986-09-14 01:30", "Asia/Shanghai", "ambiguous_local_time"),
        ("2024-03-10 02:30", "America/New_York", "nonexistent_local_time"),
        ("2024-11-03 01:30", "America/New_York", "ambiguous_local_time"),
    ],
)
def test_gap_fold(local, tz, code):
    with pytest.raises(NeedsInput) as exc:
        local_instant(local, tz)
    assert exc.value.code == code


def test_fold_candidates_and_historical_dst():
    a = local_instant("1986-09-14 01:30", "Asia/Shanghai", 0)
    b = local_instant("1986-09-14 01:30", "Asia/Shanghai", 1)
    assert b - a == timedelta(hours=1)
    assert (
        local_instant("1987-06-15 08:30", "Asia/Shanghai").isoformat()
        == "1987-06-14T23:30:00+00:00"
    )


def test_location_aliases_ambiguity():
    geo = Gazetteer()
    a = geo.resolve(LocationInput(query="北京市"))
    b = geo.resolve(LocationInput(query="Beijing"))
    assert a["status"] == b["status"] == "resolved"
    assert a["location"]["location_id"] == b["location"]["location_id"]
    assert a["location"]["tz"] == "Asia/Shanghai"
    ambiguous = geo.resolve(LocationInput(query="Springfield"))
    assert ambiguous["status"] == "needs_input" and len(ambiguous["candidates"]) > 1
    assert geo.resolve(LocationInput(query="不存在的城000"))["status"] == "needs_input"


def test_missing_time_gender_lunar_confirmation():
    result = compute_bazi("1998-04-12", "Asia/Shanghai", 116.4, time_known=False)
    assert len(result["pillars"]) == 3 and result["dayun"] is None
    assert compute_bazi("1998-04-12 09:30", "Asia/Shanghai", 116.4)["dayun"] is None
    with pytest.raises(NeedsInput) as exc:
        compute_bazi(
            None, "Asia/Shanghai", 116.4, calendar="lunar", lunar_date="2023年二月十五 10:00"
        )
    assert exc.value.code == "confirm_calendar"
    with pytest.raises(NeedsInput) as exc:
        compute_bazi(
            None,
            "Asia/Shanghai",
            116.4,
            calendar="lunar",
            lunar_date="2023年二月十五 10:00",
            calendar_confirmed=True,
        )
    assert exc.value.code == "confirm_leap_month"


def test_transits_roots_retrograde_and_range():
    chart = natal_chart("1995-12-31 23:45", "America/New_York", 40.7128, -74.006)
    result = transits(chart, "2026-11-01", "2026-11-30", bodies=["Mercury", "Saturn"])
    assert result["events"]
    for event in result["events"]:
        assert "2026-11-01" <= event["exact_date"] <= "2026-11-30"
        separation = abs(
            angular_delta(position(event["jd_tt"], event["transit_body"])[0], event["natal_lon"])
        )
        assert abs(separation - ASPECTS[event["aspect"]][0]) < 1e-6
        assert event["orb_deg"] < 1e-6
        assert event["natal_house"] == next(
            p["house"] for p in chart["planets"] if p["body"] == event["natal_body"]
        )
    duplicate_groups = {}
    for event in result["events"]:
        k = (event["transit_body"], event["natal_body"], event["aspect"])
        duplicate_groups.setdefault(k, []).append(event["exact_utc"])
    assert any(len(v) > 1 for v in duplicate_groups.values())
    unknown = natal_chart("1990-07-07", "Asia/Shanghai", 30.57, 104.06, False)
    assert all(
        e["natal_house"] is None and e["time_uncertain"]
        for e in transits(unknown, "2026-11-01", "2026-11-02", bodies=["Moon"])["events"]
    )


@pytest.mark.parametrize("granularity", ["year", "month", "day"])
def test_period_boundaries_and_relationships(granularity):
    chart = compute_bazi("1993-08-17 23:20", "Asia/Shanghai", 116.4, "male")
    result = bazi_period(chart, "2024-02-03", "2024-02-05", granularity)
    assert result["periods"][0]["pillars"]["year"] == "癸卯"
    assert result["periods"][-1]["pillars"]["year"] == "甲辰"
    for left, right in zip(result["periods"][:-1], result["periods"][1:], strict=True):
        assert left["end_utc"] == right["start_utc"]
    for p in result["periods"]:
        for k, gz in p["pillars"].items():
            assert p["ten_gods"][k] == ten_god(chart["day_master"][0], gz[0])
    assert any(r["type"] == "地支冲" for r in relations("甲子", {"day": "庚午"}))
    month = bazi_period(chart, "2026-11-01", "2026-11-30", "month")
    assert [p["pillars"]["month"] for p in month["periods"]] == ["戊戌", "己亥"]


def test_true_solar_never_moves_physical_term():
    # Shanghai true-solar correction moves civil time across Li Chun, not the physical Sun.
    t = terms(2024)[1]
    civil = (t - timedelta(minutes=5)).replace(tzinfo=None).isoformat(sep=" ")
    off = compute_bazi(civil, "Asia/Shanghai", 150, true_solar_time=False)
    on = compute_bazi(civil, "Asia/Shanghai", 150, true_solar_time=True)
    assert off["pillars"]["year"] == on["pillars"]["year"] == "癸卯"
    assert off["pillars"]["month"] == on["pillars"]["month"] == "乙丑"


def test_dayun_uses_physical_terms_when_solar_clock_crosses_lichun():
    clock = (terms(2024)[1] - timedelta(minutes=5)).replace(tzinfo=None).isoformat(sep=" ")
    off = compute_bazi(clock, "Asia/Shanghai", 150, "male", dayun_time_basis="physical")
    with pytest.raises(NeedsInput, match="真太阳时钟表修正跨过节气"):
        compute_bazi(clock, "Asia/Shanghai", 150, "male", true_solar_time=True)
    on = compute_bazi(
        clock, "Asia/Shanghai", 150, "male", true_solar_time=True, dayun_time_basis="physical"
    )
    assert off["dayun"] == on["dayun"]
    assert on["dayun"]["forward"] is False
    assert on["dayun"]["sequence"][0]["ganzhi"] == "甲子"


def test_ten_year_transit_range():
    chart = natal_chart("1995-12-31 23:45", "America/New_York", 40.7128, -74.006)
    result = transits(chart, "2026-01-01", "2035-12-31", bodies=["Saturn"])
    assert result["events"]
    assert all("2026-01-01" <= e["exact_date"] <= "2035-12-31" for e in result["events"])
    assert max(e["orb_deg"] for e in result["events"]) < 1e-6
