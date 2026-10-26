"""Per-case checks of the two computed datasets: reference charts and bazi boundaries.

Shared by the week 2/3 acceptance script (scripts.archive.verify_week23) and the evaluation
summary (evals.report), so both report the same pass criteria. The Skyfield/JPL cross-check
needs data/ephe/de440s.bsp; without it the charts are compared with the dataset only and the
Skyfield columns are None.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app import ROOT
from common.time_utils import NeedsInput
from plugins.astro.calculator import angular_delta, natal_chart
from plugins.bazi.calculator import compute_bazi

KERNEL = ROOT / "data/ephe/de440s.bsp"
FRAME = "Common TT; Earth-center apparent tropical ecliptic/equinox of date; Swiss vs independent Skyfield/JPL DE440s; barycenters for planets, Moon/Sun centers."


def reference_charts(kernel_path: Path | None = KERNEL) -> dict:
    cases = yaml.safe_load(
        (ROOT / "evals/cases/reference_charts.yaml").read_text(encoding="utf-8")
    )["cases"]
    kernel = None
    if kernel_path is not None and kernel_path.is_file():
        from skyfield.api import Loader, load_file

        ts = Loader(str(ROOT / "data/skyfield")).timescale(builtin=True)
        kernel = load_file(str(kernel_path))
    charts = []
    try:
        for case in cases:
            actual = natal_chart(**{k: v for k, v in case["input"].items() if k != "place"})
            reference_errors = [
                abs(angular_delta(p["lon"], r["lon"]))
                for p, r in zip(actual["planets"], case["expected"]["planets"], strict=True)
            ]
            sky_errors = []
            if kernel is not None:
                time = ts.tt_jd(actual["jd_tt"])
                earth = kernel["earth"].at(time)
                for p in actual["planets"]:
                    name = p["body"].lower()
                    lon = (
                        earth.observe(
                            kernel[name if name in ("sun", "moon") else name + " barycenter"]
                        )
                        .apparent()
                        .ecliptic_latlon(epoch=time)[1]
                        .degrees
                    )
                    sky_errors.append(float(abs(angular_delta(lon, p["lon"]))))
            charts.append(
                dict(
                    id=case["id"],
                    max_reference_error_deg=max(reference_errors),
                    max_skyfield_error_deg=max(sky_errors) if sky_errors else None,
                    passed=max(reference_errors) < 0.01
                    and (kernel is None or max(sky_errors) < 0.01),
                    planet_count=len(reference_errors),
                )
            )
    finally:
        if kernel is not None:
            kernel.close()
    return dict(
        cases=len(charts),
        passed=sum(r["passed"] for r in charts),
        failed=sum(not r["passed"] for r in charts),
        skipped=0,
        max_reference_error_deg=max(r["max_reference_error_deg"] for r in charts),
        max_skyfield_error_deg=max(r["max_skyfield_error_deg"] for r in charts)
        if kernel is not None
        else None,
        frame=FRAME,
        results=charts,
    )


def bazi_boundaries() -> dict:
    cases = yaml.safe_load((ROOT / "evals/cases/bazi_boundary.yaml").read_text(encoding="utf-8"))[
        "cases"
    ]
    bazi = []
    for case in cases:
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
        expected = case["expected"]
        variants = []
        for rule, ref in expected.get("by_zishi_rule", {"next_day": expected}).items():
            try:
                result = compute_bazi(**args, zishi_rule=rule)
                mismatches = [key for key, value in ref.items() if result.get(key) != value]
                variants.append(
                    dict(rule=rule, passed=not mismatches, mismatched_fields=mismatches)
                )
            except NeedsInput as exc:
                expected_code = ref.get("error") or (
                    "unknown_time_at_term" if case.get("expected_behavior") else None
                )
                variants.append(
                    dict(
                        rule=rule,
                        passed=exc.code == expected_code,
                        behavior=exc.code,
                        expected_behavior=expected_code,
                    )
                )
        bazi.append(
            dict(
                id=case["id"],
                category=case["category"],
                passed=all(r["passed"] for r in variants),
                variants=variants,
            )
        )
    return dict(
        cases=len(bazi),
        variants=sum(len(r["variants"]) for r in bazi),
        passed=sum(r["passed"] for r in bazi),
        failed=sum(not r["passed"] for r in bazi),
        skipped=0,
        results=bazi,
    )
