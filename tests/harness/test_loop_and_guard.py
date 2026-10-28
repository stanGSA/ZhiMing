import json
from pathlib import Path

import pytest

from harness.guard import Guard
from harness.loop import run_turn
from harness.models import ModelResponse, StrictInput, ToolCall
from harness.registry import Tool


def call(name, **args):
    return ToolCall(id="test-call", name=name, arguments=args)


async def execute(runtime, tool_call):
    args, error, key = Guard(runtime.registry).check(tool_call, runtime.session)
    if error:
        return error
    result = await runtime.registry.run(tool_call.name, args, runtime.session)
    tool = runtime.registry.tools[tool_call.name]
    if result.ok:
        if tool.idempotent:
            runtime.session.cache[key] = result
        if tool.exclusive_key:
            runtime.session.state[tool.exclusive_key] = True
    return result


@pytest.mark.parametrize(
    "name,args,code",
    [
        ("not_registered", {}, "unknown_tool"),
        ("draw_tarot", {"spread": "invalid", "question": "q"}, "invalid_arguments"),
        ("draw_tarot", {"spread": "single", "question": "q", "extra": 1}, "invalid_arguments"),
        ("draw_tarot", {"spread": "single", "question": "q"}, "missing_dependency"),
    ],
)
async def test_guard_errors_are_results(runtime, name, args, code):
    result = await execute(runtime, call(name, **args))
    assert not result.ok and result.code == code


async def test_same_draw_cached_changed_draw_blocked(runtime):
    runtime.session.start_reading("q")
    first = await execute(runtime, call("draw_tarot", spread="three_card", question="q"))
    cached = await execute(runtime, call("draw_tarot", spread="three_card", question="q"))
    duplicate = await execute(runtime, call("draw_tarot", spread="single", question="another q"))
    assert first.ok and cached.ok and cached.cached
    assert first.data == cached.data
    assert not duplicate.ok and duplicate.code == "duplicate_operation"


async def test_permissions_checked_even_on_cache_hit(runtime):
    runtime.session.start_reading("q")
    await execute(runtime, call("draw_tarot", spread="single", question="q"))
    runtime.session.role = "bazi"
    runtime.session.partition = "bazi"
    denied = await execute(runtime, call("draw_tarot", spread="single", question="q"))
    assert denied.code == "permission_denied"


async def test_expert_kb_partition(runtime):
    runtime.session.role = "tarot"
    runtime.session.partition = "tarot"
    allowed = await execute(
        runtime, call("lookup_meaning", system="tarot", kind="card", key="the_tower:upright")
    )
    denied = await execute(
        runtime, call("lookup_meaning", system="bazi", kind="ten_god", key="七杀")
    )
    assert allowed.ok
    assert denied.code == "partition_denied"


def test_profile_requirements_and_dependency_ownership(runtime):
    class Input(StrictInput):
        chart_id: str

    runtime.registry.register(
        Tool(
            "generic_dependency",
            "test",
            Input,
            lambda a, s: {},
            required_profile=frozenset({"birth_place"}),
            dependency="chart_id",
            dependency_argument="chart_id",
        )
    )
    guard = Guard(runtime.registry)
    request = call("generic_dependency", chart_id="foreign")
    assert guard.check(request, runtime.session)[1].code == "missing_profile"
    runtime.session.profile["birth_place"] = "合成地点"
    runtime.session.state["chart_id"] = "owned"
    assert guard.check(request, runtime.session)[1].code == "missing_dependency"
    assert guard.check(call("generic_dependency", chart_id="owned"), runtime.session)[1] is None


async def test_profile_evidence_and_cache(runtime):
    runtime.session.append_user("我叫林晓，出生时间不知道。")
    valid = call("update_profile", field="name", value="林晓", evidence="我叫林晓")
    assert (await execute(runtime, valid)).data["profile"]["version"] == 1
    assert (await execute(runtime, valid)).cached
    assert runtime.store.get_profile(runtime.session.user_id)["version"] == 1
    bad_evidence = await execute(
        runtime, call("update_profile", field="name", value="赵一鸣", evidence="我叫赵一鸣")
    )
    bad_value = await execute(
        runtime, call("update_profile", field="name", value="赵一鸣", evidence="我叫林晓")
    )
    bad_bool = await execute(
        runtime, call("update_profile", field="time_known", value=True, evidence="出生时间不知道")
    )
    assert all(not r.ok for r in (bad_evidence, bad_value, bad_bool))
    unknown = await execute(
        runtime, call("update_profile", field="time_known", value=False, evidence="出生时间不知道")
    )
    assert unknown.ok


async def test_model_error_is_sanitized(runtime):
    class Broken:
        async def chat(self, messages, tools):
            raise RuntimeError("sensitive-api-key-test")

    result = await run_turn(runtime.session, "q", Broken(), runtime.registry, runtime.tracer)
    assert result.status == "model_error"
    logs = "".join(p.read_text(encoding="utf-8") for p in runtime.tracer.root.rglob("*.jsonl"))
    assert "sensitive-api-key-test" not in logs


async def test_limits_do_not_return_unvalidated_reading(runtime, scripted_model):
    runtime.session.start_reading("q")
    await execute(runtime, call("draw_tarot", spread="single", question="q"))
    model = scripted_model([ModelResponse(text="直接绕过提交校验") for _ in range(2)])
    outcome = await run_turn(
        runtime.session, "q", model, runtime.registry, runtime.tracer, max_steps=2
    )
    assert outcome.status == "limit_reached"
    assert runtime.store.recent_readings(runtime.session.user_id) == []


async def test_token_limit_before_side_effect(runtime, scripted_model):
    model = scripted_model(
        [ModelResponse(tool_calls=[call("start_reading", question="q")], input_tokens=100)]
    )
    outcome = await run_turn(
        runtime.session, "q", model, runtime.registry, runtime.tracer, token_budget=50
    )
    assert outcome.status == "limit_reached"
    assert not runtime.session.state.get("active_reading_id")


async def test_terminal_batch_has_all_tool_responses(runtime, scripted_model):
    model = scripted_model(
        [
            ModelResponse(
                tool_calls=[
                    call("ask_user", question="请补充信息"),
                    ToolCall(id="second", name="start_reading", arguments={"question": "q"}),
                ]
            )
        ]
    )
    outcome = await run_turn(runtime.session, "q", model, runtime.registry, runtime.tracer)
    assert outcome.status == "ask_user"
    tool_messages = [m for m in runtime.session.messages if m["role"] == "tool"]
    assert len(tool_messages) == 2
    assert json.loads(tool_messages[1]["content"])["code"] == "turn_finished"
    assert not runtime.session.state.get("active_reading_id")


def test_harness_does_not_import_application_layers():
    root = Path(__file__).resolve().parents[2] / "harness"
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(
            f"from {name}" in source or f"import {name}" in source
            for name in ("plugins", "knowledge", "common", "agents", "memory")
        )
