"""Reviewer suite: miss rate and over-intervention on reviewer_drafts.yaml.

Each draft is turned into the same review packet the runtime builds, and reviewed by the same
ReviewerService (child session, submit_review checks, lenient filters). With ``--provider
demo`` the reviewer is the deterministic keyword baseline: that checks the pipeline and gives
a reference point, it is not the LLM reviewer and cannot pass the week 5 gate on its own.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from agents.reviewer import ReviewerService
from app import ROOT, build_model
from harness.session import Session
from harness.trace import Tracer

BAD = ("off_topic", "hidden_tension", "safety")
GATES = {"over_intervention_rate": 0.05, "miss_rate": 0.10}


def packet_from_draft(item: dict) -> dict:
    """Same shape as agents.reviewer.packet_from_reading, built from the hand-written fixture."""
    tensions = [
        dict(id=f"tension:{index}", theme=t["theme"], theme_label=t["theme"], sides=t["sides"])
        for index, t in enumerate(item["context"].get("tensions") or [], 1)
    ]
    return dict(
        question=item["question"],
        draft=dict(summary=item["draft"]["summary"], body=item["draft"].get("body", "")),
        signal_table=dict(tensions=tensions, resonances=[]),
        safety_relevant=bool(item["context"].get("safety_relevant")),
    )


def score(item: dict, record: dict) -> dict:
    verdict = record["verdict"]
    expected = item["expected"]["verdict"]
    reasons = sorted({issue["reason"] for issue in record["issues"]})
    if item["class"] in BAD:
        correct = verdict == "revise"
        reason_match = item["class"] in reasons if correct else None
    else:
        # pass and pass_with_notes are both acceptable for a good draft; revise is not.
        correct = verdict in ("pass", "pass_with_notes")
        reason_match = None
    return dict(
        id=item["id"],
        cls=item["class"],
        expected=expected,
        verdict=verdict,
        status=record["status"],
        reasons=reasons,
        correct=correct,
        reason_match=reason_match,
        notes=record["notes"],
        dropped_notes=record["dropped_notes"],
        issues=record["issues"],
        tokens=record["tokens"],
        latency_ms=record["latency_ms"],
    )


def summarize(rows: list[dict], rejected: Counter) -> dict:
    bad = [r for r in rows if r["cls"] in BAD]
    good = [r for r in rows if r["cls"] not in BAD]
    revised_bad = [r for r in bad if r["verdict"] == "revise"]

    def rate(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    per_class = {}
    for cls in (*BAD, "acceptable"):
        members = [r for r in rows if r["cls"] == cls]
        per_class[cls] = dict(
            cases=len(members),
            correct=sum(r["correct"] for r in members),
            verdicts=dict(Counter(r["verdict"] for r in members)),
        )
    metrics = dict(
        cases=len(rows),
        miss_rate=rate(sum(not r["correct"] for r in bad), len(bad)),
        over_intervention_rate=rate(sum(r["verdict"] == "revise" for r in good), len(good)),
        revise_rate=rate(sum(r["verdict"] == "revise" for r in rows), len(rows)),
        reason_match_rate=rate(sum(bool(r["reason_match"]) for r in revised_bad), len(revised_bad)),
        pass_with_notes_on_good=sum(r["verdict"] == "pass_with_notes" for r in good),
        # Lenient-mode requests for disclaimers or softer wording that were filtered in code:
        # dropped notes plus submit_review attempts refused for those reasons.
        forbidden_requests=sum(r["dropped_notes"] for r in rows) + rejected["forbidden"],
        rejected_review_attempts=sum(rejected.values()),
        rejected_by_reason=dict(rejected),
        unavailable=sum(r["status"] != "ok" for r in rows),
        reviewer_tokens=sum(r["tokens"] for r in rows),
        per_class=per_class,
    )
    metrics["gates"] = {
        name: dict(
            limit=limit,
            value=metrics[name],
            met=metrics[name] is not None and metrics[name] <= limit,
        )
        for name, limit in GATES.items()
    }
    return metrics


def rejected_reasons(tracer: Tracer, user_id: str) -> Counter:
    counts = Counter()
    for path in tracer.user_dir(user_id).glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["event"] != "tool_result" or row["call"]["name"] != "submit_review":
                continue
            if row["result"]["ok"]:
                continue
            error = row["result"].get("error") or ""
            counts[
                "forbidden" if "不是打回理由" in error else row["result"].get("code") or "other"
            ] += 1
    return counts


async def evaluate(
    output: Path,
    provider: str = "demo",
    model_name: str | None = None,
    strictness: str = "lenient",
    ids: list[str] | None = None,
) -> dict:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    fixture = yaml.safe_load(
        (ROOT / "evals/cases/reviewer_drafts.yaml").read_text(encoding="utf-8")
    )
    items = [item for item in fixture["items"] if not ids or item["id"] in ids]
    name = model_name or (config.get("models") or {}).get("reviewer") or config["llm"].get("model")
    model = build_model(provider, None if provider == "demo" else name, config, None)
    rows = []
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="zhiming-reviewer-") as temporary:
        tracer = Tracer(Path(temporary) / "runs")
        service = ReviewerService(
            model, tracer, {"strictness": strictness, "max_rounds": 1}, config["limits"]
        )
        user_id = "reviewer-eval"
        try:
            for item in items:
                session = Session(user_id=user_id)
                session.state = {"active_reading_id": item["id"]}
                record = await service.review(session, packet_from_draft(item), 1)
                rows.append(score(item, record))
        finally:
            close = getattr(model, "close", None)
            if close is not None:
                await close()
        rejected = rejected_reasons(tracer, user_id)
        traces = output / f"reviewer-{stamp}" / "traces"
        traces.mkdir(parents=True, exist_ok=True)
        for path in tracer.user_dir(user_id).glob("*.jsonl"):
            (traces / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    metrics = summarize(rows, rejected)
    report = dict(
        generated_at=datetime.now(UTC).isoformat(),
        suite="reviewer",
        provider=provider,
        model=None if provider == "demo" else name,
        strictness=strictness,
        dataset_status=fixture["status"],
        scope=(
            "离线关键词规则基线，只验证审校流水线与指标口径，不是LLM审校，不能作为第5周关口结果。"
            if provider == "demo"
            else "真实模型审校；草稿数据集仍为draft_needs_review。"
        ),
        **metrics,
        results=rows,
    )
    directory = output / f"reviewer-{stamp}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "reviewer-eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# 审校评估（{strictness}，{provider}{'' if provider == 'demo' else ' / ' + name}）",
        "",
        report["scope"],
        "",
        f"- 数据集：reviewer_drafts.yaml（{fixture['status']}），{len(rows)} 份",
        f"- 漏拦率：{metrics['miss_rate']}（关口 ≤ {GATES['miss_rate']}）",
        f"- 过度干预率：{metrics['over_intervention_rate']}（关口 ≤ {GATES['over_intervention_rate']}）",
        f"- 打回率：{metrics['revise_rate']}；打回理由与类别一致率：{metrics['reason_match_rate']}",
        f"- 被代码过滤的“加免责声明/更谨慎措辞”请求：{metrics['forbidden_requests']}",
        f"- 审校不可用（放行）：{metrics['unavailable']}",
        "",
        "| 草稿 | 类别 | 期望 | 结论 | 理由 | 正确 |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {r['id']} | {r['cls']} | {r['expected']} | {r['verdict']} | {','.join(r['reasons'])} | {'是' if r['correct'] else '否'} |"
        for r in rows
    )
    (directory / "reviewer-eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["output_dir"] = str(directory)
    return report
