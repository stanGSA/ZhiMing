"""Assemble first-week gate evidence from real traces, SQLite, and regression tests."""

from __future__ import annotations

import argparse
import json
import sqlite3
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from app import ROOT
from harness.session import Session
from knowledge.build import build
from plugins.tarot.draw import draw_tarot
from scripts.doctor import diagnose, probe_api


def assemble(live_path: Path, tests_path: Path, output: Path, api: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    coverage = build(output=output / "kb.sqlite")
    session = Session("gate-distribution")
    draws = []
    for _ in range(100):
        session.start_reading("独立随机抽牌分布")
        draws.append(draw_tarot("three_card", "独立随机抽牌分布", session.state["seed"]))
    distribution = {
        "draws": 100,
        "unique_seeds": len({d["seed"] for d in draws}),
        "unique_card_sequences": len({json.dumps(d["cards"], sort_keys=True) for d in draws}),
        "card_frequency": dict(Counter(c["card_id"] for d in draws for c in d["cards"])),
        "orientation_frequency": dict(
            Counter(str(c["reversed"]) for d in draws for c in d["cards"])
        ),
        "raw_draws": draws,
    }
    (output / "production-distribution.json").write_text(
        json.dumps(distribution, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    repeat = {
        spread: all(
            draw_tarot(spread, "复现", 42) == draw_tarot(spread, "复现", 42) for _ in range(100)
        )
        for spread in ("single", "three_card", "decision")
    }
    tests = ET.parse(tests_path).getroot()
    cases = list(tests.iter("testcase"))
    failed = [
        c.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None
    ]
    required_tests = [
        "test_same_draw_cached_changed_draw_blocked",
        "test_guard_errors_are_results",
        "test_profile_evidence_and_cache",
        "test_cross_session_followup",
        "test_redraw_changes_seed_and_preserves_parent",
        "test_original_crisis_fixtures",
        "test_original_mt11_safety_transition",
        "test_seed_changes_and_both_orientations",
        "test_explicit_spread_cannot_be_changed_by_model",
    ]
    test_checks = {
        name: any(
            c.get("name", "").startswith(name)
            and c.find("failure") is None
            and c.find("error") is None
            and c.find("skipped") is None
            for c in cases
        )
        for name in required_tests
    }
    live = json.loads(live_path.read_text(encoding="utf-8"))
    db = sqlite3.connect(ROOT / "data/app.db")
    db.row_factory = sqlite3.Row
    try:
        schema_version = db.execute("PRAGMA user_version").fetchone()[0]
        schema = [
            dict(r)
            for r in db.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        counts = {
            r["name"]: db.execute(
                'SELECT count(*) FROM "' + r["name"].replace('"', '""') + '"'
            ).fetchone()[0]
            for r in schema
        }
        replay = []
        all_events = []
        for path in dict.fromkeys(row["trace"] for row in live["results"]):
            events = [
                json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            ]
            all_events += events
            for event in events:
                if event["event"] != "tool_result":
                    continue
                data = event["result"]["data"]
                item = {
                    "trace": path,
                    "tool": event["call"]["name"],
                    "call": event["call"],
                    "ok": event["result"]["ok"],
                }
                if item["tool"] == "draw_tarot" and item["ok"]:
                    expected = draw_tarot(
                        data["spread"], data["question"], data["seed"], data.get("picks")
                    )
                    item["deterministic_cards_match"] = all(
                        {k: card[k] for k in expected["cards"][i]} == expected["cards"][i]
                        for i, card in enumerate(data["cards"])
                    )
                    saved = db.execute(
                        "SELECT tarot_json,signals_json,kb_version FROM readings WHERE reading_id=?",
                        (data["reading_id"],),
                    ).fetchone()
                    item["persisted_draw_matches"] = bool(
                        saved
                        and json.loads(saved["tarot_json"])
                        == {k: v for k, v in data.items() if k != "signals"}
                    )
                    item["persisted_signals_match"] = bool(
                        saved and json.loads(saved["signals_json"]) == data["signals"]
                    )
                    item["version_snapshot_exists"] = bool(
                        saved
                        and (ROOT / "data/kb_versions" / (saved["kb_version"] + ".sqlite")).exists()
                    )
                if item["tool"] == "submit_reading" and item["ok"]:
                    if data.get("response_id"):
                        saved = db.execute(
                            "SELECT output_json FROM reading_responses WHERE response_id=? AND reading_id=?",
                            (data["response_id"], data["reading_id"]),
                        ).fetchone()
                    else:
                        saved = db.execute(
                            "SELECT output_json FROM readings WHERE reading_id=?",
                            (data["reading_id"],),
                        ).fetchone()
                    item["persisted_output_matches"] = bool(
                        saved and json.loads(saved["output_json"]) == data["reading"]
                    )
                replay.append(item)
        checks = {
            "coverage_156_plus_7": coverage["card_states"] == 156
            and coverage["positions"] == 7
            and coverage["coverage"] == 1,
            "same_seed_100_repeats": all(repeat.values()),
            "independent_100_draws": distribution["unique_seeds"] == 100
            and distribution["unique_card_sequences"] > 95,
            "pytest_no_failures": not failed and bool(cases),
            "guard_and_regressions_present": all(test_checks.values()),
            "live_strict_pass": live["passed"] == live["cases"] == live["expected_cases"],
            "trace_replay_pass": bool(replay)
            and all(
                all(v is True for k, v in r.items() if k not in ("trace", "tool", "call"))
                for r in replay
            ),
            "database_integrity": db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            and not db.execute("PRAGMA foreign_key_check").fetchall(),
        }
    finally:
        db.close()
    doctor = diagnose()
    if api:
        doctor["api_probe"] = probe_api()
        checks["api_available"] = doctor["api_probe"]["ok"]
    checks["doctor_required_ok"] = doctor["ok"]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pass": all(checks.values()),
        "checks": checks,
        "coverage": coverage,
        "deterministic_repeats": repeat,
        "distribution": {k: v for k, v in distribution.items() if k != "raw_draws"},
        "pytest": {
            "cases": len(cases),
            "failed": failed,
            "required_regressions": test_checks,
            "junit": str(tests_path.resolve()),
        },
        "live_report": str(live_path.resolve()),
        "doctor": doctor,
        "schema_version": schema_version,
        "database_schema": schema,
        "table_counts": counts,
        "replayed_tool_calls": len(replay),
        "trace_replay": replay,
        "limits": "工程门禁不等于上线许可。释义人工审核率0%；未来星历等资产可缺失。",
    }
    (output / "gate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "complete-traces.json").write_text(
        json.dumps(all_events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 第一周门禁证据包",
        "",
        f"门禁：{'通过' if report['pass'] else '未通过'}；回放工具调用：{len(replay)}。",
        "",
    ]
    lines += [f"- {k}：{'通过' if v else '失败'}" for k, v in checks.items()]
    lines += [
        "",
        "详见gate.json：知识覆盖、100次重复/随机分布、Guard回归、实际数据库表结构及完整性、自检/API探测、逐次调用重放校验。complete-traces.json保留完整参数与工具返回。",
        "",
        report["limits"],
    ]
    (output / "gate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--tests", type=Path, default=ROOT / "reports/review-fix-tests.xml")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/review-fix-gate")
    parser.add_argument("--api", action="store_true")
    args = parser.parse_args()
    report = assemble(args.live, args.tests, args.output, args.api)
    print(
        json.dumps(
            {"pass": report["pass"], "checks": report["checks"]}, ensure_ascii=False, indent=2
        )
    )
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
