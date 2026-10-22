"""Owner-approved system-level acceptance over ALL review and re-review batches.

Keep earlier rejected content versions in calibration samples. Coverage uses the
latest verdict for each current content hash. Never interpret a missing call as a
verdict. A small batch's failure or undefined kappa remains in its own report.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from knowledge.review import approval, content_hash, load_ledgers, write_ledger
from scripts import model_review_kb as review

# The 2026-10-21 campaign had no preregistration; its owner-approved basis stays as recorded.
LEGACY_BASIS = (
    "负责人确认：按体系汇总全部初审及复审样本；通过率按当前内容哈希；"
    "kappa按全部真实及埋错样本的放行二分类计算，原三分类指标保留"
)
LEGACY_KAPPA = dict(
    scope="全部批次第一轮真实及埋错样本；第二轮另计重跑一致率",
    classes={"pass": "放行", "revise": "不通过", "reject": "不通过"},
    limitation="埋错样本改变类别分布，不能与仅真实条目的三分类kappa直接比较",
    owner_reply="同意：全部样本、放行二分类（推荐）",
)
PREREGISTRATION = "preregistration.json"
SYSTEMS = ("tarot", "astro", "bazi", "name", "dream", "daily")


def deviations(manifest, prereg, system):
    """How a batch departs from the pre-registered campaign; any departure blocks acceptance."""
    found = []
    for key in ("rubric_sha256", "reviewers", "passes"):
        if manifest.get(key) != prereg[key]:
            found.append(key)
    for key in ("batch_size", "plant_rate", "min_planted"):
        if manifest.get(key) != prereg["plan"][key]:
            found.append(key)
    carried = manifest.get("calibration")
    if carried and (
        carried["lock_sha256"] != prereg["calibration"]["lock_sha256"]
        or carried.get("partition") != prereg["calibration"]["partition"]
    ):
        found.append("calibration")
    # The initial review must see exactly the registered knowledge base.
    if not manifest.get("only_ids") and manifest.get("source_files") != (
        prereg["knowledge_base"]["source_files"].get(system)
    ):
        found.append("knowledge_base")
    if system not in prereg["systems"]:
        found.append("system")
    return found


def summarize(workspace, paths, system, prereg=None):
    """``prereg`` is the run root's preregistration.json, or None for a campaign that had none
    (2026-10-21): kappa then keeps that campaign's owner-approved basis."""
    entries = {e["id"]: e for e in review.load_entries(workspace.sources, system)}
    pairs, all_pairs, outcomes, batches = [], [], {}, []
    calibration_rows, calibration_runs, departures = [], [], {}
    detection = {r: [0, 0] for r in review.REVIEWERS}
    rerun = {r: [0, 0] for r in review.REVIEWERS}
    merged = [0, 0]
    complete = True
    identities = set()
    for path in paths:
        plan = review.load_plan(path)
        run = review.RunDir(path)
        manifest = review.read_json(path / "manifest.json")
        if manifest["system"] != system:
            continue
        identities.add(review.canonical({k: manifest[k] for k in ("reviewers", "rubric_sha256")}))
        if prereg and deviations(manifest, prereg, system):
            departures[path.as_posix()] = deviations(manifest, prereg, system)
        expected = {
            (b["batch"], role, n)
            for b in plan["batches"]
            for role in review.REVIEWERS
            for n in range(1, manifest["passes"] + 1)
        }
        actual = {(c["batch"], c["reviewer"], c["run_pass"]) for c in run.calls()}
        complete &= expected == actual and manifest["passes"] == 2
        verdicts = review.collect(run, plan)
        refs = {e["id"] for e in plan["entries"]} | {p["ref"] for p in plan["planted"]}
        blind = refs | {c["ref"] for c in plan["calibration"]}
        complete &= all(
            set(verdicts.get((role, number), {})) == blind
            for role in review.REVIEWERS
            for number in (1, 2)
        )
        first = {role: verdicts.get((role, 1), {}) for role in review.REVIEWERS}
        if plan["calibration"]:
            calibration_runs.append(path.as_posix())
            calibration_rows += [
                dict(
                    label=c["label"],
                    **{r: first[r].get(c["ref"], {}).get("verdict") for r in review.REVIEWERS},
                )
                for c in plan["calibration"]
            ]
        for ref in sorted(refs):
            if all(ref in first[r] for r in review.REVIEWERS):
                all_pairs.append(tuple(first[r][ref]["verdict"] for r in review.REVIEWERS))
        blocked = {f["id"] for f in plan["checks"] if f["check"] in review.BLOCKING_CHECKS}
        for entry in plan["entries"]:
            ref = entry["id"]
            if all(ref in first[r] for r in review.REVIEWERS):
                pairs.append(tuple(first[r][ref]["verdict"] for r in review.REVIEWERS))
            recorded = [
                verdicts.get((r, n), {}).get(ref, {}).get("verdict")
                for r in review.REVIEWERS
                for n in (1, 2)
            ]
            if ref in entries and content_hash(entries[ref]) == manifest["entry_hashes"][ref]:
                # Any later rejection revokes a same-hash approval, even if incomplete.
                if any(v in ("revise", "reject") for v in recorded) or ref in blocked:
                    outcomes[ref] = dict(approved=False, path=path, manifest=manifest)
                elif all(v == "pass" for v in recorded):
                    outcomes[ref] = dict(approved=True, path=path, manifest=manifest)
        for role in review.REVIEWERS:
            again = verdicts.get((role, 2), {})
            for ref in first[role]:
                if ref in again:
                    rerun[role][0] += first[role][ref]["verdict"] == again[ref]["verdict"]
                    rerun[role][1] += 1
        for plant in plan["planted"]:
            ref = plant["ref"]
            if not all(ref in first[r] for r in review.REVIEWERS):
                complete = False
                continue
            flags = [first[r][ref]["verdict"] != "pass" for r in review.REVIEWERS]
            for role, flag in zip(review.REVIEWERS, flags, strict=True):
                detection[role][0] += flag
                detection[role][1] += 1
            merged[0] += any(flags)
            merged[1] += 1
        result = review.metrics(plan, verdicts)
        batches.append(
            dict(
                path=path.as_posix(),
                entries=len(plan["entries"]),
                metrics=result["values"],
                gates=result["gates"],
                errors=len(run.errors()),
                usage=review.usage_summary(run, {}),
            )
        )
    complete &= bool(batches) and len(identities) == 1

    def rate(pair):
        return pair[0] / pair[1] if pair[1] else None

    values = dict(
        detection={r: rate(v) for r, v in detection.items()},
        detection_merged=rate(merged),
        rerun={r: rate(v) for r, v in rerun.items()},
        kappa=review.cohen_kappa(
            [tuple("pass" if v == "pass" else "reject" for v in pair) for pair in all_pairs]
        ),
        kappa_real_three_class=review.cohen_kappa(pairs),
        kappa_all_three_class=review.cohen_kappa(all_pairs),
        observed_agreement=(
            sum((a == "pass") == (b == "pass") for a, b in all_pairs) / len(all_pairs)
            if all_pairs
            else None
        ),
        observed_agreement_real_three_class=(
            sum(a == b for a, b in pairs) / len(pairs) if pairs else None
        ),
    )
    if calibration_rows:
        values["calibration"] = review.calibration_metrics(calibration_rows)
    if prereg:
        # The pre-registered basis: reviewer agreement on the frozen, balanced labelled set.
        expected = sum(prereg["calibration"]["by_system"].get(system, {}).values())
        found = values.get("calibration") or dict(items=0, reviewed=0, kappa=None)
        values["kappa_all_samples_binary"] = values["kappa"]
        values["kappa"] = found["kappa"]
        complete &= (
            not departures
            and len(calibration_runs) == 1
            and found["items"] == expected
            and found["reviewed"] == expected
        )

    def met(value, threshold):
        return value is not None and value >= threshold

    gates = dict(
        complete=complete,
        detection_merged=met(values["detection_merged"], review.GATES["detection_merged"]),
        detection_single=all(
            met(v, review.GATES["detection_single"]) for v in values["detection"].values()
        ),
        rerun=all(met(v, review.GATES["rerun"]) for v in values["rerun"].values()),
        kappa=met(values["kappa"], review.GATES["kappa"]),
    )
    calibrated = all(gates.values())
    candidates = sorted(ref for ref, result in outcomes.items() if result["approved"])
    values["pass_rate"] = len(candidates) / len(entries) if batches else None
    gates["pass_rate"] = met(values["pass_rate"], review.GATES["pass_rate"])
    result = dict(
        system=system,
        entries=len(entries),
        candidate_count=len(candidates),
        draft_count=len(entries) - len(candidates),
        metrics=values,
        gates=gates,
        calibrated=calibrated,
        passed=all(gates.values()),
        samples=dict(
            detection=detection,
            detection_merged=merged,
            rerun=rerun,
            kappa_pairs=len(all_pairs),
            kappa_real_pairs=len(pairs),
            verdict_pairs=dict(Counter(f"{a}/{b}" for a, b in all_pairs)),
            verdict_pairs_real=dict(Counter(f"{a}/{b}" for a, b in pairs)),
        ),
        batches=batches,
        thresholds=review.GATES,
        acceptance_basis=prereg["acceptance_basis"] if prereg else LEGACY_BASIS,
        kappa_basis=prereg["kappa_basis"] if prereg else LEGACY_KAPPA,
        preregistered=bool(prereg),
        deviations=departures,
        calibration_runs=calibration_runs,
        human_reviewed_rate=0.0,
    )
    return result, outcomes, entries


def record(workspace, summary, outcomes, entries, report, root):
    system = summary["system"]
    records = {
        ref: row.model_dump()
        for ref, row in load_ledgers(workspace.reviews).items()
        if ref.startswith(f"kb:{system}:")
    }
    before = records.copy()
    reasons = {}

    def revoke(ref, reason):
        if ref in records and records[ref]["content_sha256"] == content_hash(entries[ref]):
            del records[ref]
            reasons[ref] = reason

    for ref, result in outcomes.items():
        if not result["approved"]:
            revoke(ref, "同哈希内容被否决")
            continue
        if not summary["calibrated"]:
            continue
        calls = review.RunDir(result["path"]).calls()
        reviewers = []
        for role in review.REVIEWERS:
            spec = result["manifest"]["reviewers"][role]
            returned = sorted(
                {
                    c["returned_model"]
                    for c in calls
                    if c["reviewer"] == role and c["returned_model"]
                }
            )
            reviewers.append(
                dict(
                    vendor=spec["vendor"],
                    model=spec["model"],
                    returned_model="、".join(returned) or None,
                    verdict="pass",
                )
            )
        records[ref] = approval(
            entries[ref],
            reviewers,
            min(c["started_at"] for c in calls)[:10],
            review.report_reference(report, root),
        )
        previous = before.get(ref)
        if records[ref] != previous:
            same = previous and previous["content_sha256"] == records[ref]["content_sha256"]
            reasons[ref] = "同一内容的批准记录更新" if same else "体系汇总批准"
    if not summary["calibrated"]:
        # An uncalibrated system keeps no approval of its current content, whichever
        # command wrote it: `model_review_kb ledger` accepts a single calibrated batch.
        for ref in sorted(records.keys() & entries.keys()):
            revoke(ref, "体系校准未达标")
    if before != records:
        report.parent.mkdir(parents=True, exist_ok=True)
        with (report.parent / "ledger-events.jsonl").open("a", encoding="utf-8") as stream:
            for ref in sorted(before.keys() | records.keys()):
                if before.get(ref) != records.get(ref):
                    stream.write(
                        json.dumps(
                            dict(
                                at=review.now(),
                                id=ref,
                                previous=before.get(ref),
                                current=records.get(ref),
                                reason=reasons[ref],
                                evidence=(
                                    outcomes[ref]["path"].as_posix() if ref in outcomes else None
                                ),
                            ),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
        write_ledger(workspace.reviews, system, list(records.values()))
    return dict(
        written=len([ref for ref in records if records[ref] != before.get(ref)]),
        revoked=sorted(before.keys() - records.keys()),
    )


def bind(run_root, output):
    """Close the per-batch ledger path for this run root; only this script approves it."""
    review.write_json(
        run_root / review.CAMPAIGN_MARKER,
        dict(
            acceptance="按体系汇总全部初审及复审批次（scripts.kb_review_campaign）",
            output=output.as_posix(),
            per_batch_ledger="拒绝：单个小批次校准达标不代表体系校准达标",
        ),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-ledger", action="store_true")
    args = parser.parse_args(argv)
    bind(args.run_root, args.output)
    paths = sorted(
        (p.parent for p in args.run_root.glob("*/manifest.json")),
        key=lambda p: (review.read_json(p / "manifest.json").get("created_at", ""), p.name),
    )
    workspace = review.Workspace()
    prereg_path = args.run_root / PREREGISTRATION
    prereg = review.read_json(prereg_path) if prereg_path.is_file() else None
    summaries = []
    for system in prereg["systems"] if prereg else SYSTEMS:
        summary, outcomes, entries = summarize(workspace, paths, system, prereg)
        target = args.output / system
        report = target / "report.md"
        target.mkdir(parents=True, exist_ok=True)
        summary["current_content_evidence"] = {
            ref: dict(
                content_sha256=content_hash(entries[ref]),
                approved=value["approved"],
                run=value["path"].as_posix(),
            )
            for ref, value in sorted(outcomes.items())
        }
        if args.write_ledger:
            summary["ledger_changes"] = record(
                workspace, summary, outcomes, entries, report, review.ROOT
            )
        ledger = load_ledgers(workspace.reviews)
        summary["model_reviewed_count"] = sum(
            ref in ledger and ledger[ref].content_sha256 == content_hash(entry)
            for ref, entry in entries.items()
        )
        summary["effective_draft_count"] = len(entries) - summary["model_reviewed_count"]
        summary["human_reviewed_rate"] = sum(e["reviewed"] for e in entries.values()) / len(entries)
        review.write_json(target / "summary.json", summary)
        report.write_text(
            f"# {system}：体系汇总验收\n\n"
            + summary["acceptance_basis"]
            + "。阈值不变，保留所有失败样本；不是人工审核。\n\n"
            + f"当前内容双审候选 {summary['candidate_count']}/{summary['entries']}；"
            + f"质量校准达标：{summary['calibrated']}；全部关口达标：{summary['passed']}。\n\n"
            + "完整分子分母、每批原始失败指标和当前内容的证据来源见 [summary.json](summary.json)。\n\n"
            + "```json\n"
            + json.dumps(summary["metrics"], ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        summaries.append(
            {
                k: summary[k]
                for k in (
                    "system",
                    "entries",
                    "candidate_count",
                    "draft_count",
                    "model_reviewed_count",
                    "effective_draft_count",
                    "metrics",
                    "gates",
                    "calibrated",
                    "passed",
                )
            }
        )
    review.write_json(args.output / "summary.json", dict(systems=summaries))
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
