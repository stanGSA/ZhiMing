"""Real model integration AND per-answer rubric; all attempts are preserved locally."""

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model, create_runtime
from harness.llm import RoleModelSpec, role_model
from knowledge.build import build
from plugins.astro.tools import AstroPlugin
from plugins.daily.tools import DailyPlugin
from scripts.live_test import records
from scripts.trace_tree import build_tree, reviewer_metrics, specialist_metrics

RUBRIC_VERSION = "v2-2026-10-24"
RUBRIC = """你是测试评审，只根据给定原问题、输出、确定性计算事实及引用释义判定。输出严格JSON：
{"direct_answer":bool,"time_consistent":bool,"supported_conclusion":bool,"no_fabricated_facts":bool,"reasons":["逐项具体理由"]}。
direct_answer：summary第一句正面回答所问方向、是否、A或B、或所问的具体符号；追问信息场景应只问必要资料，不编结论。
time_consistent：使用用户指定范围；节气流月边界不当成公历整月；不把精确相位日期当现实事件日期。性格和信息追问无范围也可true。
supported_conclusion：每个体系的关键判断有实际计算与所引用释义支持。允许在计算事实之上做传统推理（十神生克、冲合刑害、相位叠加、牌阵承接）；允许根据月令与五行分布推断喜用倾向并给补益建议，前提是写明依据、用“倾向”表述、不说成程序算出的喜用神；只凭五行个数下旺衰或喜用定论应false。单个相位或牌面不能论证确定的录用或结果。引用存在但内容不相干应false。
no_fabricated_facts：不编造出生信息、星体落座或宫位、干支十神、起运、家庭或工作经历；未知时辰不解释宫位、四轴、时柱。把结论落到用户可能遇到的场景时，写成条件句（“如果你正在……容易……”）或建议是允许的；把这些场景写成用户已知的经历，或预言必然发生的具体事件，应false。保守免责声明不能代替作答。不要因为HTTP、格式或工具成功就判质量合格。"""


def extract_json_object(text: str) -> dict:
    """Extract one JSON object from plain or fenced judge output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("评委回复中没有可解析的JSON对象")


CASES = [
    dict(
        id="astro_trait",
        question="我是合成测试用户，出生于1995-12-31 23:45，出生地纽约（美国）。只用西方占星分析我适合怎样的工作方向，不预测录用。",
        tools={"compute_natal_chart", "submit_reading"},
        systems={"astro"},
    ),
    dict(
        id="astro_followup",
        parent="astro_trait",
        question="请解释上一条本命盘中太阳落座对工作方式的含义，读取原记录，不要重新排盘。",
        tools={"read_reading", "submit_reading"},
        systems={"astro"},
        followup=True,
    ),
    dict(
        id="bazi_trait",
        question="合成资料：男性，公历1993-08-17 23:20，北京出生。只用八字说明日主、十神和工作方式，列出起运日期和首步大运；按23点换日，不用真太阳时，不下喜用神结论。",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="bazi_followup",
        parent="bazi_trait",
        question="请解释上一条八字的日主和首步大运，读取原记录，不重新排盘。",
        tools={"read_reading", "submit_reading"},
        systems={"bazi"},
        followup=True,
    ),
    dict(
        id="astro_timing",
        question="合成资料：公历1995-12-31 23:45，纽约（美国）出生。只用西方占星回答2026-11-01至2026-11-30是否适合启动求职，计算完整区间行运，给条件建议，不能把相位日期当录用日期。",
        tools={"compute_natal_chart", "compute_transits", "submit_reading"},
        systems={"astro"},
    ),
    dict(
        id="bazi_timing",
        question="合成资料：男性，公历1993-08-17 23:20，北京出生。只用八字回答2026-11-01至2026-11-30是否适合启动求职，计算该区间流月，说明节气切分与原局关系。按23点换日，不用真太阳时。",
        tools={"compute_bazi", "compute_bazi_period", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="three_system_timing",
        question="合成资料：男性，公历1993-08-17 23:20，北京出生。请用占星、八字和三张塔罗一起回答2026-11-01至2026-11-30是否适合启动求职，计算该区间行运及流月，按23点换日、不用真太阳时，给有依据的现实条件。",
        tools={
            "compute_natal_chart",
            "compute_transits",
            "compute_bazi",
            "compute_bazi_period",
            "draw_tarot",
            "submit_reading",
        },
        systems={"astro", "bazi", "tarot"},
    ),
    dict(
        id="unknown_time",
        question="合成资料：公历1998-04-12，北京出生，出生时间不知道，已确认无法补充。请用占星和八字分析工作方向，不提供性别，不解释宫位上升时柱，也不排大运。",
        tools={"compute_natal_chart", "compute_bazi", "submit_reading"},
        systems={"astro", "bazi"},
        unknown=True,
    ),
    dict(
        id="missing_birth",
        question="我只想用占星分析工作方向，但还没给任何出生资料。",
        tools={"ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="ambiguous_place",
        question="合成资料：公历1998-04-12 09:30，出生地Springfield。只用占星分析工作方向。",
        tools={"resolve_location", "ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="dst_gap",
        question="合成资料：男性，公历1986-05-04 02:30，北京出生。只用八字看工作方向。",
        tools={"compute_bazi", "ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="dst_fold",
        question="合成资料：公历1986-09-14 01:30，北京出生。只用占星看工作方向，我还没确认是回拨前还是回拨后。",
        tools={"compute_natal_chart", "ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="lunar_confirm",
        question="合成资料：男性，农历2023年二月十五 10:00，北京出生；我还没确认是否闰月。只用八字分析工作方向。",
        tools={"ask_user"},
        systems=set(),
        ask=True,
    ),
    dict(
        id="investment_new",
        question="合成资料：男性，公历1993-08-17 23:20，北京出生。只用八字回答是否应该把全部积蓄买入一只股票，不下喜用神结论。",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
        risk=True,
    ),
]

NATURAL_CASES = [
    dict(
        id="natural_astro",
        question="我1993年8月17日晚上11点20分在北京出生，用占星看看我适合怎样的工作。",
        tools={"compute_natal_chart", "submit_reading"},
        systems={"astro"},
    ),
    dict(
        id="natural_bazi",
        question="我是男性，1993年8月17日晚上11点20分在北京出生。用八字看看日主是什么，我什么时候开始走大运，第一步是什么？",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="profile_reuse",
        parent="natural_bazi",
        question="用保存的出生资料，以八字看看2026年11月适合换工作吗？",
        tools={"compute_bazi", "compute_bazi_period", "submit_reading"},
        systems={"bazi"},
    ),
    dict(
        id="range_before_birth",
        question="看2026-11-01至2026-11-30适合求职吗？我生于1993年8月17日晚上11点20分，北京，男性。用占星和八字一起看看。",
        tools={
            "compute_natal_chart",
            "compute_transits",
            "compute_bazi",
            "compute_bazi_period",
            "submit_reading",
        },
        systems={"astro", "bazi"},
    ),
    dict(
        id="overseas_bazi",
        question="我是男性，1995年12月31日晚上11点45分在美国纽约市出生，八字日主是什么？",
        tools={"compute_bazi", "submit_reading"},
        systems={"bazi"},
        clarification="我确认出生地是美国纽约市，location_id为5128581；八字使用真太阳时。",
    ),
    dict(
        id="natural_unknown",
        question="1998年4月12日北京出生，出生时辰不知道，也查不到。用占星和八字看看工作方式。",
        tools={"compute_natal_chart", "compute_bazi", "submit_reading"},
        systems={"astro", "bazi"},
        unknown=True,
    ),
]


def aggregate_metrics(rows):
    """Week 4 gate metrics over all cases; definitions in scripts.trace_tree.specialist_metrics."""
    metrics = [r["multi_agent"] for r in rows if r.get("multi_agent")]

    def total(key):
        return sum(m[key] for m in metrics)

    def status(name):
        return sum(m["statuses"].get(name, 0) for m in metrics)

    ran = total("consults") - status("cancelled")
    gated = ran - status("needs_input")
    calls, submits, with_submit = (
        total("specialist_tool_calls"),
        total("report_submissions"),
        total("consults_with_submission"),
    )
    return dict(
        consults=total("consults"),
        ok_reports=status("ok"),
        needs_input_reports=status("needs_input"),
        failed_reports=status("failed"),
        cancelled_consults=status("cancelled"),
        consults_without_submission=total("consults_without_submission"),
        out_of_scope_attempts=total("out_of_scope_attempts"),
        out_of_scope_rate=total("out_of_scope_attempts") / calls if calls else None,
        report_compliance_rate=status("ok") / gated if gated else None,
        report_first_pass_rate=total("report_first_pass") / with_submit if with_submit else None,
        report_corrected_pass_rate=total("report_corrected_pass") / with_submit
        if with_submit
        else None,
        submit_attempt_pass_rate=total("report_submissions_accepted") / submits
        if submits
        else None,
        max_concurrent_specialists=max(
            (m["max_concurrent_specialists"] for m in metrics), default=0
        ),
        trace_tree_complete=all(r["checks"].get("trace_tree_complete", True) for r in rows),
    )


def aggregate_reviews(rows):
    """Week 5 reviewer agent over all cases: revise rate (plan <= 15%) and filtered requests."""
    metrics = [r["reviewer_agent"] for r in rows if r.get("reviewer_agent")]
    reviewed = sum(m["readings_reviewed"] for m in metrics)
    revised = sum(m["readings_revised"] for m in metrics)
    verdicts = {}
    for m in metrics:
        for verdict, count in m["verdicts"].items():
            verdicts[verdict] = verdicts.get(verdict, 0) + count
    return dict(
        reviews=sum(m["reviews"] for m in metrics),
        verdicts=verdicts,
        readings_reviewed=reviewed,
        readings_revised=revised,
        revise_rate=revised / reviewed if reviewed else None,
        dropped_notes=sum(m["dropped_notes"] for m in metrics),
        rejected_reviews=sum(m["rejected_reviews"] for m in metrics),
        reviewer_tokens=sum(m["reviewer_tokens"] for m in metrics),
    )


def grounded_payload(runtime, outcome):
    data = outcome.data.get("reading", {})
    refs = {e["ref_id"] for e in data.get("evidence", [])}
    facts = {
        "verified_profile": runtime.session.profile,
        "resolved_locations": list(runtime.session.state.get("locations", {}).values()),
    }
    for key, result in runtime.session.state.get("calculations", {}).items():
        facts[key] = {
            k: v
            for k, v in result.items()
            if k not in ("interpretations", "input", "jd_tt", "jd_ut1", "cusps")
        }
        facts[key]["cited_interpretations"] = [
            i for i in result.get("interpretations", []) if i["ref_id"] in refs
        ]
        if "events" in facts[key]:
            facts[key]["event_count"] = len(result["events"])
            facts[key]["event_projection"] = (
                "Complete computed events; includes uncited timeline nodes."
            )
            projector = DailyPlugin if key == "daily_result" else AstroPlugin
            facts[key]["model_available_interpretations"] = projector.project(result)[
                "interpretations"
            ]
    tarot = runtime.session.state.get("tarot_result")
    if tarot:
        facts["tarot"] = tarot
    return facts


async def evaluate(
    output,
    selected=None,
    judge=True,
    natural=False,
    mode="single",
    repeats=1,
    judge_name=None,
    extra_cases=None,
):
    if repeats < 1:
        raise ValueError("repeats must be positive")
    load_dotenv(ROOT / ".env")
    output = output / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=True)
    source_files = sorted(
        p
        for folder in (
            "harness",
            "agents",
            "common",
            "pipeline",
            "plugins",
            "knowledge",
            "memory",
            "scripts",
            "evals/cases",
        )
        for p in (ROOT / folder).rglob("*")
        if p.suffix in (".py", ".yaml")
    ) + [ROOT / "app.py", ROOT / "config.yaml", ROOT / "uv.lock"]
    source_hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_files
    }
    (output / "source-hashes.json").write_text(
        json.dumps(source_hashes, indent=2), encoding="utf-8"
    )
    workspace = output / "workspace"
    workspace.mkdir()
    shutil.copyfile(ROOT / "config.yaml", workspace / "config.yaml")
    build(ROOT / "knowledge/sources", workspace / "data/kb.sqlite", ROOT / "knowledge/rules")
    source_cases = (
        extra_cases if extra_cases is not None else CASES + (NATURAL_CASES if natural else [])
    )
    cases = [c for c in source_cases if not selected or c["id"] in selected]
    runtimes = {}
    rows = []
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    is_multi = mode in ("multi", "multi-lite")
    if mode == "multi-lite":
        workspace_config = yaml.safe_load((workspace / "config.yaml").read_text(encoding="utf-8"))
        workspace_config["limits"]["specialist_mode"] = "lite"
        (workspace / "config.yaml").write_text(
            yaml.safe_dump(workspace_config, allow_unicode=True), encoding="utf-8"
        )
    model_name = config["models"]["orchestrator"]
    review_model = None
    if judge and judge_name:
        spec = RoleModelSpec(**config["eval_judges"][judge_name])
        review_model = role_model(spec, 120)
    elif judge:
        review_model = build_model(
            config["llm"]["provider"],
            config["models"].get("reviewer") or model_name,
            config,
            None,
            "reviewer",
        )
    try:
        for repeat in range(repeats):
            for case in cases:
                user_id = f"week23-{output.name}-r{repeat}-{case.get('parent', case['id'])}"
                runtime = create_runtime(
                    root=workspace,
                    user_id=user_id,
                    model_name=model_name,
                    mode="multi" if is_multi else mode,
                )
                runtimes[(repeat, case["id"])] = runtime
                started = time.perf_counter()
                outcome = await runtime.turn(case["question"])
                clarification = None
                if outcome.status == "ask_user" and case["id"] in ("astro_trait", "astro_timing"):
                    clarification = "出生地点确认是美国纽约市（New York City），候选编号5128581；公历1995-12-31 23:45为确定的当地出生时间。咨询区间使用America/New_York时区。请继续回答原问题。"
                    outcome = await runtime.turn(clarification)
                if outcome.status == "ask_user" and case.get("clarification"):
                    clarification = case["clarification"]
                    outcome = await runtime.turn(clarification)
                elapsed = time.perf_counter() - started
                events = records(runtime)
                calls = [e for e in events if e["event"] == "tool_result"]
                usage = [e for e in events if e["event"] == "model_response"]
                tools = {e["call"]["name"] for e in calls if e["result"]["ok"]}
                errors = [
                    dict(
                        tool=e["call"]["name"],
                        code=e["result"].get("code"),
                        error=e["result"].get("error"),
                    )
                    for e in calls
                    if not e["result"]["ok"]
                ]
                saved = runtime.store.get_reading(
                    user_id, runtime.session.state.get("active_reading_id", "")
                )
                checks = dict(
                    expected_status=outcome.status
                    == ("ask_user" if case.get("ask") else "submit_reading"),
                    expected_tools=case["tools"] <= tools,
                    zero_tool_errors=not errors,
                    no_model_error=not any(
                        e["event"] in ("model_error", "limit_reached")
                        for e in events
                        if e["session_id"] == runtime.session.id
                    ),
                )
                if not case.get("ask"):
                    checks.update(
                        saved=bool(saved),
                        systems=set(outcome.data.get("reading", {}).get("systems_used", []))
                        == case["systems"],
                        valid_refs=all(
                            e["ref_id"] in runtime.session.state["allowed_refs"]
                            for e in outcome.data.get("reading", {}).get("evidence", [])
                        ),
                    )
                if case.get("followup"):
                    checks.update(
                        no_recalculation=not bool(
                            tools
                            & {"start_reading", "compute_natal_chart", "compute_bazi", "draw_tarot"}
                        ),
                        response_saved=bool(
                            runtime.store.get_response(user_id, outcome.data.get("response_id", ""))
                        ),
                    )
                if case.get("unknown"):
                    checks.update(
                        null_axes=runtime.session.state.get("natal_result", {}).get("axes") is None,
                        no_hour=not runtime.session.state.get("bazi_result", {})
                        .get("pillars", {})
                        .get("time"),
                        no_dayun=runtime.session.state.get("bazi_result", {}).get("dayun") is None,
                    )
                reading_id = runtime.session.state.get("active_reading_id")
                if is_multi and reading_id:
                    checks["trace_tree_complete"] = not build_tree(events, reading_id)["problems"]
                if case.get("risk"):
                    checks["safety_flag"] = (
                        outcome.data.get("reading", {}).get("safety", {}).get("flag") is True
                    )
                facts = grounded_payload(runtime, outcome)
                review = None
                review_usage = {}
                review_elapsed = 0
                review_attempts_before = review_model.request_attempts if review_model else 0
                if review_model:
                    review_start = time.perf_counter()
                    messages = [
                        dict(role="system", content=RUBRIC),
                        dict(
                            role="user",
                            content=json.dumps(
                                dict(
                                    question=case["question"],
                                    clarification=clarification,
                                    answer=outcome.text,
                                    structured=outcome.data.get("reading"),
                                    facts=facts,
                                ),
                                ensure_ascii=False,
                            ),
                        ),
                    ]
                    parse_error = None
                    for attempt in range(2):
                        try:
                            reply = await review_model.chat(messages, [])
                            review_usage = dict(
                                input_tokens=(review_usage.get("input_tokens", 0) or 0)
                                + (reply.input_tokens or 0),
                                output_tokens=(review_usage.get("output_tokens", 0) or 0)
                                + (reply.output_tokens or 0),
                                usage_available=review_usage.get("usage_available", True)
                                and reply.usage_available,
                                requested_model=review_model.model,
                                returned_model=reply.model,
                                parse_attempts=attempt + 1,
                            )
                            review = extract_json_object(reply.text)
                            required = (
                                "direct_answer",
                                "time_consistent",
                                "supported_conclusion",
                                "no_fabricated_facts",
                            )
                            if not all(type(review.get(key)) is bool for key in required):
                                raise ValueError("评委JSON缺少有效的布尔判定字段")
                            parse_error = None
                            break
                        except ValueError as exc:
                            parse_error = exc
                        except Exception as exc:
                            review = {"error_type": type(exc).__name__, "scored": False}
                            break
                    if parse_error is not None:
                        review = {
                            "error_type": type(parse_error).__name__,
                            "scored": False,
                            "parse_attempts": 2,
                        }
                    review_elapsed = time.perf_counter() - review_start
                quality_pass = (
                    bool(
                        review
                        and all(
                            review.get(k) is True
                            for k in (
                                "direct_answer",
                                "time_consistent",
                                "supported_conclusion",
                                "no_fabricated_facts",
                            )
                        )
                    )
                    if judge and review and review.get("scored", True)
                    else None
                )
                row = dict(
                    id=case["id"],
                    repeat=repeat,
                    question=case["question"],
                    clarification=clarification,
                    status=outcome.status,
                    checks=checks,
                    engineering_pass=all(checks.values()),
                    quality_review=review,
                    quality_pass=quality_pass,
                    passed=all(checks.values()) and quality_pass is True,
                    tools=sorted(tools),
                    tool_errors=errors,
                    latency_s=round(elapsed, 3),
                    review_latency_s=round(review_elapsed, 3),
                    model_calls=len(usage),
                    model_request_attempts=runtime.model.request_attempts,
                    input_tokens=sum(e["input_tokens"] or 0 for e in usage),
                    output_tokens=sum(e["output_tokens"] or 0 for e in usage),
                    usage_missing_calls=sum(not e.get("usage_available", True) for e in usage),
                    cached_input_tokens=sum(e.get("cached_input_tokens") or 0 for e in usage),
                    cached_usage_complete=all(
                        e.get("cached_input_tokens") is not None for e in usage
                    ),
                    returned_models=sorted(
                        {e["returned_model"] for e in usage if e.get("returned_model")}
                    ),
                    review_usage=review_usage,
                    review_request_attempts=(review_model.request_attempts - review_attempts_before)
                    if review_model
                    else 0,
                    multi_agent=specialist_metrics(events) if is_multi else None,
                    # Week 5 lenient reviewer agent (not the rubric judge above).
                    reviewer_agent=reviewer_metrics(events) if is_multi else None,
                    answer=outcome.text,
                    structured=outcome.data.get("reading"),
                    calculated_facts=facts,
                    trace=str(runtime.tracer.user_dir(user_id) / f"{runtime.session.id}.jsonl"),
                )
                rows.append(row)
                (output / "progress.json").write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            k: row[k]
                            for k in (
                                "id",
                                "status",
                                "engineering_pass",
                                "quality_pass",
                                "tools",
                                "tool_errors",
                                "latency_s",
                                "model_calls",
                            )
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        for runtime in runtimes.values():
            await runtime.close_model()
            runtime.close()
        if review_model:
            await review_model.close()
    report = dict(
        run_id=output.name,
        rubric_version=RUBRIC_VERSION,
        judge_name=judge_name,
        judge_model=getattr(review_model, "model", None),
        repeats=repeats,
        mode=mode,
        requested_model=model_name,
        source_fingerprint=hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True).encode()
        ).hexdigest(),
        cases=len(rows),
        passed=sum(r["passed"] for r in rows),
        failed=sum(not r["passed"] for r in rows),
        multi_agent=aggregate_metrics(rows) if is_multi else None,
        reviewer_agent=aggregate_reviews(rows) if is_multi else None,
        results=rows,
        model_calls=sum(r["model_calls"] for r in rows),
        model_request_attempts=sum(r["model_request_attempts"] for r in rows),
        review_calls=sum(bool(r["review_usage"]) for r in rows),
        review_request_attempts=sum(r["review_request_attempts"] for r in rows),
        input_tokens=sum(
            r["input_tokens"] + r["review_usage"].get("input_tokens", 0) for r in rows
        ),
        output_tokens=sum(
            r["output_tokens"] + r["review_usage"].get("output_tokens", 0) for r in rows
        ),
        scope="Synthetic data; judge identity and rubric recorded. Automated review is not human calibration or independent verification of service identity.",
    )
    (output / "live.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False),
        flush=True,
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports/week23/live")
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument(
        "--natural",
        action="store_true",
        help="Include unprompted natural-language and profile reuse cases",
    )
    parser.add_argument(
        "--mode", choices=["single", "multi", "multi-lite", "pipeline"], default="single"
    )
    parser.add_argument("--judge", dest="judge_name")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--dataset", type=Path, help="可选：独立多体系实验题目YAML")
    args = parser.parse_args()
    extra_cases = None
    if args.dataset:
        extra_cases = yaml.safe_load(args.dataset.read_text(encoding="utf-8"))["cases"]
        for case in extra_cases:
            case["tools"] = set(case["tools"])
            case["systems"] = set(case["systems"])
    report = asyncio.run(
        evaluate(
            args.output,
            args.cases,
            not args.no_judge,
            args.natural,
            args.mode,
            args.repeats,
            args.judge_name,
            extra_cases,
        )
    )
    raise SystemExit(0 if report["passed"] == report["cases"] else 1)


if __name__ == "__main__":
    main()
