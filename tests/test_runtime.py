import copy
import json
import subprocess
import sys

import pytest

from app import create_runtime
from common.schemas import Reading
from common.validation import validate_reading
from harness.models import ToolCall
from tests.test_harness import execute


@pytest.mark.parametrize("spread,count", [("single", 1), ("three_card", 3), ("decision", 3)])
async def test_end_to_end_draw_save_trace(project, spread, count):
    runtime = create_runtime(root=project, user_id="synth", seed=42, spread=spread)
    try:
        outcome = await runtime.turn(
            "A offer 还是 B offer？" if spread == "decision" else "用塔罗看看近期状态"
        )
        assert outcome.status == "submit_reading"
        stored = runtime.store.get_reading("synth", outcome.data["reading_id"])
        assert len(stored["tarot_json"]["cards"]) == count
        assert stored["kb_version"] == runtime.kb.version
        assert stored["signals_json"] == runtime.session.state["signals"]
        assert stored["output_json"]["confidence"]["level"] == "low"
        traces = list((project / "runs").rglob("*.jsonl"))
        records = [json.loads(line) for line in traces[0].read_text(encoding="utf-8").splitlines()]
        names = [r["call"]["name"] for r in records if r["event"] == "tool_result"]
        assert names[0] == "start_reading" and names[-1] == "submit_reading"
        assert names.count("draw_tarot") == 1
        assert all(r["session_id"] == runtime.session.id for r in records)
    finally:
        runtime.close()


async def test_followup_reuses_cards_and_record(runtime):
    initial = await runtime.turn("用塔罗看看近期状态")
    old_id = initial.data["reading_id"]
    old_cards = copy.deepcopy(runtime.session.state["tarot_result"]["cards"])
    followup = await runtime.turn("第二张牌具体什么意思？")
    assert followup.status == "submit_reading"
    response = runtime.store.get_response(runtime.session.user_id, followup.data["response_id"])
    assert response["question"] == "第二张牌具体什么意思？"
    assert response["output_json"] == followup.data["reading"]
    assert old_cards[1]["name"] in followup.text
    assert runtime.session.state["active_reading_id"] == old_id
    assert runtime.session.state["tarot_result"]["cards"] == old_cards
    assert len(runtime.store.recent_readings(runtime.session.user_id)) == 1


async def test_cross_session_followup(project):
    first = create_runtime(root=project, user_id="synth", seed=42)
    initial = await first.turn("看看近期状态")
    card_name = first.session.state["tarot_result"]["cards"][1]["name"]
    first.close()
    second = create_runtime(root=project, user_id="synth")
    try:
        outcome = await second.turn("第二张牌具体什么意思？")
        assert outcome.status == "submit_reading" and card_name in outcome.text
        assert second.session.state["active_reading_id"] == initial.data["reading_id"]
        response = second.store.get_response("synth", outcome.data["response_id"])
        assert response["reading_id"] == initial.data["reading_id"]
        assert response["output_json"] == outcome.data["reading"]
        assert (
            second.store.get_reading("synth", initial.data["reading_id"])["output_json"]
            == initial.data["reading"]
        )
        assert second.store.recent_readings("synth")[0]["reading_id"] == initial.data["reading_id"]
    finally:
        second.close()


async def test_new_question_links_previous_reading(runtime):
    first = await runtime.turn("看看近期状态")
    second = await runtime.turn("A offer 还是 B offer？")
    assert second.status == "submit_reading"
    assert first.data["reading_id"] != second.data["reading_id"]
    row = runtime.store.get_reading(runtime.session.user_id, second.data["reading_id"])
    assert row["parent_reading_id"] == first.data["reading_id"]


async def test_cannot_restart_unfinished_draw_without_user_request(runtime):
    runtime.session.append_user("看看近期状态")
    runtime.session.start_reading("看看近期状态")
    await execute(
        runtime,
        ToolCall(id="draw", name="draw_tarot", arguments={"spread": "single", "question": "q"}),
    )
    denied = await execute(
        runtime, ToolCall(id="restart", name="start_reading", arguments={"question": "q"})
    )
    assert not denied.ok
    runtime.session.append_user("请重新抽一次")
    allowed = await execute(
        runtime, ToolCall(id="restart", name="start_reading", arguments={"question": "q"})
    )
    assert allowed.ok


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_ref",
        "undrawn_card",
        "fake_bazi",
        "fake_astro",
        "confidence",
        "orientation",
        "unsupported_system",
    ],
)
async def test_output_validation_rejects_fabrications(runtime, mutation):
    outcome = await runtime.turn("看看近期状态")
    draft = copy.deepcopy(outcome.data["reading"])
    if mutation == "foreign_ref":
        draft["evidence"][0]["ref_id"] = "tarot:another-reading:pos1:the_star:upright"
    elif mutation == "undrawn_card":
        draft["summary"] = "抽到了【愚人】正位，建议尝试。"
    elif mutation == "fake_bazi":
        draft["summary"] = "日柱甲子，适合行动。"
    elif mutation == "fake_astro":
        draft["summary"] = "太阳在白羊座，适合行动。"
    elif mutation == "confidence":
        draft["confidence"]["level"] = "high"
    elif mutation == "orientation":
        draft["evidence"][0]["reading"] = "【月亮】正位。"
    else:
        draft["systems_used"] = ["bazi", "tarot"]
    assert validate_reading(Reading.model_validate(draft), runtime.session)


async def test_guard_rejection_can_be_repaired(runtime):
    outcome = await runtime.turn("看看近期状态")
    draft = copy.deepcopy(outcome.data["reading"])
    draft["evidence"][0]["ref_id"] = "fake"
    from harness.guard import Guard

    args, error, _ = Guard(runtime.registry).check(
        ToolCall(id="bad", name="submit_reading", arguments=draft), runtime.session
    )
    assert error and not error.ok
    draft["evidence"][0]["ref_id"] = outcome.data["reading"]["evidence"][0]["ref_id"]
    assert validate_reading(Reading.model_validate(draft), runtime.session) is None


async def test_high_risk_flag_and_crisis_no_draw(runtime):
    outcome = await runtime.turn("我该投资这只股票吗？")
    assert outcome.data["reading"]["safety"]["flag"]
    before = len(runtime.store.recent_readings(runtime.session.user_id))
    crisis = await runtime.turn("我不想活了，想结束生命")
    assert crisis.status == "crisis_support"
    assert len(runtime.store.recent_readings(runtime.session.user_id)) == before


async def test_reading_ownership_and_forget(project):
    first = create_runtime(root=project, user_id="synth-a", seed=42)
    second = create_runtime(root=project, user_id="synth-b", seed=43)
    try:
        a = await first.turn("看看近期状态")
        b = await second.turn("看看近期状态")
        assert second.store.get_reading("synth-b", a.data["reading_id"]) is None
        first.store.update_profile("synth-a", "name", "测试", "我叫测试")
        first.forget()
        assert first.store.get_profile("synth-a") == {"version": 0}
        assert first.store.recent_readings("synth-a") == []
        assert not first.tracer.user_dir("synth-a").exists()
        assert second.store.get_reading("synth-b", b.data["reading_id"])
        assert first.session.user_messages == []
    finally:
        first.close()
        second.close()


def test_cli_runs_from_other_working_directory(project, tmp_path):
    from app import ROOT

    output = subprocess.check_output(
        [
            sys.executable,
            "-X",
            "utf8",
            str(ROOT / "cli.py"),
            "draw",
            "--question",
            "合成CLI测试",
            "--seed",
            "42",
            "--user",
            "cli-synthetic-test",
            "--json-output",
            "--root",
            str(project),
        ],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
    )
    assert json.loads(output)["status"] == "submit_reading"
