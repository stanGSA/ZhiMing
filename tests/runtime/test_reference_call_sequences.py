"""The correct calls for each P1 question pass the Guard (P0.2 of docs/根因整改实施计划.md).

P1 recorded 122 provenance errors ("C" categories) in Final-single. Replaying the calls a correct
agent makes for the same questions shows whether those came from the Guard being stricter than
its own rules or from the model's calls: the reference sequences below pass, so they were the
model's. The same sequences are what the pipeline's planner (P3) is meant to emit.
"""

import pytest

from scripts.live_week23 import CASES, NATURAL_CASES
from tests.plugins.test_astro_bazi_integration import invoke

QUESTIONS = {case["id"]: case for case in CASES + NATURAL_CASES}
NOVEMBER = ("2026-11-01", "2026-11-30")
NEW_YORK = ("纽约", "1995-12-31 23:45")
BEIJING = ("北京", "1993-08-17 23:20")
UNKNOWN_TIME = ("北京", "1998-04-12")
# question id -> (place to resolve, birth clock, time known, gender, date range)
REFERENCE = {
    "astro_trait": (*NEW_YORK, True, None, None),
    "bazi_trait": (*BEIJING, True, "male", None),
    "bazi_timing": (*BEIJING, True, "male", NOVEMBER),
    "three_system_timing": (*BEIJING, True, "male", NOVEMBER),
    "unknown_time": (*UNKNOWN_TIME, False, None, None),
    "investment_new": (*BEIJING, True, "male", None),
    "natural_astro": (*BEIJING, True, None, None),
    "natural_bazi": (*BEIJING, True, "male", None),
    "range_before_birth": (*BEIJING, True, "male", NOVEMBER),
    "overseas_bazi": (*NEW_YORK, True, "male", None),
    "natural_unknown": (*UNKNOWN_TIME, False, None, None),
}


def outcome(result) -> str:
    if not result.ok:
        return "error: " + str(result.error)
    data = result.data or {}
    return "needs_input: " + data["code"] if data.get("status") == "needs_input" else "ok"


async def replay(runtime, case_id, place, birth_local, time_known, gender, date_range):
    """Run the reference calls in order; returns [(tool, outcome)]."""
    case = QUESTIONS[case_id]
    runtime.session.calendar_anchor = "2026-10-30"
    runtime.session.append_user(case["question"])
    if case.get("clarification"):
        runtime.session.append_user(case["clarification"])
    log = []

    async def call(name, args):
        result = await invoke(runtime, name, args)
        log.append((name, outcome(result)))
        return result

    await call("start_reading", dict(question=case["question"], systems=sorted(case["systems"])))
    location = await call("resolve_location", dict(query=place))
    birth = dict(
        birth_local=birth_local,
        location_id=location.data["location"]["location_id"],
        time_known=time_known,
    )
    if "astro" in case["systems"]:
        chart = await call("compute_natal_chart", birth)
        if date_range and chart.ok:
            await call(
                "compute_transits",
                dict(chart_id=chart.data["chart_id"], start=date_range[0], end=date_range[1]),
            )
    if "bazi" in case["systems"]:
        bazi = await call("compute_bazi", {**birth, **({"gender": gender} if gender else {})})
        if date_range and bazi.ok:
            await call(
                "compute_bazi_period",
                dict(
                    bazi_id=bazi.data["bazi_id"],
                    start=date_range[0],
                    end=date_range[1],
                    granularity="month",
                ),
            )
    if "tarot" in case["systems"]:
        await call("draw_tarot", dict(spread="three_card", question=case["question"]))
    return log


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
async def test_reference_calls_pass_the_guard(runtime, case_id):
    log = await replay(runtime, case_id, *REFERENCE[case_id])
    assert [step for step in log if step[1] != "ok"] == []
    expected = {tool for tool in QUESTIONS[case_id]["tools"] if tool != "submit_reading"}
    assert expected <= {tool for tool, _ in log}


async def test_overseas_range_asks_which_city_the_dates_follow(runtime):
    # P1 expects astro_timing to be answered directly; the code instead asks which city's dates
    # the range follows, because a birthplace is not where the user lives now (9a626a5). The
    # pipeline's requirements table (P3) has to settle this one way, with the evaluation.
    log = await replay(runtime, "astro_timing", *NEW_YORK, True, None, NOVEMBER)
    assert log[-1] == ("compute_transits", "needs_input: confirm_period_timezone")
    assert all(result == "ok" for _, result in log[:-1])
