"""Reproducible per-case computation evidence and independent Skyfield maxima."""

import argparse
import json
from pathlib import Path

from app import ROOT
from evals.facts import KERNEL, bazi_boundaries, reference_charts


def verify():
    # The acceptance evidence always includes the independent check: refuse to run without it.
    if not KERNEL.is_file():
        raise FileNotFoundError(KERNEL)
    return dict(charts=reference_charts(KERNEL), bazi=bazi_boundaries())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=ROOT / "reports/week23/computations.json")
    args = p.parse_args()
    report = verify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: {f: v for f, v in data.items() if f != "results"} for k, data in report.items()},
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(0 if all(data["failed"] == 0 for data in report.values()) else 1)


if __name__ == "__main__":
    main()
