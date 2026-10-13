"""All applicable trajectory routes replayed through the real harness guard.

This is a labelled integration replay, NOT an independent model-choice benchmark.
"""

import json
import shutil
import uuid
from pathlib import Path

import yaml

from app import ROOT, create_runtime
from common.validation import HIGH_RISK
from harness.guard import Guard
from harness.models import ToolCall
from knowledge.build import build
from plugins.tarot.draw import draw_tarot

SUPPORTED = {
    "compute_natal_chart",
    "compute_transits",
    "compute_bazi",
    "compute_bazi_period",
    "draw_tarot",
    "lookup_meaning",
    "submit_reading",
    "ask_user",
}


async def execute(runtime, name, arguments):
    call = ToolCall(id=uuid.uuid4().hex, name=name, arguments=arguments)
    parsed, result, key = Guard(runtime.registry).check(call, runtime.session)
    if result is None:
        result = await runtime.registry.run(name, parsed, runtime.session)
        tool = runtime.registry.tools[name]
        if result.ok:
            if tool.idempotent:
                runtime.session.cache[key] = result
            if tool.exclusive_key:
                runtime.session.state[tool.exclusive_key] = True
    runtime.tracer.log(
        runtime.session, "tool_result", call=call.model_dump(), result=result.model_dump()
    )
    return result


def output(runtime, case):
    state = runtime.session.state
    systems = sorted({s["system"] for s in state["signals"]})
    evidence = []
    for system in systems:
        signals = [s for s in state["signals"] if s["system"] == system]
        s = next((s for s in signals if s["horizon"] == "short_term"), signals[0])
        evidence.append(
            dict(
                ref_id=s["ref_id"],
                reading="离线标注路线回放：符号主题提示先核实条件、安排沟通与准备，不作为现实事件预测。",
            )
        )
    summary = "可先核实现实条件再小步尝试；这是标注路线的离线集成回放。"
    if case["id"] == "traj-048":
        summary = "当前只能提供原局五行计数，不能判断姓名是否合适；姓名比较尚缺后续计算能力。"
    if (state.get("tarot_result") or {}).get("spread") == "decision":
        summary = "暂倾向A，前提是核实成本与实际需求；这是离线集成回放。"
    if "下个月适合跳槽" in state["question"]:
        summary = "下个月有条件适合跳槽，前提是先核实岗位与书面录用；这是离线集成回放。"
    risk = bool(HIGH_RISK.search(state["question"] + case["question"]))
    return dict(
        question_type=case["type"] if case["type"] in ("timing", "decision", "trait") else "tarot",
        systems_used=systems,
        summary=summary,
        evidence=evidence,
        advice=["先核实客观条件。"],
        confidence=dict(level="low", reason="知识为未人工审核草稿；离线回放不评估解释质量"),
        safety=dict(
            flag=risk, note="高风险问题需专业判断，不以符号代替就医或财务法律意见。" if risk else ""
        ),
    )


async def route(runtime, case, profile, start="2026-11-01", end="2026-11-30"):
    expected = case["expected"]
    if expected.get("first_action") == "ask_user":
        return await execute(
            runtime, "ask_user", dict(question="请补充/确认：" + "、".join(expected["ask_for"]))
        )
    names = list(expected["tools_single"])
    if (
        names == ["submit_reading"]
        and not runtime.session.state.get("signals")
        and "compute_bazi" in expected.get("optional_tools", [])
    ):
        names.insert(0, "compute_bazi")
    if expected.get("new_reading") is not False:
        result = await execute(runtime, "start_reading", dict(question=case["question"]))
        if not result.ok:
            return result
    birth = {}
    if any(name in names for name in ("compute_natal_chart", "compute_bazi")):
        location = await execute(runtime, "resolve_location", dict(query=profile["place"]))
        if not location.ok or location.data.get("status") != "resolved":
            return location
        birth = dict(
            birth_local=profile["birth_local"],
            location_id=location.data["location"]["location_id"],
            time_known=profile["time_known"],
        )
    for name in names:
        if name == "compute_natal_chart":
            args = birth
        elif name == "compute_bazi":
            args = {**birth, "gender": profile.get("gender")}
        elif name == "compute_transits":
            args = dict(chart_id=runtime.session.state["chart_id"], start=start, end=end)
        elif name == "compute_bazi_period":
            args = dict(bazi_id=runtime.session.state["bazi_id"], start=start, end=end)
        elif name == "draw_tarot":
            args = dict(
                spread=expected.get("tarot_spread", case.get("tarot_spread", "three_card")),
                question=case["question"],
            )
        elif name == "lookup_meaning":
            signal = runtime.session.state["signals"][0]
            entry_ref = signal["kb_ref"].split("@")[0]
            _, system, kind, key = entry_ref.split(":", 3)
            args = dict(system=system, kind=kind, key=key)
        elif name == "submit_reading":
            args = output(runtime, case)
        else:
            raise ValueError("unsupported replay")
        result = await execute(runtime, name, args)
        if not result.ok or result.data.get("status") == "needs_input":
            return result
    return result


async def evaluate(output_dir: Path):
    target = output_dir / ("trajectory-" + uuid.uuid4().hex[:8])
    target.mkdir(parents=True, exist_ok=True)
    fixture = yaml.safe_load((ROOT / "evals/cases/trajectory.yaml").read_text(encoding="utf-8"))
    profiles = yaml.safe_load((ROOT / "evals/cases/profiles.yaml").read_text(encoding="utf-8"))[
        "profiles"
    ]
    workspace = target / "workspace"
    workspace.mkdir()
    shutil.copyfile(ROOT / "config.yaml", workspace / "config.yaml")
    build(ROOT / "knowledge/sources", workspace / "data/kb.sqlite", ROOT / "knowledge/rules")
    rows = []
    for case in fixture["cases"]:
        expected = case["expected"]
        required = set(
            expected.get(
                "tools_single", expected.get("after_user_answers", {}).get("tools_single", [])
            )
        )
        reason = None
        if required - SUPPORTED:
            reason = "依赖尚未实施的工具：" + ", ".join(sorted(required - SUPPORTED))
        if case.get("history") == "H_dream":
            reason = "依赖第六周解梦历史"
        if reason:
            rows.append(dict(id=case["id"], status="skipped", reason=reason))
            continue
        runtime = create_runtime(workspace, user_id=case["id"], provider="demo", seed=42)
        try:
            p = profiles[case["profile"]]
            runtime.session.profile = {
                **p,
                "birth_local_dt": p.get("birth_local"),
                "birth_place": p.get("place"),
                "version": 0,
            }
            if p.get("time_known") is False:
                runtime.session.append_user("出生时间不知道，确认无法补充。")
            if case.get("history"):
                base = {
                    "id": "baseline",
                    "type": "timing" if case["history"] == "H_timing" else "decision",
                    "question": "基线合成记录：近期工作条件",
                    "expected": dict(
                        tools_single=[
                            "compute_natal_chart",
                            "compute_transits",
                            "compute_bazi",
                            "compute_bazi_period",
                            "draw_tarot",
                            "submit_reading",
                        ]
                        if case["history"] == "H_timing"
                        else ["draw_tarot", "submit_reading"],
                        tarot_spread="three_card" if case["history"] == "H_timing" else "decision",
                    ),
                }
                # The dataset has history labels but no saved H_* fixtures. Construct and
                # disclose deterministic histories; never fabricate uncomputed entities.
                if case["id"] == "traj-079":
                    runtime.session.default_seed = next(
                        seed
                        for seed in range(1000)
                        if any(
                            c["card_id"] == "the_tower"
                            for c in draw_tarot("three_card", "baseline", seed)["cards"]
                        )
                    )
                if case["id"] == "traj-076":
                    runtime.session.default_seed = next(
                        seed
                        for seed in range(1000)
                        if draw_tarot("decision", "baseline", seed)["cards"][2]["reversed"]
                    )
                runtime.session.append_user(base["question"])
                baseline = await route(runtime, base, p)
                if not baseline.ok:
                    raise ValueError("baseline rejected")
                runtime.session.append_user(case["question"])
                if expected.get("new_reading") is False:
                    await execute(runtime, "read_reading", {})
            else:
                runtime.session.append_user(case["question"])
            result = await route(runtime, case, p)
            rows.append(
                dict(
                    id=case["id"],
                    status="passed" if result.ok else "failed",
                    error=result.error,
                    expected_tools=sorted(required),
                    history=case.get("history"),
                    ask=bool(expected.get("first_action")),
                )
            )
        except Exception as exc:
            rows.append(dict(id=case["id"], status="failed", error_type=type(exc).__name__))
        finally:
            runtime.close()
    report = dict(
        suite="trajectory-week23",
        provider="labelled-replay",
        cases=sum(r["status"] != "skipped" for r in rows),
        passed=sum(r["status"] == "passed" for r in rows),
        failed=sum(r["status"] == "failed" for r in rows),
        skipped=sum(r["status"] == "skipped" for r in rows),
        results=rows,
        scope="Expected routes executed through real guard, registry, deterministic calculators, storage and trace; NOT model-choice F1 or answer-quality evaluation. H_timing/H_decision fixtures are newly computed synthetic histories. First-action asks tested without invented replies; relative windows fixed to an explicitly declared integration range, not a calendar parser benchmark.",
        dataset_status=fixture["status"],
    )
    (target / "trajectory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "trajectory.md").write_text(
        "# 三体系标注路线集成回放\n\n"
        + report["scope"]
        + "\n\n"
        + f"通过{report['passed']}，失败{report['failed']}，跳过{report['skipped']}。\n\n"
        + "\n".join(
            f"- {r['id']}: {r['status']} {r.get('reason', r.get('error') or '')}" for r in rows
        )
        + "\n",
        encoding="utf-8",
    )
    return report
