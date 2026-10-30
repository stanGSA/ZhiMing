"""The tarot pilot end to end with a scripted writer (P1 of docs/根因整改实施计划.md)."""

import copy

import pytest

from app import create_runtime
from harness.models import ModelResponse
from harness.progress import progress_label
from plugins.tarot.draw import draw_tarot
from tests.pipeline.drafts import (
    QUESTION,
    Composer,
    followup_answer,
    good,
    swapped_positions,
    wrong_orientation,
)


@pytest.fixture
def make(project):
    runtimes = []

    def build(*drafts, user_id="pipeline-user", seed=42):
        composer = Composer(*drafts)
        runtime = create_runtime(
            root=project, user_id=user_id, seed=seed, model=composer, mode="pipeline"
        )
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def planned_tools(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


async def test_a_new_reading_takes_one_writing_call(make):
    runtime, composer, events = make(good)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"] == {
        "run_id": outcome.data["pipeline"]["run_id"],
        "kind": "new",
        "model_calls": 1,
        "repairs": 0,
        "degraded": False,
        "problems": [],
    }
    assert planned_tools(events) == ["start_reading", "draw_tarot", "submit_reading"]
    assert [e["purpose"] for e in events if e["event"] == "model_response"] == ["compose"]
    # The writer saw R-numbers and the cards' text, never a full reference, and no tools.
    ((messages, tools),) = composer.seen
    assert tools == [] and "tarot:" not in str(messages)
    state = runtime.session.state
    saved = runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])
    for card in state["tarot_result"]["cards"]:
        side = "逆位" if card["reversed"] else "正位"
        assert f"【{card['name']}】{side}" in outcome.text
    assert {e["ref_id"] for e in saved["output_json"]["evidence"]} <= state["allowed_refs"]
    assert saved["output_json"]["confidence"]["level"] in ("low", "medium")
    assert runtime.store.unfinished_pipeline_run(runtime.session.user_id) is None


async def test_a_wrong_orientation_is_repaired_once(make):
    runtime, composer, events = make(wrong_orientation, good)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (2, 1, False)
    assert "牌面方向错误" in info["problems"][0][0]
    # The repair request names the problem and what may be cited.
    repair = composer.seen[1][0][-1]["content"]
    assert "牌面方向错误" in repair and "R1、R2、R3" in repair
    assert progress_label(next(e for e in events if e.get("stage") == "repair"))


async def test_a_card_in_the_wrong_position_is_caught_by_the_pipeline(make):
    runtime, _, _ = make(swapped_positions, good)
    outcome = await runtime.turn(QUESTION)
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "过去位是【" in outcome.data["pipeline"]["problems"][0][0]


async def test_two_failed_drafts_degrade_to_a_reading_made_by_code(make):
    runtime, _, _ = make("没有按格式写。", "还是没有按格式写。")
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert info["degraded"] and info["model_calls"] == 2
    reading = outcome.data["reading"]
    assert reading["summary"].startswith("这次抽到过去位【")
    assert len(reading["sections"]) == 3
    assert runtime.store.get_reading(runtime.session.user_id, outcome.data["reading_id"])


async def test_a_cut_off_draft_is_repaired(make):
    cut = ModelResponse(
        text="【摘要】近期", input_tokens=10, output_tokens=10, finish_reason="length"
    )
    runtime, composer, _ = make(cut, good)
    outcome = await runtime.turn(QUESTION)
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "截断" in composer.seen[1][0][-1]["content"]


async def test_follow_up_in_the_same_session_reads_the_saved_draw(make):
    runtime, composer, events = make(good, followup_answer)
    first = await runtime.turn(QUESTION)
    cards = copy.deepcopy(runtime.session.state["tarot_result"]["cards"])
    events.clear()
    second = await runtime.turn("第二张牌具体什么意思？请解释原牌，不要重新抽牌。")
    assert second.status == "submit_reading" and second.data["response_id"]
    assert planned_tools(events) == ["read_reading", "submit_reading"]
    assert runtime.session.state["tarot_result"]["cards"] == cards
    prompt = composer.seen[1][0][1]["content"]
    assert "原解读摘要" in prompt and first.data["reading"]["summary"] in prompt
    assert runtime.store.get_response(runtime.session.user_id, second.data["response_id"])


async def test_follow_up_from_another_session_reads_the_latest_tarot_reading(make):
    runtime, _, _ = make(good)
    first = await runtime.turn(QUESTION)
    later, _, events = make(followup_answer)
    outcome = await later.turn("上一条占卜中第二张牌具体什么意思？读取原记录，不要重新抽牌。")
    assert outcome.status == "submit_reading"
    assert planned_tools(events) == ["read_reading", "submit_reading"]
    assert later.session.state["active_reading_id"] == first.data["reading_id"]


async def test_an_explicit_redraw_starts_a_new_reading(make):
    runtime, _, _ = make(good, good)
    first = await runtime.turn(QUESTION)
    second = await runtime.turn("请重新抽一次，仍用三张牌看近期事业状态。")
    assert second.status == "submit_reading"
    assert second.data["reading_id"] != first.data["reading_id"]
    assert second.data["pipeline"]["kind"] == "new"


async def test_other_questions_stay_with_the_agent_loop(make):
    reply = ModelResponse(text="请告诉我你的出生时间。", input_tokens=10, output_tokens=5)
    runtime, composer, events = make(reply)
    outcome = await runtime.turn("我是男，1993年出生，用八字看看我的性格。")
    assert outcome.status == "text"
    assert composer.seen[0][1], "the agent loop offers its tools"
    assert not [e for e in events if e["event"] == "pipeline_stage"]


async def test_an_interrupted_run_resumes_from_the_same_draw(make):
    runtime, _, _ = make(RuntimeError("connection reset"))
    failed = await runtime.turn(QUESTION)
    assert failed.status != "submit_reading"
    run = runtime.store.unfinished_pipeline_run(runtime.session.user_id)
    assert run["stage"] == "computed"
    drawn = run["state"]["snapshot"]["tarot_result"]["cards"]
    # A new process: same user, nothing in memory.
    later, _, events = make(good)
    outcome = await later.turn("继续")
    assert outcome.status == "submit_reading"
    assert "draw_tarot" not in planned_tools(events)
    saved = later.store.get_reading(later.session.user_id, outcome.data["reading_id"])
    assert saved["tarot_json"]["cards"] == drawn
    assert saved["question"] == QUESTION
    assert later.store.unfinished_pipeline_run(later.session.user_id) is None


async def test_chosen_deck_positions_are_used(make):
    runtime, _, _ = make(good)
    runtime.session.choose_picks((5, 10, 20))
    await runtime.turn(QUESTION)
    state = runtime.session.state
    expected = draw_tarot("three_card", QUESTION, state["seed"], (5, 10, 20))["cards"]
    assert [c["name"] for c in state["tarot_result"]["cards"]] == [c["name"] for c in expected]


async def test_a_high_risk_question_gets_the_safety_note_from_code(make):
    def all_in(messages):
        return (
            good(messages)
            .replace("【表态】平稳", "【表态】暂不适合")
            .replace("近期事业整体平稳，可以按计划推进。", "暂不适合把积蓄全部买入一只股票。")
        )

    runtime, _, _ = make(all_in)
    outcome = await runtime.turn("只用塔罗三张牌帮我反思：是否应该把积蓄全部买入一只股票？")
    assert outcome.status == "submit_reading"
    reading = outcome.data["reading"]
    assert reading["verdict"] == "not_now"
    assert reading["safety"]["flag"] and "投资建议" in reading["safety"]["note"]


async def test_progress_follows_the_stages(make):
    runtime, _, events = make(good)
    await runtime.turn(QUESTION)
    labels = [label for e in events if (label := progress_label(e))]
    assert labels[:3] == ["正在理解你的问题", "正在抽牌", "正在撰写解读"]
    assert labels[-1] == "解读已完成"


async def test_clearing_records_drops_an_unfinished_draw(make):
    runtime, _, _ = make(RuntimeError("down"))
    await runtime.turn(QUESTION)
    user = runtime.session.user_id
    assert runtime.store.unfinished_pipeline_run(user)
    assert runtime.store.export_user(user)["unfinished_readings"][0]["question"] == QUESTION
    runtime.store.delete_readings(user)
    assert runtime.store.unfinished_pipeline_run(user) is None


def test_pipeline_mode_takes_its_systems_from_config(project):
    writer = create_runtime(root=project, model=Composer(), mode="pipeline")
    demo = create_runtime(root=project, mode="pipeline")
    single = create_runtime(root=project, model=Composer())
    try:
        assert writer.pipeline_systems == ("tarot",)
        # The offline demo replays tool calls and cannot write a draft: the agent loop answers.
        assert demo.pipeline_systems == () and single.pipeline_systems == ()
        assert set(writer.registry.tools) == set(single.registry.tools)
    finally:
        for runtime in (writer, demo, single):
            runtime.close()
