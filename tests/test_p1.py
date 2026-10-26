"""P1 boundary regressions: aliases, provenance, visibility, progress and policy failure."""

import copy
import json

import httpx
import pytest

from common.policy_judge import PolicyJudge
from common.stages import available
from harness.guard import Guard
from harness.models import ModelResponse, ToolCall
from harness.progress import progress_label
from harness.refs import transform
from harness.session import Session
from harness.trace import Tracer
from plugins.context import BirthInput, birth_provenance, inferred_birth
from tests.plugins.test_astro_bazi_integration import invoke
from web import create_web_app


def test_judge_json_extractor_accepts_fences_and_surrounding_text():
    from scripts.live_week23 import extract_json_object

    expected = {"direct_answer": True, "reasons": []}
    assert extract_json_object('```json\n{"direct_answer": true, "reasons": []}\n```') == expected
    assert extract_json_object('评审结果：{"direct_answer": true, "reasons": []} 完成') == expected
    with pytest.raises(ValueError):
        extract_json_object("没有JSON")


def test_failure_taxonomy_separates_submission_quality_and_tool_errors():
    from scripts.failure_taxonomy import summarize, task_success

    row = {
        "id": "case-1",
        "repeat": 0,
        "status": "submit_reading",
        "checks": {"zero_tool_errors": False, "confidence_not_overstated": True},
        "quality_pass": True,
        "quality_review": {
            "direct_answer": True,
            "time_consistent": True,
            "supported_conclusion": True,
            "no_fabricated_facts": True,
        },
        "tool_errors": [{"tool": "submit_reading", "code": "validation_failed", "error": "retry"}],
        "latency_s": 1,
    }
    summary = summarize({"results": [row]})
    assert task_success(row)
    assert summary["task_success"] == 1 and summary["first_try_clean"] == 0
    assert summary["submitted"] == summary["quality_scored"] == summary["submitted_quality"] == 1


def test_failure_taxonomy_classifies_profile_provenance_errors_as_c():
    from scripts.failure_taxonomy import category

    assert category("update_profile", "validation_failed", "地理字段须来自已确认地点") == (
        "C 画像写入越界（地理/历法口径）"
    )


def test_aliases_are_recursive_session_local_and_full_ids_accepted():
    one, two = Session("one"), Session("two")
    value = {"ref_id": "astro:fact:1", "children": [{"ref_ids": ["astro:fact:1", "bazi:fact:2"]}]}
    short = transform(value, one)
    assert short == {"ref_id": "R1", "children": [{"ref_ids": ["R1", "R2"]}]}
    assert transform(short, one, restore=True) == value
    assert transform(value, one, restore=True) == value
    assert transform({"ref_id": "R999"}, one, restore=True)["ref_id"] == "R999"
    assert transform({"ref_id": "other:fact"}, two)["ref_id"] == "R1"
    assert one.state["ref_alias"]["R1"] != two.state["ref_alias"]["R1"]


async def test_lite_missing_birth_returns_needs_input_without_model(runtime):
    from agents.lite import LiteModel
    from agents.schemas import ConsultInput
    from agents.specialists import build_specialists
    from harness.loop import run_turn
    from plugins.astro import AstroPlugin

    session = runtime.session
    session.role = session.partition = "astro"
    session.start_reading("工作方向")
    registry = build_specialists(
        [AstroPlugin(runtime.kb, runtime.store)], runtime.registry.tools["lookup_meaning"]
    )["astro"].registry

    class NoModel:
        async def chat(self, *args):
            pytest.fail("missing input must not invoke report model")

    from agents.consult import stop_on_needs_input

    result = await run_turn(
        session,
        "brief",
        LiteModel(NoModel(), session, "astro", ConsultInput(system="astro", sub_question="工作")),
        registry,
        runtime.tracer,
        as_evidence=False,
        on_tool_result=stop_on_needs_input,
    )
    assert result.status == "needs_input" and session.model_calls == 0


def test_birth_defaults_do_not_repair_fabricated_values():
    session = Session("p1")
    session.append_user("男性，公历1993-08-17 23:20，北京出生。看2026-11-01至2026-11-30工作。")
    session.state["locations"] = {"beijing": {"tz": "Asia/Shanghai", "lat": 39.9, "lon": 116.4}}
    args = BirthInput()
    assert birth_provenance(args, session) is None
    assert args.birth_local == "1993-08-17 23:20" and args.location_id == "beijing"
    wrong = BirthInput(birth_local="1990-01-01 08:00")
    assert "1993-08-17 23:20" in birth_provenance(wrong, session)
    assert wrong.birth_local == "1990-01-01 08:00"
    session.append_user("另一人的生日为1991-02-01 12:00。")
    ambiguous = BirthInput()
    assert birth_provenance(ambiguous, session) is None
    assert ambiguous.birth_local is None


def test_birth_inference_never_uses_a_meeting_clock():
    session = Session("p1")
    session.append_user("我出生于1993-08-17。2026-11-01 10:00开会，适合谈加薪吗？")
    assert inferred_birth(session) is None
    session.user_messages[:] = ["我是1993-08-17 23:20出生的，看2026-11-01工作状态。"]
    assert inferred_birth(session) == "1993-08-17 23:20"
    session.user_messages[:] = ["我出生于1993-08-17 23:20，另一人的生日1991-02-01，时辰未知。"]
    assert inferred_birth(session) is None


async def test_alias_identity_survives_new_reading_and_restore(runtime):
    outcome = await runtime.turn("抽三张塔罗看看近期状态")
    reading_id = outcome.data["reading_id"]
    original = transform(
        {"ref_id": outcome.data["reading"]["evidence"][0]["ref_id"]}, runtime.session
    )
    full = transform(original, runtime.session, restore=True)
    runtime.session.start_reading("一个新问题")
    new = transform({"ref_id": "tarot:a-new-calculation"}, runtime.session)
    assert new != original
    restored = await invoke(runtime, "read_reading", {"reading_id": reading_id})
    assert restored.ok
    assert transform(original, runtime.session, restore=True) == full
    assert transform(new, runtime.session, restore=True)["ref_id"] == "tarot:a-new-calculation"


async def test_ref_only_evidence_persists_full_ids_and_guard_stays_strict(runtime):
    outcome = await runtime.turn("抽三张塔罗看看近期状态")
    assert outcome.status == "submit_reading"
    draft = copy.deepcopy(outcome.data["reading"])
    for item in draft["evidence"]:
        item.pop("reading")
    runtime.session.state["response_mode"] = "followup"
    short = transform(draft, runtime.session)
    result = await invoke(runtime, "submit_reading", short)
    assert result.ok, result.error
    assert all(
        e["reading"] and e["ref_id"].startswith("tarot:")
        for e in result.data["reading"]["evidence"]
    )
    bad = copy.deepcopy(short)
    bad["evidence"][0]["ref_id"] = "R999999"
    result = await invoke(runtime, "submit_reading", bad)
    assert not result.ok and result.code == "validation_failed"
    parsed, error, _ = Guard(runtime.registry).check(
        ToolCall(id="bad", name="submit_reading", raw_arguments='{"summary":', argument_error=True),
        runtime.session,
    )
    assert parsed is None and "字符" in error.error
    result = await invoke(runtime, "draw_tarot", {"spread": "invalid", "question": "q"})
    assert not result.ok and "Input should be" in result.error


def test_stage_visibility_is_not_a_guard_bypass():
    from common.schemas import EmptyInput
    from harness.registry import Registry, Tool

    registry = Registry()
    tool = Tool("compute_transits", "", EmptyInput, lambda a, s: {}, dependency="chart_id")
    registry.register(tool)
    session = Session("s")
    assert not available(tool, session)
    _, error, _ = Guard(registry).check(ToolCall(id="x", name=tool.name, arguments={}), session)
    assert error.code == "missing_dependency"
    session.state.update(active_reading_id="r", chart_id="chart")
    assert available(tool, session)
    session.state["response_mode"] = "followup"
    assert not available(tool, session)
    session.state["complete"] = True
    assert available(tool, session)  # A later new question can compute again.


async def test_new_question_after_followup_can_start_a_fresh_reading(runtime):
    first = await runtime.turn("抽三张牌看近期状态")
    followup = await runtime.turn("第二张牌具体什么意思？")
    assert followup.status == "submit_reading"
    redraw = await runtime.turn("请重新抽三张牌看工作状态")
    assert redraw.status == "submit_reading"
    assert redraw.data["reading_id"] != first.data["reading_id"]


def test_stage_install_does_not_mutate_shared_tools():
    from common.schemas import EmptyInput
    from common.stages import install
    from harness.registry import Registry, Tool

    shared = Tool("lookup_meaning", "", EmptyInput, lambda a, s: {})
    one, two = Registry(), Registry()
    one.register(shared)
    two.register(shared)
    install(one)
    install(two)
    assert shared.available is None
    assert one.tools[shared.name] is not two.tools[shared.name]


def test_progress_is_allowlisted_and_never_contains_payload():
    record = {
        "event": "tool_result",
        "call": {"name": "submit_reading", "arguments": {"secret": "private"}},
        "result": {"ok": False, "code": "validation_failed", "error": "private"},
    }
    assert progress_label(record) == "事实核对未通过，正在改写"
    record["event"] = "unknown"
    assert progress_label(record) is None


async def test_sse_demo_sequence_and_cookie_isolation(project):
    app = create_web_app(root=project)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Zhiming-Client": "web"},
    ) as client:
        await client.get("/api/session", params={"provider": "demo"})
        answer = await client.post(
            "/api/chat",
            json={"message": "抽三张牌看近期状态", "system": "tarot", "spread": "three_card"},
        )
        assert answer.status_code == 200
        response = await client.get("/api/progress")
        labels = [
            json.loads(line[6:])["label"]
            for line in response.text.splitlines()
            if line.startswith("data: ") and "label" in line
        ]
        assert labels[0] == "正在理解你的问题" and "正在抽牌" in labels and "解读已完成" in labels
        assert "ref_id" not in response.text and "抽三张牌看近期状态" not in response.text
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as other:
        assert (await other.get("/api/progress")).status_code == 401


async def test_evaluation_progress_is_redacted_and_has_initial_state(project):
    app = create_web_app(root=project)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        initial = await client.get("/api/evaluation-progress")
        assert initial.status_code == 200
        assert initial.json()["status"] == "not_started"

        progress_path = project / "reports/p1/codego-v4/web-progress.json"
        progress_path.parent.mkdir(parents=True)
        progress_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated": "2026-10-25T00:00:00+00:00",
                    "status": "running",
                    "active_job": "B0-multi",
                    "runtime_model": "deepseek-v4-flash",
                    "judge_model": "deepseek-v4-pro",
                    "planned_cases": 517,
                    "completed_cases": 60,
                    "percent": 11.61,
                    "batches": [
                        {
                            "name": "B0-multi",
                            "expected": 60,
                            "completed": 0,
                            "terminal": False,
                            "status": "running",
                            "last_case": None,
                            "prompt": "do not expose",
                        }
                    ],
                    "error_count": 1,
                    "recent_errors": [
                        {
                            "batch": "B0-single",
                            "case": "case-1",
                            "kind": "review_error",
                            "message": "invalid_json",
                            "trace": "do not expose",
                            "answer": "private answer",
                            "token": "secret",
                        }
                    ],
                    "api_key": "secret",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        response = await client.get("/api/evaluation-progress")
        body = response.json()
        encoded = response.text
        assert body["completed_cases"] == 60
        assert body["batches"][0]["name"] == "B0-multi"
        assert "prompt" not in encoded and "trace" not in encoded
        assert "private answer" not in encoded and "secret" not in encoded


async def test_policy_judge_negation_accepts_but_failure_does_not_bypass(tmp_path):
    class Model:
        async def chat(self, messages, tools):
            return ModelResponse(
                text='{"certainty":false,"discourage_care":false}', input_tokens=20, output_tokens=5
            )

    session = Session("policy")
    judge = PolicyJudge(Model(), Tracer(tmp_path))
    assert await judge.check(["不能说你一定会成功"], session) is None
    assert session.total_tokens == 25
    assert await judge.check(["这只股票必涨"], session) is not None

    class Broken:
        async def chat(self, *args):
            raise RuntimeError("failure")

    assert (
        await PolicyJudge(Broken(), Tracer(tmp_path)).check(["你一定会成功"], session)
    ).code == "policy_unavailable"


def test_kappa_uses_boolean_categories_and_constant_raters():
    from scripts.model_review_kb import cohen_kappa

    assert cohen_kappa([("True", "True")] * 8 + [("False", "False")] * 2) == 1
    assert (
        cohen_kappa([("True", "True")] * 6 + [("False", "True")] * 2 + [("False", "False")] * 2)
        == 0.5455
    )
    assert cohen_kappa([("True", "True")] * 20) is None


def test_taxonomy_counts_repeats_and_does_not_guess_missing_cache():
    from scripts.failure_taxonomy import cost, summarize

    base = dict(
        id="same",
        checks={"expected_status": False, "zero_tool_errors": False},
        status="text",
        latency_s=1,
        tool_errors=[dict(tool="compute_bazi", code="invalid_arguments", error="schema")],
    )
    summary = summarize(dict(results=[base | {"repeat": 0}, base | {"repeat": 1}]))
    assert summary["categories"][0][1:] == (2, 2, 2)
    assert cost(summary, {"models": {}}) is None
    mixed = summarize(dict(results=[base | {"cached_input_tokens": 0}, base]))
    assert mixed["cache_rate"] is None


def test_report_publisher_skips_malformed_tension_tables_explicitly():
    from scripts.p1_report import valid_tension_table

    assert valid_tension_table({"tensions": []})
    assert not valid_tension_table({"tensions": [{"theme": "work"}]})
    assert valid_tension_table(
        {
            "tensions": [
                {
                    "horizon": "month",
                    "theme": "work",
                    "theme_label": "工作",
                    "systems": ["bazi", "astro"],
                    "windows": [{"window": "2026-11"}],
                }
            ]
        }
    )


async def test_lite_plan_uses_guard_and_only_calls_model_for_report(runtime):
    from agents.lite import LiteModel
    from agents.schemas import ConsultInput
    from agents.specialists import build_specialists
    from harness.loop import run_turn
    from plugins.tarot import TarotPlugin

    session = runtime.session
    session.role = session.partition = "tarot"
    session.append_user("请用塔罗看近期状态")
    session.start_reading("近期状态")
    registry = build_specialists(
        [TarotPlugin(runtime.kb)], runtime.registry.tools["lookup_meaning"]
    )["tarot"].registry

    class Reporter:
        calls = 0

        async def chat(self, messages, tools):
            self.calls += 1
            assert [t["function"]["name"] for t in tools] == ["submit_report"]
            draw = next(json.loads(m["content"])["data"] for m in messages if m["role"] == "tool")
            card = draw["cards"][0]
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="report",
                        name="submit_report",
                        arguments={
                            "answer": "先梳理现实条件",
                            "points": [
                                {
                                    "ref_id": card["ref_id"],
                                    "text": f"【{card['name']}】{'逆位' if card['reversed'] else '正位'}。",
                                }
                            ],
                            "confidence": {"level": "low", "reason": "未经审核"},
                        },
                    )
                ],
                input_tokens=10,
                output_tokens=5,
            )

    reporter = Reporter()
    model = LiteModel(
        reporter, session, "tarot", ConsultInput(system="tarot", sub_question="近期状态")
    )
    result = await run_turn(session, "brief", model, registry, runtime.tracer, as_evidence=False)
    assert result.status == "submit_report" and reporter.calls == 1
    assert session.model_calls == 1 and session.total_tokens == 15


async def test_lite_recovery_keeps_calculation_tools_available(runtime):
    from agents.lite import LiteModel
    from agents.schemas import ConsultInput

    class Recovery:
        async def chat(self, messages, tools):
            assert {t["function"]["name"] for t in tools} == {"compute_bazi", "submit_report"}
            return ModelResponse(text="recover")

    model = LiteModel(
        Recovery(), runtime.session, "bazi", ConsultInput(system="bazi", sub_question="工作")
    )
    tools = [{"function": {"name": name}} for name in ("compute_bazi", "submit_report")]
    reply = await model.chat([{"role": "tool", "content": '{"ok":false}'}], tools)
    assert reply.text == "recover" and model.report_attempts == 1


async def test_lite_unknown_question_does_not_erase_known_birth_clock(runtime):
    from agents.lite import LiteModel
    from agents.schemas import ConsultInput

    session = runtime.session
    session.append_user("我是1993-08-17 23:20在北京出生，不知道适合什么工作。")
    model = LiteModel(None, session, "astro", ConsultInput(system="astro", sub_question="工作"))
    response = await model.chat([{"role": "user", "content": "brief"}], [])
    assert response.planned
    assert response.tool_calls[0].arguments["birth_local"] == "1993-08-17 23:20"
    assert response.tool_calls[0].arguments.get("time_known", True) is True


async def test_policy_cancel_preserves_unknown_usage_charge(tmp_path):
    import asyncio

    from harness.budget import Budget

    class Cancelled:
        async def chat(self, messages, tools):
            raise asyncio.CancelledError()

    session = Session("policy")
    session.turn_budget = Budget(10000)
    with pytest.raises(asyncio.CancelledError):
        await PolicyJudge(Cancelled(), Tracer(tmp_path)).check(["你一定会成功"], session)
    assert session.turn_budget.held == 0 and session.turn_budget.used > 0


@pytest.mark.parametrize("system", ["astro", "bazi", "name", "dream", "daily"])
async def test_ref_only_evidence_covers_all_computation_plugins(runtime, system):
    from common.evidence import fill_evidence
    from common.schemas import Reading
    from tests.plugins.test_astro_bazi_integration import draft, prepare

    birth = await prepare(runtime)
    if system in ("astro", "bazi"):
        tool = "compute_natal_chart" if system == "astro" else "compute_bazi"
        result = await invoke(runtime, tool, birth)
    elif system == "name":
        runtime.session.append_user("分析王明")
        result = await invoke(runtime, "analyze_name", {"surname": "王", "given": "明"})
    elif system == "dream":
        runtime.session.append_user("梦见掉牙")
        result = await invoke(
            runtime, "lookup_dream_symbols", {"symbols": [{"phrase": "掉牙", "symbol": "掉牙"}]}
        )
    else:
        runtime.session.profile.update(
            birth_local_dt="1993-08-17 23:20", tz="Asia/Shanghai", lat=39.9, lon=116.4
        )
        result = await invoke(runtime, "daily_fortune", {"date": runtime.session.calendar_anchor})
    assert result.ok and result.data.get("status") != "needs_input", result
    output = draft(runtime)
    output["evidence"] = [{"ref_id": ref} for ref in sorted(runtime.session.state["allowed_refs"])]
    reading = Reading.model_validate(output)
    assert not fill_evidence(reading, runtime.session.state)
    assert all(e.reading for e in reading.evidence)
    for item in reading.evidence:
        # Every generated fact still traverses the existing plugin validators.
        candidate = copy.deepcopy(output)
        candidate["evidence"] = [item.model_dump()]
        candidate["question_type"] = system if system in ("name", "dream", "daily") else "trait"
        validators = (
            list(runtime.session.output_validators.values())
            if system == "daily"
            else [runtime.session.output_validators[system]]
        )
        error = next(
            (
                error
                for validator in validators
                if (error := validator(Reading.model_validate(candidate), runtime.session.state))
            ),
            None,
        )
        assert error is None, (system, item, error)
