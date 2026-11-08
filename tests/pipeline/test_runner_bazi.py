"""Bazi through the pipeline with scripted models (P3 of the plan)."""

import re
from datetime import UTC, datetime

import pytest

from app import create_runtime
from pipeline import requirements
from pipeline.bazi import ASK_GENDER, Bazi
from pipeline.runner import PipelineRunner
from tests.pipeline.drafts import Composer

CLOCK = datetime(2026, 10, 30, 4, 0, tzinfo=UTC)  # noon in Shanghai, 2026-10-30
SHANGHAI = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 31.23,
    "lon": 121.47,
    "birth_place": "上海",
    "time_known": True,
    "gender": "female",
}
LOS_ANGELES = {
    **SHANGHAI,
    "tz": "America/Los_Angeles",
    "lat": 34.05,
    "lon": -118.24,
    "birth_place": "洛杉矶",
}
TRAIT = "看看我的八字，我是什么性格？"
DAYUN = "帮我看看八字的大运，我什么时候起运？"
NEXT_MONTH = "用八字看看我下个月的事业运。"
LINE = re.compile(r"^(R\d+)｜(\S+?)｜(.+?)｜关键词", re.M)


def facts_in(messages) -> list[tuple[str, str, str]]:
    return LINE.findall(messages[1]["content"])


def aliases(messages, label: str) -> list[str]:
    return [alias for alias, lab, _ in facts_in(messages) if lab == label]


def written(messages, extra="") -> str:
    facts = facts_in(messages)
    timing = [a for a, label, _ in facts if label in ("流年", "流月", "流日")]
    natal = [a for a, label, _ in facts if label in ("日主", "四柱", "大运")]
    first = timing[0] if timing else natal[0]
    second = natal[0]
    return (
        "【表态】平稳\n【摘要】整体平稳，适合按计划推进。留意沟通节奏。\n"
        f"【分层】这段时间的节奏\n{{{{{first}}}}}提示你把精力放在长期目标上。{extra}\n【引用】{first}\n"
        f"【分层】你的底色\n{{{{{second}}}}}说明你做事偏稳，往往先观察再行动。\n【引用】{second}\n"
        "【建议】\n- 先排序：把最重要的两件事写下来。\n【收尾】按自己的节奏来。"
    )


def builder(project, runtimes):
    """A runtime factory for these tests; the runtimes it makes are closed by the fixture."""

    def build(*replies, user_id="bazi-user", birth=SHANGHAI, selected=None):
        composer = Composer(*replies)
        runtime = create_runtime(
            root=project,
            user_id=user_id,
            seed=7,
            model=composer,
            mode="pipeline",
            clock=lambda: CLOCK,
        )
        if birth:
            runtime.store.update_profile_fields(user_id, birth, "合成测试资料")
            runtime.session.profile = runtime.store.get_profile(user_id)
        runtime.session.refresh_calendar(CLOCK)
        if selected:
            runtime.session.state["selected_systems"] = selected
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    return build


@pytest.fixture
def make(project):
    runtimes = []
    yield builder(project, runtimes)
    for runtime in runtimes:
        runtime.close()


def planned(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


async def test_a_trait_question_reads_the_natal_chart_in_one_call(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(TRAIT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert planned(events) == ["start_reading", "compute_bazi", "submit_reading"]
    ((messages, tools),) = composer.seen
    assert tools == [] and "bazi:" not in str(messages)
    labels = {label for _, label, _ in facts_in(messages)}
    assert {"日主", "四柱"} <= labels and "流月" not in labels
    assert outcome.data["reading"]["question_type"] == "trait"


async def test_next_month_computes_flow_months_over_the_month(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    assert planned(events)[:3] == ["start_reading", "compute_bazi", "compute_bazi_period"]
    period = runtime.session.state["bazi_period_result"]
    assert (period["start"], period["end"], period["granularity"]) == (
        "2026-11-01",
        "2026-11-30",
        "month",
    )
    sheet = composer.seen[0][0][1]["content"]
    assert "日期范围：2026-11-01至2026-11-30" in sheet
    assert aliases(composer.seen[0][0], "流月")
    assert outcome.data["reading"]["question_type"] == "timing"


async def test_a_luck_cycle_question_lists_the_cycles(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(DAYUN)
    assert outcome.status == "submit_reading", outcome.text
    assert "compute_bazi_period" not in planned(events)
    labels = [label for _, label, _ in facts_in(composer.seen[0][0])]
    assert labels.count("大运") >= 3


async def test_a_luck_cycle_question_asks_for_the_gender(make):
    birth = {k: v for k, v in SHANGHAI.items() if k != "gender"}
    runtime, composer, events = make(written, birth=birth)
    first = await runtime.turn(DAYUN)
    assert first.status == "ask_user" and first.text == ASK_GENDER
    assert composer.seen == []
    second = await runtime.turn("男")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_result"]["dayun"]["gender"] == "male"
    assert runtime.store.get_profile(runtime.session.user_id)["gender"] == "male"
    assert second.data["pipeline"]["asks"] == 1


async def test_overseas_birth_asks_for_the_solar_time_choice(make):
    runtime, composer, events = make(written, birth=LOS_ANGELES)
    first = await runtime.turn(TRAIT)
    assert first.status == "ask_user" and "真太阳时" in first.text
    second = await runtime.turn("用真太阳时")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_result"]["input"]["true_solar_time"] is True


async def test_an_unclear_range_is_asked(make):
    runtime, composer, events = make(written)
    first = await runtime.turn("用八字看看最近的运势")
    assert first.status == "ask_user" and first.text == requirements.UNCLEAR_RANGE
    second = await runtime.turn("看下个月就行")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_period_result"]["start"] == "2026-11-01"


@pytest.mark.parametrize(
    "message",
    [
        "用八字和星盘一起看看下个月",
        "帮我合婚，看看我们两个人的八字",
        "用紫微斗数看看命盘",
        "刚才那个八字解读里说的偏印是什么意思？",
        "我的出生时间记错了，八字要改成9点",
        "今天运势怎么样？",
    ],
)
async def test_messages_the_bazi_pipeline_leaves_alone(make, message):
    runtime, *_ = make(written)
    found = PipelineRunner(runtime).detect(message)
    assert found is None or found.system != "bazi", message


async def test_a_wrong_ten_god_is_repaired(make):
    def wrong_god(messages):
        sheet = messages[1]["content"]
        month = re.search(r"月柱(\S{2})（天干\S为(\S{2})）", sheet)
        other = next(g for g in ("正官", "七杀", "正财") if g != month[2])
        return written(messages, extra=f"月柱{month[1]}为{other}。")

    runtime, composer, events = make(wrong_god, written)
    outcome = await runtime.turn(TRAIT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert any("这里的十神是" in p for p in info["problems"][0])


def test_problems_on_an_empty_state():
    session = type("S", (), {"state": {}, "policy_judge": None})()
    assert Bazi(None).problems(["日主是丙火。"], session) == []


# ---- the evaluation sets run end to end offline -------------------------------------------


def dataset(name):
    import yaml

    from app import ROOT

    return yaml.safe_load((ROOT / f"evals/cases/{name}.yaml").read_text(encoding="utf-8"))["cases"]


def test_the_sets_are_apart_and_carry_what_the_live_evaluation_reads():
    from common.validation import HIGH_RISK

    tuning, final = dataset("bazi_pilot"), dataset("bazi_final")
    assert (len(tuning), len(final)) == (6, 4)
    assert not {c["id"] for c in tuning} & {c["id"] for c in final}
    assert not {c["question"] for c in tuning} & {c["question"] for c in final}
    for case in tuning + final:
        assert {"id", "question", "tools", "systems"} <= set(case), case["id"]
        assert case["systems"] == ["bazi"], case["id"]
        assert bool(case.get("risk")) == bool(HIGH_RISK.search(case["question"])), case["id"]


@pytest.mark.parametrize(
    "case",
    dataset("bazi_pilot") + dataset("bazi_final"),
    ids=lambda case: case["id"],
)
async def test_each_evaluation_case_reaches_submission(make, case):
    runtime, composer, events = make(
        written, user_id=f"eval-{case['id']}", birth=case.get("profile")
    )
    assert PipelineRunner(runtime).detect(case["question"]).system == "bazi"
    outcome = await runtime.turn(case["question"])
    if outcome.status == "ask_user":
        assert case.get("clarification"), outcome.text
        outcome = await runtime.turn(case["clarification"])
    assert outcome.status == "submit_reading", outcome.text
    assert set(case["tools"]) <= set(planned(events))
    reading = outcome.data["reading"]
    assert reading["systems_used"] == case["systems"]
    assert outcome.data["pipeline"]["model_calls"] <= 3
    result = runtime.session.state["bazi_result"]
    if case.get("unknown"):
        assert "time" not in result["pillars"]
    if case.get("risk"):
        assert reading["safety"]["flag"] is True
    if "compute_bazi_period" in case["tools"]:
        assert runtime.session.state["bazi_period_result"]["periods"]
    if case.get("clarification"):
        assert result["input"]["true_solar_time"] is ("不用" not in case["clarification"])
    period = runtime.session.state.get("bazi_period_result")
    profile = case.get("profile") or {}
    if period and profile.get("tz", "Asia/Shanghai") != "Asia/Shanghai":
        # Owner, 2026-11-08: no stated residence, so the birth place's timezone, noted.
        assert period["tz"] == profile["tz"]
        assert "日期按出生地" in reading["closing"]


# ---- the consultation timezone of a range (owner, 2026-11-08) -------------------------------


async def test_overseas_birth_without_residence_uses_the_birth_timezone(make):
    """An overseas birth without a stated residence: the birth place's timezone, noted."""
    birth = {**LOS_ANGELES, "true_solar_time": False}
    runtime, composer, events = make(written, birth=birth)
    outcome = await runtime.turn(NEXT_MONTH)
    assert outcome.status == "submit_reading", outcome.text
    assert "ask_user" not in planned(events)
    period = runtime.session.state["bazi_period_result"]
    assert period["tz"] == "America/Los_Angeles"
    closing = outcome.data["reading"]["closing"]
    assert "日期按出生地洛杉矶的时区（America/Los_Angeles）计算" in closing
    assert "America/Los_Angeles当地时间" in composer.seen[0][0][1]["content"]


async def test_overseas_birth_with_a_stated_residence_is_asked(make):
    birth = {**LOS_ANGELES, "true_solar_time": False}
    runtime, composer, events = make(written, birth=birth)
    first = await runtime.turn("我现在住在多伦多，用八字看看我下个月的事业运。")
    assert first.status == "ask_user" and "哪个城市的时间" in first.text
    assert "compute_bazi_period" not in planned(events) and composer.seen == []
    second = await runtime.turn("按北京时间")
    assert second.status == "submit_reading", second.text
    assert runtime.session.state["bazi_period_result"]["tz"] == "Asia/Shanghai"
    assert "出生地" not in second.data["reading"]["closing"]


async def test_a_stated_timezone_is_used_for_the_range(make):
    birth = {**LOS_ANGELES, "true_solar_time": False}
    runtime, *_ = make(written, birth=birth)
    outcome = await runtime.turn("按北京时间，用八字看看我下个月的事业运。")
    assert outcome.status == "submit_reading", outcome.text
    assert runtime.session.state["bazi_period_result"]["tz"] == "Asia/Shanghai"
    assert "出生地" not in outcome.data["reading"]["closing"]


async def test_a_birth_in_beijing_time_is_not_noted(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn(NEXT_MONTH)
    assert runtime.session.state["bazi_period_result"]["tz"] == "Asia/Shanghai"
    assert "出生地" not in outcome.data["reading"]["closing"]
