"""Serial latency baseline and screenshot regression scenarios; preserve every attempt."""

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

from app import ROOT
from scripts.live_week23 import CASES, NATURAL_CASES, evaluate

SCREENSHOT_CASES = [
    dict(
        id="la_clock_confirmation",
        question="合成资料：男性，公历1990年6月15日下午5点整，美国洛杉矶出生，是当地钟表时间。用八字告诉我日主和日柱。",
        clarification="不用真太阳时，按固定UTC+8，23点换日。请继续回答原问题。",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="la_solar_confirmed",
        question="合成资料：男性，公历1990年6月15日下午5点整，美国洛杉矶出生，是当地钟表时间。按真太阳时、23点换日，用八字告诉我日主和日柱。",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="la_consultation_confirmation",
        question="合成资料：男性，公历1990-06-15 17:00，美国洛杉矶出生，当地钟表时间。八字不用真太阳时，23点换日。分析2026年11月是否适合开始求职，计算流月并给条件建议。",
        clarification="我现在住在洛杉矶，咨询按洛杉矶时间。请继续回答原问题。",
        tools={"compute_bazi", "compute_bazi_period", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="month_after_next",
        question="合成资料：男性，公历1993-08-17 23:20，北京出生，不用真太阳时，23点换日。用八字看下下个月适合开始求职吗？计算流月，给条件建议。",
        tools={"compute_bazi", "compute_bazi_period", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="quarter_clock",
        question="合成资料：公历1993年8月17日下午3点一刻，北京出生。只用占星看看适合怎样的工作方式。",
        tools={"compute_natal_chart", "submit_reading"},
        systems={"astro"},
    ),
    dict(
        id="imprecise_clock",
        question="合成资料：公历1993年8月17日，北京出生，只知道是早上8点多。用占星分析工作方式。",
        tools={"ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="province_confirmation",
        question="合成资料：公历1993年8月17日15:15，长沙出生。只用占星看看工作方式。",
        clarification="湖南省的长沙，出生时刻准确。请继续回答原问题。",
        tools={"resolve_location", "compute_natal_chart", "submit_reading"},
        systems={"astro"},
    ),
]


async def run(suite, output, mode="single"):
    names = [c["id"] for c in (CASES + NATURAL_CASES if suite == "baseline" else SCREENSHOT_CASES)]
    if suite == "screenshots":
        NATURAL_CASES.extend(SCREENSHOT_CASES)
        # Re-run original questions unchanged after the observed answer/reviewer failures.
        names.extend(["range_before_birth", "overseas_bazi"])
    started = time.perf_counter()
    result = await evaluate(output, names, judge=True, natural=True, mode=mode)
    latencies = sorted(r["latency_s"] for r in result["results"])
    result["latency_baseline"] = dict(
        suite=suite,
        mode=mode,
        concurrency=1,
        cases=len(latencies),
        median_s=round(statistics.median(latencies), 3),
        p95_nearest_rank_s=latencies[math.ceil(0.95 * len(latencies)) - 1],
        max_s=max(latencies),
        wall_s=round(time.perf_counter() - started, 3),
        measurement="Dialogue wall time including clarification; excludes rubric judge, setup and knowledge build. Wall time includes all phases.",
        comparison="Descriptive baseline only; previous concurrent batch has different source and service conditions, so no causal speedup claim.",
    )
    path = output / result["run_id"] / "serial-summary.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["latency_baseline"], ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["baseline", "screenshots"], default="baseline")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/v2-followup/serial")
    parser.add_argument("--mode", choices=["single", "multi"], default="single")
    args = parser.parse_args()
    result = asyncio.run(run(args.suite, args.output, args.mode))
    raise SystemExit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
