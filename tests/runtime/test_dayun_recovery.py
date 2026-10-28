"""Regression for the production 'first and current luck cycle' failure chain."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from common.facts import validate_calculation_facts
from common.schemas import Reading
from harness.models import ModelResponse, ToolCall
from plugins.bazi.intent import dayun_overview
from tests.plugins.test_astro_bazi_integration import invoke
from tests.plugins.test_name_dream_daily import with_birth

QUESTION = "根据我的出生资料，说明起运日期、首步大运与当前大运的主题。"


def birth(runtime):
    with_birth(runtime, birth_local_dt="2001-10-25 03:00", gender="male", lon=114.3)
    runtime.session.refresh_calendar(datetime(2026, 10, 29, tzinfo=UTC))


async def prepare(runtime, question=QUESTION):
    birth(runtime)
    runtime.session.append_user(question)
    assert (await invoke(runtime, "start_reading", {"question": question, "systems": ["bazi"]})).ok
    result = await invoke(runtime, "compute_bazi", {"gender": "male"})
    assert result.ok, result.error
    return result.data


def draft(runtime):
    ref = next(
        i["ref_id"]
        for i in runtime.session.state["bazi_result"]["interpretations"]
        if i["fact"].startswith("dayun:")
    )
    return dict(
        question_type="timing",
        systems_used=["bazi"],
        summary="起运日期为2007-05-05，首步大运丁酉，当前处在丙申大运的年份范围内。",
        sections=[
            dict(
                title="先认识阶段主题",
                body="可把竞争与共享作为反思线索，核对实际分工和资源边界。",
                ref_ids=[ref],
            )
        ],
        evidence=[dict(ref_id=ref)],
        advice=["把当前项目的职责和投入写清楚。"],
        confidence=dict(level="low", reason="传统文化解读"),
        safety=dict(flag=False, note=""),
    )


@pytest.mark.parametrize(
    "question", [QUESTION, "什么时候起运，第一步大运是什么？", "对比首运和当前大运的主题"]
)
def test_overview_intent(question):
    assert dayun_overview(question)


@pytest.mark.parametrize(
    "question",
    [
        "说明当前大运和明年的流月",
        "大运期间今年适合跳槽吗",
        "分析2027年财运及大运",
        "看2026-11-01至2026-11-10的大运",
        "大运怎样影响下个月",
        "当前大运的吉凶运势",
    ],
)
def test_mixed_forecast_never_uses_overview_exception(question):
    assert not dayun_overview(question)


async def test_dayun_submits_without_unrelated_flow_calculation(runtime):
    chart = await prepare(runtime)
    assert chart["dayun"]["start_solar"] == "2007-05-05"
    assert chart["dayun"]["current_candidates"][0]["ganzhi"] == "丙申"
    assert chart["dayun"]["next_transition_year"] == 2027
    assert "end_year" not in chart["dayun"]["current_candidates"][0]
    assert any(i["fact"].startswith("dayun_stem:2:丙申:") for i in chart["interpretations"])
    assert "lookup_meaning" not in [
        s["function"]["name"] for s in runtime.registry.schemas(runtime.session)
    ]
    result = await invoke(runtime, "submit_reading", draft(runtime))
    assert result.ok, result.error
    saved = runtime.store.get_reading(runtime.session.user_id, result.data["reading_id"])
    assert saved and "bazi_period_result" not in saved["calculations_json"]


async def test_overview_does_not_supply_other_system_or_forecast_evidence(runtime):
    await prepare(runtime)
    reading = Reading(**draft(runtime))
    state = deepcopy(runtime.session.state)
    state["question"] = "当前大运和明年的流年如何"
    assert validate_calculation_facts(reading, state)
    state["question"] = QUESTION
    state["question_source"] = "说明当前大运，并分析明年的流月。"
    assert validate_calculation_facts(reading, state)
    state["question_source"] = QUESTION
    state["timeframe_required"] = True
    assert validate_calculation_facts(reading, state)
    state.pop("timeframe_required")
    reading.systems_used.append("astro")
    assert validate_calculation_facts(reading, state)
    reading.systems_used = ["bazi"]
    state["bazi_result"]["dayun"] = None
    assert validate_calculation_facts(reading, state)


async def test_transition_year_returns_candidates_not_exact_handoff(runtime):
    birth(runtime)
    runtime.session.refresh_calendar(datetime(2027, 1, 1, tzinfo=UTC))
    runtime.session.append_user(QUESTION)
    await invoke(runtime, "start_reading", {"question": QUESTION, "systems": ["bazi"]})
    chart = (await invoke(runtime, "compute_bazi", {"gender": "male"})).data
    assert [s["ganzhi"] for s in chart["dayun"]["current_candidates"]] == ["丙申", "乙未"]
    assert "年份标记" in chart["dayun"]["note"]


async def test_first_cycle_comparison_keeps_primary_and_current_independent(runtime):
    chart = await prepare(runtime)
    base = dict(bazi_id=chart["bazi_id"], tz="Asia/Shanghai")
    first = await invoke(
        runtime,
        "compute_bazi_period",
        dict(**base, start="2007-01-01", end="2016-12-31", granularity="year", scope="dayun_first"),
    )
    assert first.ok, first.error
    assert not runtime.session.state.get("timeframe")
    current = await invoke(
        runtime,
        "compute_bazi_period",
        dict(**base, start="2026-10-29", end="2027-10-29", scope="dayun_current"),
    )
    assert not current.ok  # Crosses out of the current calculated cycle's labelled years.
    current = await invoke(
        runtime,
        "compute_bazi_period",
        dict(**base, start="2026-01-01", end="2026-12-31", scope="dayun_current"),
    )
    assert current.ok, current.error
    primary = await invoke(
        runtime, "compute_bazi_period", dict(**base, start="2026-01-01", end="2026-01-31")
    )
    assert primary.ok, primary.error
    assert runtime.session.state["timeframe"] == ("2026-01-01", "2026-01-31")
    assert any(s["horizon"] == "timing" for s in runtime.session.state["signals"])
    assert set(runtime.session.state["bazi_comparison_results"]) == {"dayun_first", "dayun_current"}
    mismatch = await invoke(
        runtime, "compute_bazi_period", dict(**base, start="2026-11-01", end="2026-11-30")
    )
    assert not mismatch.ok and "相同时间范围" in mismatch.error
    result = await invoke(runtime, "submit_reading", draft(runtime))
    assert result.ok, result.error
    stored = runtime.store.get_reading(runtime.session.user_id, result.data["reading_id"])[
        "calculations_json"
    ]
    assert {
        "bazi_period_dayun_first",
        "bazi_period_dayun_current",
        "bazi_period_result",
    } <= stored.keys()
    runtime.session.append_user("解释刚才的首运比较结果。")
    restored = await invoke(runtime, "read_reading", dict(reading_id=result.data["reading_id"]))
    assert restored.ok
    assert (await invoke(runtime, "submit_reading", draft(runtime))).ok


async def test_forecast_cannot_escape_user_range_with_comparison_scope(runtime):
    chart = await prepare(runtime, "看2026-11-01至2026-11-10的流年与当前大运")
    result = await invoke(
        runtime,
        "compute_bazi_period",
        dict(
            bazi_id=chart["bazi_id"],
            start="2007-01-01",
            end="2016-12-31",
            granularity="year",
            scope="dayun_first",
        ),
    )
    assert not result.ok and "必须使用primary" in result.error
    result = await invoke(
        runtime,
        "compute_bazi_period",
        dict(bazi_id=chart["bazi_id"], start="2026-11-02", end="2026-11-10"),
    )
    assert not result.ok and "指定范围一致" in result.error


@pytest.mark.parametrize(
    "start,end,granularity,limit",
    [
        ("2007-01-01", "2017-12-31", "year", 3660),
        ("2026-10-01", "2027-12-31", "month", 366),
        ("2026-10-29", "2016-12-31", "month", 366),
    ],
)
async def test_incident_ranges_fail_before_calculation_not_as_needs_input(
    runtime, start, end, granularity, limit
):
    chart = await prepare(runtime)
    result = await invoke(
        runtime,
        "compute_bazi_period",
        dict(bazi_id=chart["bazi_id"], start=start, end=end, granularity=granularity),
    )
    assert not result.ok and str(limit) in result.error
    assert result.data.get("status") != "needs_input"
    assert "bazi_period_result" not in runtime.session.state


async def test_lookup_failure_provides_real_versioned_candidates(runtime):
    await prepare(runtime)
    result = await invoke(
        runtime, "lookup_meaning", dict(system="bazi", kind="element_relation", key="金克木")
    )
    assert not result.ok
    candidates = runtime.kb.suggested_keys("bazi", "element_relation", "金克木")
    assert candidates and all(
        runtime.kb.lookup("bazi", "element_relation", key) for key in candidates
    )
    assert all(key in result.error for key in candidates)


async def test_whole_turn_finishes_under_original_twelve_step_limit(runtime):
    birth(runtime)

    class DayunModel:
        calls = 0

        async def chat(self, messages, tools):
            self.calls += 1
            name, args = (
                ("start_reading", {"question": QUESTION, "systems": ["bazi"]})
                if self.calls == 1
                else ("compute_bazi", {"gender": "male"})
                if self.calls == 2
                else ("submit_reading", draft(runtime))
            )
            return ModelResponse(
                input_tokens=100,
                output_tokens=100,
                tool_calls=[ToolCall(id=str(self.calls), name=name, arguments=args)],
            )

    model = DayunModel()
    runtime.model = model
    result = await runtime.turn(QUESTION)
    assert result.status == "submit_reading", result.text
    assert model.calls == 3 and runtime.max_steps == 12
    assert result.data["reading"]["evidence"]
