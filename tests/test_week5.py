"""Week 5: cross-system merge, tension disclosure, lenient reviewer and profile reuse."""

import json
import uuid
from pathlib import Path

import pytest

from agents.reviewer import ReviewInput, rule_review, submit_review, validate_review
from app import create_runtime
from common.schemas import Reading
from harness.guard import Guard
from harness.models import ToolCall
from harness.session import Session
from scripts.trace_tree import build_tree, reviewer_metrics
from signals.merge import fingerprint, merge_signals, model_view, undisclosed
from tests.test_multi_agent import (
    BIRTH,
    LOW,
    RoleModel,
    astro_specialist,
    bazi_specialist,
    call,
    disclose,
    events,
    first_points,
    make,
    reading,
    respond,
    tarot_only_orchestrator,
    tarot_specialist,
    turn_results,
)
from tests.test_week23_integration import draft, invoke, prepare

TAROT_SUMMARY = "建议先梳理现状，再做小步尝试。"


def sig(system, theme, valence, strength, horizon="trait", timeframe=None, ref=None):
    return dict(
        ref_id=ref or f"{system}:{theme}:{valence}:{strength}:{timeframe}",
        system=system,
        theme=theme,
        valence=valence,
        strength=strength,
        horizon=horizon,
        timeframe=timeframe,
        keywords=[f"{system}词"],
        kb_ref="kb:x",
        kb_refs=["kb:x"],
        rule_version=1,
        reviewed=False,
    )


class ReviewRoleModel(RoleModel):
    """RoleModel that also serves the reviewer session (tool table = submit_review only)."""

    async def chat(self, messages, tools):
        names = {t["function"]["name"] for t in tools}
        if names == {"submit_review"}:
            self.calls["reviewer"] += 1
            return await self.handlers["reviewer"](messages)
        return await super().chat(messages, tools)


def review(verdict="pass", issues=(), notes=()):
    return respond(call("submit_review", verdict=verdict, issues=list(issues), notes=list(notes)))


def packet_of(messages):
    return json.loads(next(m["content"] for m in messages if m["role"] == "user"))


# --- signals/merge.py -------------------------------------------------------------------


def test_tension_resonance_and_horizon_separation():
    signals = [
        sig("astro", "career", 0.2, 0.6),
        sig("bazi", "career", -0.2, 0.6),
        sig("astro", "self", 0.2, 0.6),
        sig("bazi", "self", 0.2, 0.5),
        sig("tarot", "self", 0.3, 0.7),
        # A strongly negative card on career is a different horizon: no offsetting.
        sig("tarot", "career", -0.6, 0.9, horizon="moment"),
    ]
    merged = merge_signals(signals)
    assert [t["id"] for t in merged["tensions"]] == ["tension:trait:career"]
    tension = merged["tensions"][0]
    assert tension["systems"] == ["astro", "bazi"]
    assert tension["side_texts"] == ["astro: 偏正向（astro词）", "bazi: 偏负向（bazi词）"]
    assert tension["refs"]["bazi"] == [signals[1]["ref_id"]]
    (resonance,) = merged["resonances"]
    assert resonance["id"] == "resonance:trait:self" and resonance["confidence"] == "high"
    assert all(item["horizon"] != "moment" for item in merged["tensions"] + merged["resonances"])


def test_weak_side_is_not_a_tension_and_zero_does_not_dilute():
    weak = merge_signals([sig("astro", "career", 0.2, 0.6), sig("bazi", "career", -0.2, 0.3)])
    assert weak["tensions"] == []
    # Twenty neutral facts of the same system must not cancel its one directional fact.
    neutral = [sig("bazi", "career", 0.0, 0.6, ref=f"n{i}") for i in range(20)]
    diluted = merge_signals(
        [sig("astro", "career", 0.13, 0.6), sig("bazi", "career", -0.13, 0.6), *neutral]
    )
    assert [t["id"] for t in diluted["tensions"]] == ["tension:trait:career"]


def test_timing_signals_align_by_real_intervals():
    # Solar-term months change mid-day on 2026-11-07; a transit is compared only with the
    # month that actually covers its date, never by the label "November".
    october = "2026-10-08T03:00:00+00:00/2026-11-07T05:00:00+00:00"
    november = "2026-11-07T05:00:00+00:00/2026-12-07T00:00:00+00:00"
    signals = [
        sig("bazi", "career", -0.2, 0.5, "timing", october, "bazi:oct"),
        sig("bazi", "career", 0.2, 0.5, "timing", november, "bazi:nov"),
        sig("astro", "career", 0.13, 0.8, "timing", "2026-11-03", "astro:1103"),
        sig("astro", "career", 0.13, 0.8, "timing", "2026-11-20", "astro:1120"),
        sig("astro", "career", 0.0, 0.8, "timing", "2026-11-01/2026-11-30", "astro:range"),
    ]
    merged = merge_signals(signals)
    (tension,) = merged["tensions"]
    assert [w["window"] for w in tension["windows"]] == ["2026-11-03"]
    assert tension["refs"] == {"astro": ["astro:1103"], "bazi": ["bazi:oct"]}
    (resonance,) = merged["resonances"]
    assert [w["window"] for w in resonance["windows"]] == ["2026-11-20"]
    view = model_view(merged)
    assert view["tensions"][0]["windows"] == ["2026-11-03"]


def test_weights_change_combined_valence_not_tensions():
    signals = [sig("astro", "career", 0.2, 0.6), sig("bazi", "career", -0.1, 0.6)]
    equal = merge_signals(signals)
    leaning = merge_signals(signals, weights={"bazi": 5, "astro": 1})
    assert leaning["weights"] == {"astro": 1.0, "bazi": 2.0}  # clamped to [0.5, 2]
    assert [t["id"] for t in leaning["tensions"]] == [t["id"] for t in equal["tensions"]]
    # A distrusted system still shows up in a tension: weights cannot hide a disagreement.
    discounted = merge_signals(signals, weights={"bazi": 0.5})
    assert discounted["tensions"][0]["systems"] == ["astro", "bazi"]
    before = equal["tensions"][0]["windows"][0]["combined_valence"]
    after = leaning["tensions"][0]["windows"][0]["combined_valence"]
    assert after < before
    assert fingerprint(signals) == fingerprint(list(reversed(signals)))


def test_disclosure_needs_theme_and_both_systems():
    merged = merge_signals([sig("astro", "career", 0.2, 0.6), sig("bazi", "career", -0.2, 0.6)])

    def output(tensions):
        return Reading.model_validate(
            dict(
                question_type="timing",
                systems_used=["astro", "bazi"],
                summary="有条件适合。",
                evidence=[dict(ref_id="r", reading="x")],
                tensions=tensions,
                confidence=LOW,
                safety=dict(flag=False, note=""),
            )
        )

    one_side = [dict(theme="career", sides=["占星：有利变动", "也要注意"], how_to_read="看情况")]
    assert undisclosed(merged, output(one_side))
    both = [
        dict(theme="事业", sides=["占星：有利变动", "八字：压力大"], how_to_read="机会与压力并存")
    ]
    assert undisclosed(merged, output(both)) == []


# --- tension disclosure and merge persistence ------------------------------------------


def two_system_orchestrator(with_merge=True, followup=None):
    attempts = []

    async def orchestrator(messages):
        done = turn_results(messages)
        last_user = [m for m in messages if m["role"] == "user"][-1]["content"]
        if followup and followup in last_user:
            if not done:
                return respond(call("read_reading"))
            restored = done[0]["data"]["reading"]
            attempts.append(("followup", restored.get("merge")))
            output = dict(restored["output_json"])
            output["summary"] = "两边并不矛盾：机会和压力同时存在。"
            return respond(call("submit_reading", **output))
        if not done:
            return respond(call("start_reading", question="用占星和八字看看我的工作方式"))
        if len(done) == 1:
            return respond(call("resolve_location", query="北京"))
        if len(done) == 2:
            location = done[1]["data"]["location"]["location_id"]
            return respond(
                call(
                    "consult_specialist",
                    system="astro",
                    sub_question="工作方式",
                    location_id=location,
                ),
                call(
                    "consult_specialist",
                    system="bazi",
                    sub_question="工作方式",
                    location_id=location,
                ),
            )
        payload = reading(
            first_points(done[2:4], ["astro", "bazi"]),
            ["astro", "bazi"],
            question_type="trait",
            summary="更适合结构清楚、能逐步验证的工作方式。",
        )
        if not attempts:
            attempts.append("hidden")
            return respond(call("submit_reading", **payload))
        if with_merge and not any(r.get("data", {}).get("merge") for r in done if r["ok"]):
            return respond(call("merge_signals"))
        merge = next(r["data"]["merge"] for r in done if r["ok"] and "merge" in r["data"])
        payload["tensions"] = disclose(merge)
        attempts.append("disclosed")
        return respond(call("submit_reading", **payload))

    return orchestrator, attempts


async def test_hidden_tension_is_blocked_and_merge_is_saved(project):
    orchestrator, attempts = two_system_orchestrator()
    model = RoleModel(orchestrator=orchestrator, astro=astro_specialist(), bazi=bazi_specialist())
    runtime = make(project, model)
    try:
        outcome = await runtime.turn(BIRTH + "用占星和八字看看我的工作方式。")
        assert outcome.status == "submit_reading", outcome.text
        submits = [
            e
            for e in events(runtime)
            if e["event"] == "tool_result" and e["call"]["name"] == "submit_reading"
        ]
        assert [s["result"]["ok"] for s in submits] == [False, True]
        assert "张力未披露" in submits[0]["result"]["error"]
        assert "tension:trait:career" in submits[0]["result"]["error"]
        saved = runtime.store.get_reading(
            runtime.session.user_id, runtime.session.state["active_reading_id"]
        )
        merge = saved["merge_json"]
        assert {t["id"] for t in merge["tensions"]} >= {"tension:trait:career"}
        assert merge["weights"] == {"astro": 1.0, "bazi": 1.0}
        assert merge["signal_fingerprint"] == fingerprint(saved["signals_json"])
        assert {t["theme"] for t in saved["output_json"]["tensions"]} >= {"career"}
        merged = [
            e
            for e in events(runtime)
            if e["event"] == "tool_result" and e["call"]["name"] == "merge_signals"
        ]
        assert merged[0]["result"]["data"]["merge"]["weights"] == merge["weights"]
    finally:
        runtime.close()


async def test_single_mode_saves_merge_but_keeps_week1_3_rules(project):
    runtime = create_runtime(project, user_id="single-merge", provider="demo", seed=42)
    try:
        assert "merge_signals" not in runtime.registry.tools
        birth = await prepare(runtime)
        assert (await invoke(runtime, "compute_natal_chart", birth)).ok
        assert (await invoke(runtime, "compute_bazi", {**birth, "gender": "male"})).ok
        submitted = await invoke(runtime, "submit_reading", draft(runtime))
        assert submitted.ok, submitted.error
        saved = runtime.store.get_reading("single-merge", submitted.data["reading_id"])
        assert saved["output_json"]["tensions"] == []
        assert saved["merge_json"]["tensions"]  # recorded for evaluation, not enforced
        assert runtime.store.review_notes("single-merge", submitted.data["reading_id"]) == []
    finally:
        runtime.close()


# --- reviewer --------------------------------------------------------------------------


async def test_reviewer_runs_on_every_new_reading_and_is_traced(project):
    packets = []

    async def reviewer(messages):
        packets.append(packet_of(messages))
        return review("pass")

    model = ReviewRoleModel(
        orchestrator=tarot_only_orchestrator(), tarot=tarot_specialist(), reviewer=reviewer
    )
    runtime = make(project, model, reviewer=True)
    try:
        question = "用三张塔罗看看最近的工作状态。"
        outcome = await runtime.turn(question)
        assert outcome.status == "submit_reading", outcome.text
        assert model.calls["reviewer"] == 1
        (packet,) = packets
        assert packet["question"] == question
        assert packet["draft"]["summary"] == TAROT_SUMMARY
        assert packet["signal_table"] == {"tensions": [], "resonances": []}
        reading_id = runtime.session.state["active_reading_id"]
        notes = runtime.store.review_notes(runtime.session.user_id, reading_id)
        assert [(n["round"], n["verdict"], n["status"]) for n in notes] == [(1, "pass", "ok")]
        tree = build_tree(events(runtime), reading_id)
        assert tree["problems"] == []
        (root,) = tree["roots"]
        assert sorted(c["role"] for c in root["children"]) == ["reviewer", "tarot"]
        metrics = reviewer_metrics(events(runtime))
        assert metrics["reviews"] == 1 and metrics["revise_rate"] == 0
    finally:
        runtime.close()


async def test_revise_is_one_round_then_released(project):
    seen = []

    async def final(done):
        failures = [r for r in done if not r["ok"] and r["code"] == "review_revise"]
        seen.append(failures)
        summary = TAROT_SUMMARY if not failures else "最近工作宜先梳理现状，再小步推进。"
        payload = reading(first_points(done[1:2], ["tarot"]), ["tarot"], question_type="tarot")
        payload["summary"] = summary
        return respond(call("submit_reading", **payload))

    async def reviewer(messages):
        packet = packet_of(messages)
        issue = dict(
            reason="off_topic",
            quote=packet["draft"]["summary"],
            fix="第一句直接回答最近工作状态如何。",
        )
        return review("revise", issues=[issue])

    model = ReviewRoleModel(
        orchestrator=tarot_only_orchestrator(final=final),
        tarot=tarot_specialist(),
        reviewer=reviewer,
    )
    runtime = make(project, model, reviewer=True)
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        # The reviewer still disagrees, but the harness allows one revise round only.
        assert model.calls["reviewer"] == 1
        failure = seen[1][0]
        assert "第1轮" in failure["error"] and "off_topic" in failure["error"]
        reading_id = runtime.session.state["active_reading_id"]
        saved = runtime.store.get_reading(runtime.session.user_id, reading_id)
        assert saved["output_json"]["summary"] == "最近工作宜先梳理现状，再小步推进。"
        notes = runtime.store.review_notes(runtime.session.user_id, reading_id)
        assert [(n["round"], n["verdict"]) for n in notes] == [(1, "revise")]
        assert notes[0]["issues"][0]["reason"] == "off_topic"
    finally:
        runtime.close()


async def test_unavailable_reviewer_fails_open(project):
    async def broken(messages):
        raise RuntimeError("reviewer model down")

    model = ReviewRoleModel(
        orchestrator=tarot_only_orchestrator(), tarot=tarot_specialist(), reviewer=broken
    )
    runtime = make(project, model, reviewer=True)
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        reading_id = runtime.session.state["active_reading_id"]
        notes = runtime.store.review_notes(runtime.session.user_id, reading_id)
        assert [(n["verdict"], n["status"]) for n in notes] == [("unavailable", "unavailable")]
        assert build_tree(events(runtime), reading_id)["problems"] == []
    finally:
        runtime.close()


async def test_followup_uses_saved_merge_and_is_not_reviewed(project):
    orchestrator, attempts = two_system_orchestrator(followup="你刚才不是说")
    calls = []

    async def reviewer(messages):
        calls.append(packet_of(messages))
        return review("pass")

    model = ReviewRoleModel(
        orchestrator=orchestrator,
        astro=astro_specialist(),
        bazi=bazi_specialist(),
        reviewer=reviewer,
    )
    runtime = make(project, model, reviewer=True)
    try:
        first = await runtime.turn(BIRTH + "用占星和八字看看我的工作方式。")
        assert first.status == "submit_reading", first.text
        # The reviewer saw the disclosed draft and the code-computed tensions.
        assert calls[0]["signal_table"]["tensions"]
        assert "张力（career）" in calls[0]["draft"]["body"]
        second = await runtime.turn("你刚才不是说适合吗？怎么又说要小心？")
        assert second.status == "submit_reading", second.text
        assert len(calls) == 1
        kind, merge = attempts[-1]
        assert kind == "followup" and merge["tensions"]
    finally:
        runtime.close()


def review_session(packet, strictness="lenient"):
    session = Session(user_id="u", role="reviewer")
    session.state = {"review_packet": packet, "review_strictness": strictness}
    return session


PACKET = dict(
    question="下个月适合跳槽吗？",
    draft=dict(summary="你是一个有主见的人。", body="依据：木星三合本命太阳。"),
    signal_table=dict(tensions=[], resonances=[]),
    safety_relevant=False,
)


@pytest.mark.parametrize(
    ("verdict", "issues", "notes", "error"),
    [
        ("revise", [], [], "至少"),
        ("pass", [], ["精简一点"], "pass_with_notes"),
        ("pass_with_notes", [], [], "notes"),
        ("revise", [("caution", "你是一个有主见的人", "措辞更谨慎")], [], "宽松模式"),
        ("revise", [("off_topic", "你是一个有主见的人", "加上免责声明")], [], "不是打回理由"),
        ("revise", [("off_topic", "下个月很适合", "改成直接回答")], [], "quote"),
        ("revise", [("hidden_tension", "tension:1", "补另一边")], [], "没有张力"),
        (
            "revise",
            [("safety", "你是一个有主见的人", "删掉结论，只写就医建议")],
            [],
            "不能要求删掉",
        ),
        ("revise", [("off_topic", "你是一个 有主见的人。", "第一句先回答适不适合")], [], None),
    ],
)
def test_lenient_review_checks(verdict, issues, notes, error):
    args = ReviewInput(
        verdict=verdict,
        issues=[dict(reason=r, quote=q, fix=f) for r, q, f in issues],
        notes=notes,
    )
    result = validate_review(args, review_session(PACKET))
    assert (result is None) if error is None else error in result


def test_strict_mode_allows_caution_and_lenient_drops_forbidden_notes():
    caution = ReviewInput(
        verdict="revise",
        issues=[dict(reason="caution", quote="你是一个有主见的人", fix="措辞更谨慎")],
    )
    assert validate_review(caution, review_session(PACKET, "strict")) is None
    notes = ReviewInput(verdict="pass_with_notes", notes=["建议加一句免责声明", "语气更谨慎一些"])
    session = review_session(PACKET)
    result = submit_review(notes, session)["review"]
    assert result["verdict"] == "pass" and result["notes"] == [] and result["dropped_notes"] == 2
    kept = submit_review(
        ReviewInput(verdict="pass_with_notes", notes=["可补一个后续可问的问题"]), session
    )["review"]
    assert kept["verdict"] == "pass_with_notes" and kept["dropped_notes"] == 0


def test_strictness_config(project):
    off = create_runtime(root=project, provider="demo", mode="multi", strictness="off")
    strict = create_runtime(root=project, provider="demo", mode="multi", strictness="strict")
    single = create_runtime(root=project, provider="demo", mode="single")
    try:
        assert off.reviewer_model is None and single.reviewer_model is None
        assert strict.reviewer_model is strict.model
    finally:
        for runtime in (off, strict, single):
            runtime.close()
    with pytest.raises(ValueError):
        create_runtime(root=project, provider="demo", mode="multi", strictness="harsh")


async def test_demo_multi_runs_rule_reviewer(project):
    runtime = create_runtime(root=project, user_id="demo-review", provider="demo", mode="multi")
    try:
        outcome = await runtime.turn("A 公司还是 B 公司的 offer？")
        assert outcome.status == "submit_reading", outcome.text
        notes = runtime.store.review_notes(
            "demo-review", runtime.session.state["active_reading_id"]
        )
        assert notes and notes[0]["status"] == "ok"
    finally:
        runtime.close()


def test_rule_baseline_reasons():
    hidden = dict(
        PACKET,
        draft=dict(summary="下个月适合跳槽。", body="木星三合本命太阳，放心去做。"),
        signal_table=dict(
            tensions=[dict(id="tension:1", theme="career", sides=["astro: 利", "bazi: 压力"])],
            resonances=[],
        ),
    )
    assert rule_review(hidden)["issues"][0]["reason"] == "hidden_tension"
    safety = dict(
        PACKET,
        question="这只股票下周会涨吗？",
        draft=dict(summary="下周会涨，可以加仓。", body=""),
        safety_relevant=True,
    )
    assert rule_review(safety)["issues"][0]["reason"] == "safety"
    assert (
        rule_review(dict(PACKET, draft=dict(summary="下个月有条件适合跳槽。", body="")))["verdict"]
        == "pass"
    )


async def test_reviewer_suite_runs_offline(tmp_path):
    from evals.reviewer import evaluate

    report = await evaluate(tmp_path)
    assert report["cases"] == 45 and report["unavailable"] == 0
    assert {k: v["cases"] for k, v in report["per_class"].items()} == {
        "off_topic": 10,
        "hidden_tension": 10,
        "safety": 10,
        "acceptable": 15,
    }
    # The keyword baseline is deterministic; these are the numbers in the week 5 report.
    assert (report["miss_rate"], report["over_intervention_rate"]) == (0.0667, 0.0667)
    assert report["gates"]["over_intervention_rate"]["met"] is False
    assert (Path(report["output_dir"]) / "reviewer-eval.md").exists()


# --- profile reuse ---------------------------------------------------------------------


def check(runtime, name, **arguments):
    _, result, _ = Guard(runtime.registry).check(
        ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments), runtime.session
    )
    return result


def test_ask_user_does_not_repeat_known_profile(runtime):
    store = runtime.store
    for field, value, evidence in (
        ("gender", "male", "男"),
        ("birth_local_dt", "1993-08-17 23:20", "1993-08-17 23:20"),
        ("birth_place", "北京", "北京"),
    ):
        runtime.session.profile = store.update_profile("synthetic-test", field, value, evidence)
    runtime.session.append_user("帮我看看下个月的事业。")
    runtime.session.start_reading("下个月的事业")
    rejected = check(runtime, "ask_user", question="请告诉我你的出生日期和出生地。")
    assert rejected.code == "validation_failed" and "不要重复追问" in rejected.error
    assert check(runtime, "ask_user", question="你的性别是？").code == "validation_failed"
    # Asking about something the profile lacks is fine.
    assert check(runtime, "ask_user", question="想看哪个方面：跳槽还是升职？") is None
    # A tool in this turn asked for the data: the clarification is legitimate.
    runtime.session.messages.append(
        {
            "role": "tool",
            "tool_call_id": "x",
            "content": json.dumps(
                {"ok": True, "data": {"status": "needs_input", "question": "出生地有同名"}}
            ),
        }
    )
    assert check(runtime, "ask_user", question="请确认出生地是哪个省的北京？") is None
    runtime.session.append_user("不好意思，我出生日期记错了。")
    assert check(runtime, "ask_user", question="请告诉我正确的出生日期。") is None


async def test_system_weights_need_explicit_preference(runtime):
    runtime.session.append_user("我更信八字一些，占星参考就好。")

    async def save(value, evidence):
        return await invoke(
            runtime, "update_profile", dict(field="system_weights", value=value, evidence=evidence)
        )

    assert (await save({"bazi": 1.5, "astro": 0.8}, "我更信八字一些，占星参考就好")).ok
    assert runtime.session.profile["system_weights"] == {"bazi": 1.5, "astro": 0.8}
    assert not (await save({"tarot": 1.5}, "我更信八字一些")).ok
    assert not (await save({"bazi": 3}, "我更信八字一些")).ok
    assert not (await save({"bazi": 0.6}, "我更信八字一些")).ok
    assert not (await save({"bazi": 1.5}, "八字")).ok


async def test_start_reading_links_an_owned_previous_reading(project):
    first = create_runtime(project, user_id="revisit", provider="demo", seed=42)
    other = create_runtime(project, user_id="stranger", provider="demo")
    later = create_runtime(project, user_id="revisit", provider="demo")
    try:
        outcome = await first.turn("用三张塔罗看看最近的工作状态")
        assert outcome.status == "submit_reading"
        old = first.session.state["active_reading_id"]
        other.session.append_user("上次说的怎么样了？")
        stolen = await invoke(other, "start_reading", dict(question="回访", parent_reading_id=old))
        assert stolen.code == "missing_reading"
        later.session.append_user("上次说的工作状态，现在怎么样了？")
        linked = await invoke(later, "start_reading", dict(question="回访", parent_reading_id=old))
        assert linked.ok
        assert later.session.state["parent_reading_id"] == old
        previous = linked.data["previous_reading"]
        assert previous["reading_id"] == old and previous["summary"]
        assert previous["merge"] == model_view(
            first.store.get_reading("revisit", old)["merge_json"]
        )
    finally:
        for runtime in (first, other, later):
            runtime.close()


def test_store_migration_adds_merge_column(project):
    runtime = create_runtime(project, user_id="m", provider="demo")
    try:
        columns = {row[1] for row in runtime.store.db.execute("PRAGMA table_info(readings)")}
        assert "merge_json" in columns
    finally:
        runtime.close()


async def test_reviewer_budget_shares_the_request(project):
    """A reviewer denied by the shared budget is unavailable and never blocks the reading."""

    async def reviewer(messages):
        return review("pass")

    model = ReviewRoleModel(
        orchestrator=tarot_only_orchestrator(), tarot=tarot_specialist(), reviewer=reviewer
    )
    runtime = make(project, model, reviewer=True, reviewer_token_budget=10)
    try:
        outcome = await runtime.turn("用三张塔罗看看最近的工作状态。")
        assert outcome.status == "submit_reading", outcome.text
        assert model.calls["reviewer"] == 0
        notes = runtime.store.review_notes(
            runtime.session.user_id, runtime.session.state["active_reading_id"]
        )
        assert notes[0]["verdict"] == "unavailable" and notes[0]["failure"] == "limit_reached"
    finally:
        runtime.close()


def test_trace_tree_requires_finished_reviews():
    started = dict(
        timestamp="2026-10-13T00:00:00+00:00",
        event="review_started",
        session_id="parent",
        parent_session_id=None,
        reading_id="r",
        role="orchestrator",
        parent_call_id=None,
        child_session_id="child",
        call_id="c1",
    )
    child = dict(
        started,
        event="session_started",
        session_id="child",
        parent_session_id="parent",
        role="reviewer",
        parent_call_id="c1",
    )
    problems = build_tree([started, child], "r")["problems"]
    assert any("review_finished" in p for p in problems)
    assert any("开始或结束" in p for p in problems)


async def test_week1_offline_replay_counts_only_computation_tools(tmp_path):
    """Reviewer and merge calls are orchestration, not the plugin tools the F1 compares."""
    from evals.run import evaluate as evaluate_week1

    report = await evaluate_week1(tmp_path, "multi")
    assert report["passed"] == report["cases"] == 12
    assert report["offline_tool_f1"] == 1.0
