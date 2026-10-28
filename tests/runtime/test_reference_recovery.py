"""Replay of a live tarot failure: knowledge-base references offered beside the drawn cards,
a read of the reading that was not saved yet, guessed lookup keys, and the same rejected
submission until the retry limit stopped the turn.

Each of those steps now either cannot happen or is answered with exactly what to fix.
"""

import copy
import json

import pytest

from agents.demo import DemoModel
from harness.context import compact_context
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall
from harness.refs import transform
from tests.plugins.test_astro_bazi_integration import invoke

QUESTION = "工作停滞了，接下来三个月怎么推进？"


class Replay:
    """A scripted model that keeps what it was shown before each step."""

    def __init__(self, steps):
        self.steps = iter(steps)
        self.shown = []

    async def chat(self, messages, tools):
        self.shown.append((copy.deepcopy(messages), tools))
        return next(self.steps)


def step(index, name, **arguments):
    return ModelResponse(
        input_tokens=100,
        output_tokens=10,
        tool_calls=[ToolCall(id=f"call-{index}", name=name, arguments=arguments)],
    )


def draft(evidence, section_refs):
    sections = [
        {
            "title": f"第{index + 1}层：先看清处境",
            "body": "这一层说明当下的处境，以及可以先着手的地方。",
            "ref_ids": refs,
        }
        for index, refs in enumerate(section_refs)
    ]
    return DemoModel.submission(
        QUESTION, [{"ref_id": ref} for ref in evidence], "three_card", None, sections
    )


def cited(value, key=None) -> list[str]:
    """Every reference a model-visible payload offers."""
    if key == "ref_id" and isinstance(value, str):
        return [value]
    if key == "ref_ids" and isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return [ref for k, v in value.items() for ref in cited(v, k)]
    if isinstance(value, list):
        return [ref for v in value for ref in cited(v)]
    return []


async def test_reference_failure_chain_is_recoverable(runtime):
    model = Replay(
        [
            step(0, "start_reading", question=QUESTION, systems=["tarot"]),
            step(1, "draw_tarot", spread="three_card", question=QUESTION),
            # Two references nobody returned, in evidence and in a section.
            step(2, "submit_reading", **draft(["R1", "R2", "R3", "R4"], [["R1", "R5"]])),
            step(3, "read_reading"),
            step(4, "lookup_meaning", system="tarot", kind="upright", key="cups_four"),
            step(5, "lookup_meaning", system="tarot", kind="card", key="cups_four"),
            step(6, "submit_reading", **draft(["R1", "R2", "R3"], [["R1"], ["R2"], ["R3"]])),
        ]
    )
    outcome = await run_turn(runtime.session, QUESTION, model, runtime.registry, runtime.tracer)
    state = runtime.session.state
    results = [json.loads(m["content"]) for m in runtime.session.messages if m["role"] == "tool"]
    start, draw, rejected, current, bad_kind, missing, saved = results

    assert outcome.status == "submit_reading"
    # The draw offers one reference per card, and each one is citable.
    assert cited(draw["data"]) == ["R1", "R2", "R3"]
    assert "kb:" not in json.dumps(draw, ensure_ascii=False)
    assert {runtime.session.state["ref_alias"][r] for r in ("R1", "R2", "R3")} == set(
        state["allowed_refs"]
    )
    # The submission schema lists exactly those references.
    submit = next(t for t in model.shown[2][1] if t["function"]["name"] == "submit_reading")
    definitions = submit["function"]["parameters"]["$defs"]
    assert definitions["Evidence"]["properties"]["ref_id"]["enum"] == ["R1", "R2", "R3"]
    assert definitions["Section"]["properties"]["ref_ids"]["items"]["enum"] == ["R1", "R2", "R3"]
    # One rejection names every bad reference by path and lists what may be cited.
    error = rejected["error"]
    assert "evidence.3.ref_id=R4不是工具返回过的编号" in error
    assert "sections.0.ref_ids.1=R5不是工具返回过的编号" in error
    for alias, card in zip(("R1", "R2", "R3"), state["tarot_result"]["cards"], strict=True):
        assert f"{alias}（{card['label']}：【{card['name']}】" in error
    # The unsaved reading is readable as it stands, and reading it resets nothing.
    reading = current["data"]["reading"]
    assert reading["status"] == "in_progress"
    assert [item["ref_id"] for item in reading["citable"]] == ["R1", "R2", "R3"]
    assert cited(reading["tarot_json"]) == ["R1", "R2", "R3"]
    assert state.get("response_mode") != "followup"
    assert state["tarot_drawn"]
    # A kind outside the schema is refused before any lookup; a bare card id gets the keys.
    assert bad_kind["code"] == "invalid_arguments" and "kind" in bad_kind["error"]
    assert missing["code"] == "missing_entry"
    for card in state["tarot_result"]["cards"]:
        assert card["meaning_key"] in missing["error"]
    # The corrected draft is saved with full identifiers.
    assert saved["ok"]
    stored = runtime.store.get_reading(runtime.session.user_id, start["data"]["reading_id"])
    assert [e["ref_id"] for e in stored["output_json"]["evidence"]] == [
        state["ref_alias"][r] for r in ("R1", "R2", "R3")
    ]


async def test_lookup_and_compaction_hide_entry_references(runtime):
    runtime.session.append_user(QUESTION)
    assert (await invoke(runtime, "start_reading", dict(question=QUESTION))).ok
    assert (await invoke(runtime, "draw_tarot", dict(spread="single", question=QUESTION))).ok
    card = runtime.session.state["tarot_result"]["cards"][0]
    found = await invoke(
        runtime, "lookup_meaning", dict(system="tarot", kind="card", key=card["meaning_key"])
    )
    # The entry keeps its source for the trace; the model sees its text, not a citable id.
    assert found.data["entry"]["ref_id"].startswith("kb:tarot:card:")
    shown = transform(found.data, runtime.session)
    assert "ref_id" not in shown["entry"]
    assert shown["entry"]["text"] == found.data["entry"]["text"]
    # A compacted context restates the draw with the same rule.
    assert compact_context(runtime.session, runtime.registry, force=True)
    snapshot = next(m["content"] for m in runtime.session.messages if m["role"] == "user")
    assert "kb:tarot" not in snapshot
    assert cited(json.loads(snapshot.split("\n", 1)[1])) == ["R1"]


@pytest.mark.parametrize("field", ["evidence", "sections", "points"])
async def test_moving_the_same_bad_reference_still_stops_after_three_failures(runtime, field):
    session = runtime.session
    session.append_user(QUESTION)
    assert (await invoke(runtime, "start_reading", dict(question=QUESTION))).ok
    registry = runtime.registry
    if field == "points":
        from agents.specialists import build_specialists

        # Use the real specialist tools and validator in an isolated child session.
        plugin = runtime.registry.tools["draw_tarot"].handler.__self__
        spec = build_specialists([plugin], registry.tools["lookup_meaning"])["tarot"]
        session = session.spawn(
            "tarot",
            "tarot",
            messages=[],
            state=copy.deepcopy(session.state),
            profile={},
            parent_call_id=None,
            budget=None,
            continue_prompt="提交报告",
        )
        registry = spec.registry
    steps = [step(0, "draw_tarot", spread="three_card", question=QUESTION)]
    for index in range(3):
        refs = ["R1", "R2", "R3"]
        refs[index] = "R999"
        if field == "points":
            arguments = dict(
                answer="先梳理现状。",
                points=[{"ref_id": ref, "text": "先核实现实条件。"} for ref in refs],
                confidence={"level": "low", "reason": "释义未人工审核"},
            )
        else:
            arguments = draft(
                refs if field == "evidence" else ["R1"], [refs] if field == "sections" else []
            )
        steps.append(
            step(index + 1, "submit_report" if field == "points" else "submit_reading", **arguments)
        )
    model = Replay(steps)
    outcome = await run_turn(session, QUESTION, model, registry, runtime.tracer, max_steps=4)
    assert outcome.status == "retry_limit"
    errors = [json.loads(m["content"])["error"] for m in session.messages if m["role"] == "tool"][
        1:
    ]
    assert len(set(errors)) == 3  # Detailed field paths remain useful to the model.
    assert session.state["tarot_result"]["cards"]
    assert runtime.store.recent_readings(session.user_id) == []


async def test_unsaved_read_before_calculation_allows_the_first_draw(runtime):
    runtime.session.append_user(QUESTION)
    assert (await invoke(runtime, "start_reading", dict(question=QUESTION, systems=["tarot"]))).ok
    current = (await invoke(runtime, "read_reading", {})).data["reading"]
    assert current["recovery_stage"] == "needs_calculation"
    assert current["pending_specialists"] == []
    assert current["citable"] == []
    assert "不要重新抽牌或计算" not in current["note"]
    assert (await invoke(runtime, "draw_tarot", dict(spread="single", question=QUESTION))).ok
    ready = (await invoke(runtime, "read_reading", {})).data["reading"]
    assert ready["recovery_stage"] == "ready_to_submit"
    assert ready["tarot_json"]["cards"]
    assert ready["citable"]
