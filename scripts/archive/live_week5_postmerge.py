"""Reproducible real-model checks with per-draft checkpoints and existing runtime rubric."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app import ROOT, build_model
from common.schemas import Reading
from evals import reviewer
from scripts import live_week23
from signals.merge import merge_signals, model_view, undisclosed


def check_disclosure_output(content, field, merged):
    reading = Reading(
        question_type="timing",
        systems_used=["astro", "bazi"],
        summary="合成区间内存在方向相反的张力。",
        evidence=[dict(ref_id="synthetic", reading="合成信号")],
        tensions=content["tensions"],
        confidence=dict(level="low", reason="合成测试"),
        safety=dict(flag=False, note=""),
    )
    missing = undisclosed(merged, reading)
    dates = re.compile(r"2026-11-\d{2}|11月(?:1|20)日")
    exclusive = all(
        all(
            not dates.search(str(entry.model_dump()[key]))
            for key in ("theme", "sides", "how_to_read")
            if key != field
        )
        for entry in reading.tensions
    )
    expected = [
        (("2026-11-01", "11月1日"), {"占星|astro": "有利", "八字|bazi": "压力"}),
        (("2026-11-20", "11月20日"), {"占星|astro": "压力", "八字|bazi": "有利"}),
    ]
    directions = all(
        any(
            any(day in str(entry.model_dump()[field]) for day in aliases)
            and all(
                any(re.search(system, side) and value in side for side in entry.sides)
                for system, value in sides.items()
            )
            for entry in reading.tensions
        )
        for aliases, sides in expected
    )
    reading.tensions.pop()
    negative = len(undisclosed(merged, reading)) == 1
    return dict(
        passed=not missing and exclusive and directions and negative,
        missing=missing,
        date_only_in_requested_field=exclusive,
        directions_correct=directions,
        omission_rejected=negative,
    )


async def disclosure_boundaries(output):
    """Synthetic direction reversal; deliberately move dates between visible fields."""
    signals = [
        dict(
            ref_id=f"{system}:{day}",
            system=system,
            theme="career",
            valence=value,
            strength=0.6,
            horizon="timing",
            timeframe=f"2026-11-{day:02}",
            keywords=[],
            kb_ref="synthetic",
            kb_refs=["synthetic"],
            rule_version=1,
            reviewed=False,
        )
        for day, directions in [
            (1, {"astro": 0.2, "bazi": -0.2}),
            (20, {"astro": -0.2, "bazi": 0.2}),
        ]
        for system, value in directions.items()
    ]
    merged = merge_signals(signals)
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    model = build_model(config["llm"]["provider"], config["models"]["orchestrator"], config, None)
    rows = []
    try:
        for field in ("theme", "sides", "how_to_read"):
            started = time.perf_counter()
            attempts = model.request_attempts
            row = dict(field=field, passed=False)
            try:
                reply = await model.chat(
                    [
                        dict(
                            role="system",
                            content=(
                                "合成测试，不涉及真实预测。根据给定合并表输出严格JSON对象，"
                                "唯一键tensions是两条张力列表，每条包含theme、sides、how_to_read。"
                                "theme使用career；sides准确写出占星和八字的方向，用有利表示正向、"
                                "压力表示负向；how_to_read解释两个体系的分歧。必须区分11月1日"
                                "与11月20日的反向结论。日期只放进用户指定的字段，其他字段不得出现日期。"
                            ),
                        ),
                        dict(
                            role="user",
                            content=json.dumps(
                                dict(date_field=field, merge=model_view(merged)), ensure_ascii=False
                            ),
                        ),
                    ],
                    [],
                )
                content = json.loads(reply.text.strip().removeprefix("```json").removesuffix("```"))
                row.update(check_disclosure_output(content, field, merged))
                row.update(
                    output=content,
                    returned_model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                    usage_available=reply.usage_available,
                )
            except Exception as exc:
                row["error_type"] = type(exc).__name__
            row.update(
                latency_s=round(time.perf_counter() - started, 3),
                request_attempts=model.request_attempts - attempts,
            )
            rows.append(row)
            (output / "boundary.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        await model.close()
    return all(r["passed"] for r in rows)


async def run(args):
    if args.env_file:
        load_dotenv(args.env_file)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.suite == "boundary":
        return await disclosure_boundaries(args.output)
    if args.suite == "reviewer":
        rows = []
        original_score = reviewer.score

        def checkpoint(item, record):
            row = original_score(item, record)
            rows.append(row)
            (args.output / "progress.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {k: row[k] for k in ("id", "cls", "verdict", "status", "correct")},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return row

        reviewer.score = checkpoint
        try:
            report = await reviewer.evaluate(
                args.output,
                provider=yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["llm"][
                    "provider"
                ],
                strictness=args.strictness,
            )
        finally:
            reviewer.score = original_score
        print(
            json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False),
            flush=True,
        )
        return report["unavailable"] == 0 and all(g["met"] for g in report["gates"].values())

    # Keep the existing integration harness and rubric unchanged. Add a preference-bearing
    # timing turn and a new-session follow-up to exercise stored merge snapshots.
    original_cases = live_week23.CASES
    cases = [dict(c) for c in original_cases]
    for case in cases:
        if case["id"] == "three_system_timing":
            case["question"] += "我更信八字，请记住这个偏好。"
    cases.append(
        dict(
            id="week5_followup",
            parent="three_system_timing",
            question=(
                "我不是不信八字，这句话没有降低八字权重的意思。请读取上次记录，"
                "解释之前占星与八字的分歧，保留各自方向和日期范围，不要重新排盘或抽牌。"
            ),
            tools={"read_reading", "submit_reading"},
            systems={"astro", "bazi", "tarot"},
            followup=True,
        )
    )
    live_week23.CASES = cases
    original_grounded = live_week23.grounded_payload

    def with_history(runtime, outcome):
        facts = original_grounded(runtime, outcome)
        if runtime.session.state.get("response_mode") == "followup":
            saved = runtime.store.get_reading(
                runtime.session.user_id, runtime.session.state["active_reading_id"]
            )
            facts["saved_reading"] = {
                k: saved[k] for k in ("question", "systems_used", "output_json", "merge_json")
            }
        elif runtime.session.state.get("question") == next(
            c["question"] for c in cases if c["id"] == "three_system_timing"
        ):
            # A follow-up must inherit the actual saved systems, including a degraded parent.
            next(c for c in cases if c["id"] == "week5_followup")["systems"] = set(
                outcome.data.get("reading", {}).get("systems_used", [])
            )
        return facts

    live_week23.grounded_payload = with_history
    try:
        report = await live_week23.evaluate(
            args.output,
            selected=[
                "bazi_trait",
                "bazi_followup",
                "astro_timing",
                "three_system_timing",
                "unknown_time",
                "week5_followup",
            ],
            judge=True,
            mode="multi",
        )
    finally:
        live_week23.CASES = original_cases
        live_week23.grounded_payload = original_grounded
    rows = {r["id"]: r for r in report["results"]}
    before = rows["three_system_timing"]["calculated_facts"]["verified_profile"].get(
        "system_weights", {}
    )
    after = rows["week5_followup"]["calculated_facts"]["verified_profile"].get("system_weights", {})
    boundary = dict(
        initial_weights=before,
        followup_weights=after,
        explicit_preference_saved=before.get("bazi", 1) > 1,
        double_negation_preserves_weights=bool(before) and before == after,
    )
    (args.output / report["run_id"] / "boundary-checks.json").write_text(
        json.dumps(boundary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(boundary, ensure_ascii=False), flush=True)
    return report["passed"] == report["cases"] and all(
        boundary[k] for k in ("explicit_preference_saved", "double_negation_preserves_weights")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=["reviewer", "runtime", "boundary"])
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--strictness", choices=["lenient", "strict"], default="lenient")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/week5-postmerge/live")
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(args)) else 1)


if __name__ == "__main__":
    main()
