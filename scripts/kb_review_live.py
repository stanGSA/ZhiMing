"""Run a pre-registered knowledge review campaign end to end, on the owner's machine.

    python -m scripts.kb_review_live pilot  --run-root <活动目录> --calibration <校准集> --iteration 1
    python -m scripts.kb_review_live preregister --run-root <活动目录> --calibration <校准集>
    python -m scripts.kb_review_live run    --run-root <活动目录> [--systems tarot ...]
    python -m scripts.kb_review_live status --run-root <活动目录>
    python -m scripts.kb_review_live accept --run-root <活动目录>

``pilot`` reviews only the calibration set's dev partition (no real entry), so the rubric can be
checked and revised before the full spend; its pre-specified gates are ``PILOT_GATES``, with at
most ``PILOT_MAX`` iterations before the owner decides on other reviewers. ``preregister``
fixes, before any acceptance call, the rubric hash, reviewers, knowledge base, the frozen
holdout partition, plan settings, thresholds, the kappa basis and the pilot evidence, and
closes the per-batch ledger path. ``run``
then works system by system: one initial run of every entry (with planted copies and the
calibration items) → merge → the reviser proposes fixes for the queue → proposals that change
something are applied → only those entries are re-reviewed in a new run, for at most the
registered number of rounds. Passed content is never sent again and unchanged content is
never re-reviewed; every run directory stays, failures included. Each step resumes where it
stopped: finished calls, proposals and applied edits are never repeated. ``accept`` is the
system-level acceptance (scripts.kb_review_campaign --write-ledger) plus a knowledge build.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from knowledge.build import build
from knowledge.review import content_hash
from scripts import kb_review_calibration as calibration_set
from scripts import kb_review_campaign as campaign
from scripts import model_review_kb as review
from scripts.kb_review_budget import BudgetModel, ReviewBudget
from scripts.kb_review_rubric import RUBRIC_VERSION

ROUNDS = 3
EDITABLE = ("text", "theme_map", "synonyms", "keywords")
PLAN = dict(batch_size=10, plant_rate=0.1, min_planted=5, passes=2)
# Fixed before any pilot: both reviewers agree on the dev set, each is stable on a second
# look, and each agrees with the frozen labels. Thresholds match the acceptance gates where
# those exist; label agreement is a pilot-only bar.
PILOT_GATES = dict(kappa=0.6, rerun=0.9, label_agreement=0.85)
PILOT_MAX = 3  # the first pilot plus at most two rubric revisions


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def relative(path: Path) -> str:
    path = path.resolve()
    root = review.ROOT.resolve()
    return (path.relative_to(root) if path.is_relative_to(root) else path).as_posix()


def preregister(
    run_root: Path,
    calibration: Path,
    config: dict,
    roles: dict,
    *,
    seed: int = 1,
    rounds: int = ROUNDS,
    systems=campaign.SYSTEMS,
    decisions: list[dict] | None = None,
    workspace=None,
    pilot_override: str | None = None,
) -> dict:
    """Write preregistration.json before any acceptance call; it can never be rewritten.

    The latest pilot must have run under today's rubric and met every gate, unless the owner
    gives ``pilot_override`` (a reason, recorded verbatim)."""
    workspace = workspace or review.Workspace()
    target = run_root / campaign.PREREGISTRATION
    if target.exists():
        raise ValueError(f"{relative(target)} 已登记，不能改写；新的口径须使用新的活动目录")
    if any(run_root.glob("*/manifest.json")):
        raise ValueError("活动目录已有审核批次，不能事后登记")
    data, lock = calibration_set.frozen(calibration)
    holdout = lock["by_partition"]["holdout"]
    missing = [s for s in systems if not holdout.get(s)]
    if missing:
        raise ValueError(f"校准集保留部分缺少体系：{'、'.join(missing)}")
    pilots = pilot_record(run_root)
    latest = pilots[-1] if pilots else None
    ready = bool(
        latest
        and latest["met"]
        and latest["rubric_sha256"] == review.rubric_digest()
        and latest.get("calibration_sha256") == lock["sha256"]
        and latest.get("reviewers")
        == {name: review.public_spec(roles[name]) for name in review.REVIEWERS}
        and set(systems) <= set(latest.get("systems", []))
    )
    if not ready and not (pilot_override or "").strip():
        raise ValueError(
            "最近一次试跑未在当前规则下通过（或尚未试跑）；请先试跑，或由负责人写明 --pilot-override 理由"
        )
    review.check_roles(roles, config, (*review.REVIEWERS, "reviser"))
    review.require_endpoints(roles, (*review.REVIEWERS, "reviser"))
    kb_review = config.get("kb_review") or {}
    record = dict(
        schema=1,
        campaign=run_root.name,
        registered_at=now(),
        git=review.git_state(review.ROOT),
        systems=list(systems),
        rubric_version=RUBRIC_VERSION,
        rubric_sha256=review.rubric_digest(),
        reviewers={name: review.public_spec(roles[name]) for name in review.REVIEWERS},
        reviser=review.public_spec(roles["reviser"]),
        exceptions=dict(
            runtime_vendor=kb_review.get("runtime_vendor_exception"),
            reviser_vendor=kb_review.get("reviser_vendor_exception"),
        ),
        passes=PLAN["passes"],
        plan=dict(PLAN, seed=seed, rereview_rounds=rounds),
        calibration=dict(
            path=relative(calibration),
            lock_sha256=lock["sha256"],
            partition="holdout",
            holdout_sha256=lock["partition_sha256"]["holdout"],
            by_system=holdout,
            confirmed_by=lock["confirmed_by"],
            confirmed_at=lock["confirmed_at"],
            review_kind=lock.get("review_kind", "human"),
            confirmation_statement=lock.get("statement"),
        ),
        knowledge_base=dict(
            kb_version=review.kb_version(workspace.sources, workspace.rules, workspace.reviews),
            source_files={s: review.source_digests(workspace, s) for s in systems},
        ),
        pilots=pilots,
        pilot_gates=PILOT_GATES,
        pilot_override=(pilot_override or "").strip() or None,
        thresholds=review.GATES,
        acceptance_basis=(
            "运行前登记：按体系汇总本活动全部初审及复审批次；通过率按当前内容哈希的最后一份完整"
            "双模型两轮结论；埋错检出只计机械埋错；重跑一致率计全部盲审条目；kappa在已冻结的平衡"
            "标注校准集上计算；阈值不变；体系未达标时撤销该体系当前内容的全部批准"
        ),
        kappa_basis=dict(
            scope="每个体系初审中混入的已冻结标注校准集保留部分（约一半合格、一半各含一处真实缺陷），"
            "第一轮；开发部分只用于试跑和完善规则，不进入验收",
            classes={"pass": "放行", "revise": "不通过", "reject": "不通过"},
            reason="真实条目九成以上判通过时kappa失真（2026-10-21占星两家同时标出0条）；"
            "平衡且有标签的校准集使kappa衡量两家能否一致地分辨缺陷",
            label_agreement="各家与标签的一致率、缺陷检出率、合格放行率只作报告，不作关口",
        ),
        budget=dict(
            state_path=relative(run_root / "budget.json"),
            unlimited=bool((kb_review.get("budget") or {}).get("unlimited")),
        ),
        supersedes=(
            "20261021-live 活动保留为失败记录，不删除、不重置；本活动按上述口径独立验收，"
            "其结论取代该活动写入的账本批准"
        ),
        owner_decisions=decisions or [],
    )
    review.write_json(target, record)
    campaign.bind(run_root, run_root / "campaign")
    return record


def budget_config(config: dict, run_root: Path) -> dict:
    """The campaign's own persistent budget ledger, whatever config.yaml points to."""
    kb_review = dict(config.get("kb_review") or {})
    kb_review["budget"] = dict(
        kb_review.get("budget") or {}, state_path=relative(run_root / "budget.json")
    )
    return dict(config, kb_review=kb_review)


def paid_models(config: dict, run_root: Path, timeout: float):
    budget = ReviewBudget(budget_config(config, run_root), review.ROOT)

    def make_model(role, spec):
        return BudgetModel(
            None, role, spec, budget, make_model=lambda: review.role_model(spec, timeout)
        )

    return make_model


# ---- pilot on the dev partition -----------------------------------------------------------


def pilot_plan(workspace, config, system: str, calibration: Path, *, seed: int) -> dict:
    """Only the dev items of one system, blind and batched like an ordinary run: by kind, at
    most ``batch_size`` per batch, never two copies of one entry together."""
    found = review.calibration_for(calibration, system, "dev")
    items = found["items"]
    rng = random.Random(seed)
    batches = []
    for kind in sorted({i["entry"]["kind"] for i in items}):
        members = [i for i in items if i["entry"]["kind"] == kind]
        rng.shuffle(members)
        groups: list[list[dict]] = []
        for item in members:
            room = [
                g
                for g in groups
                if len(g) < PLAN["batch_size"] and all(o["original"] != item["original"] for o in g)
            ]
            if room:
                room[0].append(item)
            else:
                groups.append([item])
        batches += [dict(kind=kind, refs=[i["ref"] for i in g]) for g in groups]
    batches = [
        dict(
            batch=f"b{n:03d}",
            kind=b["kind"],
            items=[dict(item=f"i{k:02d}", ref=r) for k, r in enumerate(b["refs"], 1)],
        )
        for n, b in enumerate(batches, 1)
    ]
    by_id = {e["id"]: e for e in review.load_entries(workspace.sources, system)}
    contents = {i["ref"]: i["entry"] for i in items}
    prompts = {b["batch"]: review.batch_messages(system, b, contents, by_id) for b in batches}
    roles = review.load_roles(config)
    manifest = dict(
        schema=review.SCHEMA,
        kind="pilot",
        system=system,
        seed=seed,
        batch_size=PLAN["batch_size"],
        passes=PLAN["passes"],
        rubric_version=RUBRIC_VERSION,
        rubric_sha256=review.rubric_digest(),
        script_sha256=review.sha256_bytes(Path(review.__file__).read_bytes()),
        reviewers={n: review.public_spec(roles[n]) for n in review.REVIEWERS},
        calibration=dict(lock_sha256=found["lock"]["sha256"], items=len(items), partition="dev"),
        batch_count=len(batches),
        prompt_sha256={
            k: review.sha256_bytes(review.canonical(v).encode()) for k, v in prompts.items()
        },
    )
    return dict(
        manifest=manifest,
        entries=[],
        planted=[],
        calibration=items,
        batches=batches,
        prompts=prompts,
        checks=[],
    )


def summarize_pilot(run: review.RunDir, plan: dict) -> dict:
    """Agreement on the dev items, each reviewer's stability and agreement with the labels,
    and every item the reviewers or the labels disagree on (what the rubric must settle)."""
    verdicts = review.collect(run, plan)
    first = {r: verdicts.get((r, 1), {}) for r in review.REVIEWERS}
    second = {r: verdicts.get((r, 2), {}) for r in review.REVIEWERS}
    items = plan["calibration"]
    rows = [
        dict(
            label=i["label"],
            **{r: first[r].get(i["ref"], {}).get("verdict") for r in review.REVIEWERS},
        )
        for i in items
    ]
    agreement = review.calibration_metrics(rows)
    rerun = {
        r: review.ratio(
            sum(first[r][i["ref"]]["verdict"] == second[r][i["ref"]]["verdict"] for i in items if i["ref"] in first[r] and i["ref"] in second[r]),
            sum(i["ref"] in first[r] and i["ref"] in second[r] for i in items),
        )
        for r in review.REVIEWERS
    }  # fmt: skip
    disputed = []
    for item in items:
        seen = {
            f"{r}.p{n}": table.get(item["ref"])
            for r in review.REVIEWERS
            for n, table in ((1, first[r]), (2, second[r]))
        }
        calls = {k: v["verdict"] for k, v in seen.items() if v}
        flagged = {k: v != "pass" for k, v in calls.items()}
        if len(set(flagged.values())) > 1 or any(
            f != (item["label"] == "fail") for f in flagged.values()
        ):
            disputed.append(
                dict(
                    id=item["id"],
                    label=item["label"],
                    verdicts=calls,
                    reasons={k: v["reason"] for k, v in seen.items() if v},
                    issues={k: v["issues"] for k, v in seen.items() if v and v["issues"]},
                )
            )  # fmt: skip
    gates = dict(
        complete=agreement["reviewed"] == agreement["items"]
        and all(sum(i["ref"] in second[r] for i in items) == len(items) for r in review.REVIEWERS),
        kappa=(agreement["kappa"] or 0) >= PILOT_GATES["kappa"],
        rerun=all((v or 0) >= PILOT_GATES["rerun"] for v in rerun.values()),
        label_agreement=all(
            (a["accuracy"] or 0) >= PILOT_GATES["label_agreement"]
            for a in agreement["label_agreement"].values()
        ),
    )
    return dict(
        system=plan["manifest"]["system"],
        rubric_sha256=plan["manifest"]["rubric_sha256"],
        agreement=agreement,
        rerun=rerun,
        gates=gates,
        met=all(gates.values()),
        thresholds=PILOT_GATES,
        disputed=disputed,
        usage=review.usage_summary(run, {}),
    )


async def run_pilot(
    run_root: Path,
    iteration: int,
    calibration: Path,
    *,
    workspace,
    config: dict,
    roles: dict,
    make_model,
    systems=campaign.SYSTEMS,
    concurrency: int = 2,
    timeout: float = 120,
) -> dict:
    if not 1 <= iteration <= PILOT_MAX:
        raise ValueError(f"试跑最多 {PILOT_MAX} 轮；仍不达标时请负责人决定是否更换审核模型")
    root = run_root / f"pilot-{iteration}"
    _, calibration_lock = calibration_set.frozen(calibration)
    results = {}
    for system in systems:
        path = root / system
        if (path / "manifest.json").is_file():
            plan = review.load_plan(path)
            if plan["manifest"]["rubric_sha256"] != review.rubric_digest():
                raise ValueError(
                    f"{relative(path)} 是在另一版规则下试跑的；调整规则后请用新的 --iteration"
                )
            if plan["manifest"]["calibration"]["lock_sha256"] != calibration_lock["sha256"]:
                raise ValueError(f"{relative(path)} 使用另一版校准集；请用新的 --iteration")
            run = review.RunDir(path)
            if plan["manifest"]["reviewers"] != {
                name: review.public_spec(roles[name]) for name in review.REVIEWERS
            }:
                raise ValueError(
                    "试跑审核角色与 manifest 不符；变更审核方参数须使用新的 --iteration"
                )
        else:
            plan = pilot_plan(workspace, config, system, calibration, seed=iteration)
            run = review.open_run(
                path, plan, dict(created_at=now(), git=review.git_state(review.ROOT))
            )
        result = await review.execute(
            run, plan, roles, make_model=make_model, timeout=timeout, concurrency=concurrency
        )
        if result["failed"]:
            results[system] = dict(status="service_errors", failed=result["failed"])
            continue
        summary = summarize_pilot(run, plan)
        review.write_json(path / "pilot-summary.json", summary)
        results[system] = {k: summary[k] for k in ("met", "gates", "rerun")} | dict(
            kappa=summary["agreement"]["kappa"],
            label_agreement=summary["agreement"]["label_agreement"],
            disputed=len(summary["disputed"]),
        )
    overall = dict(
        iteration=iteration,
        rubric_sha256=review.rubric_digest(),
        calibration_sha256=calibration_lock["sha256"],
        systems=results,
        met=len(results) == len(systems) and all(r.get("met") for r in results.values()),
    )
    if all("met" in r for r in results.values()):
        review.write_json(root / "summary.json", overall)
    return overall


def pilot_record(run_root: Path) -> list[dict]:
    """Every finished pilot, in order: what the preregistration cites."""
    found = []
    for path in sorted(run_root.glob("pilot-*/summary.json"), key=lambda p: int(p.parent.name[6:])):
        summary = review.read_json(path)
        identities = [
            review.read_json(path.parent / system / "manifest.json")["reviewers"]
            for system in summary["systems"]
            if (path.parent / system / "manifest.json").is_file()
        ]
        reviewers = (
            identities[0]
            if identities
            and len(identities) == len(summary["systems"])
            and all(identity == identities[0] for identity in identities)
            else None
        )
        found.append(
            dict(
                dir=relative(path.parent),
                iteration=summary["iteration"],
                rubric_sha256=summary["rubric_sha256"],
                calibration_sha256=summary.get("calibration_sha256"),
                systems=list(summary["systems"]),
                met=summary["met"],
                reviewers=reviewers,
                summary_sha256=review.sha256_bytes(path.read_bytes()),
            )
        )
    return found


# ---- the acceptance campaign ---------------------------------------------------------------


def stage(path: Path, make_plan, workspace) -> tuple[review.RunDir, dict]:
    """An existing run resumes from its own stored plan; a new one is planned now."""
    if (path / "manifest.json").is_file():
        return review.RunDir(path), review.load_plan(path)
    plan = make_plan()
    facts = dict(
        created_at=now(),
        git=review.git_state(review.ROOT),
        kb_version=review.kb_version(workspace.sources, workspace.rules, workspace.reviews),
    )
    return review.open_run(path, plan, facts), plan


def apply_pending(workspace, run: review.RunDir, plan: dict) -> list[str]:
    """Ids whose reviewed content a valid proposal changed, applying those not yet applied.

    A proposal identical to the reviewed content changes nothing: the entry stays a draft and
    is not re-reviewed (resending unchanged content would only dilute the failure).
    """
    record = run.path / "applied.json"
    if record.is_file():
        # Later rounds may have revised these entries again; what this run applied is fixed.
        return review.read_json(record)["ids"]
    path = run.path / "revisions.json"
    proposals = [p for p in (review.read_json(path) if path.is_file() else []) if not p["invalid"]]
    system = plan["manifest"]["system"]
    current = {e["id"]: e for e in review.load_entries(workspace.sources, system)}
    reviewed = {e["id"]: e for e in plan["entries"]}
    todo, done = [], []
    for proposal in proposals:
        before = reviewed[proposal["id"]]
        if all(before[k] == proposal["proposal"][k] for k in EDITABLE):
            continue
        after = dict(before, **proposal["proposal"], version=before["version"] + 1)
        state = content_hash(current[proposal["id"]])
        if state == content_hash(after):
            done.append(proposal["id"])
        elif state == proposal["before_sha256"]:
            todo.append(proposal["id"])
        else:
            raise ValueError(f"{proposal['id']} 在修改建议之后被另行修改，请人工核对")
    if todo:
        review.apply_revisions(workspace, run, todo)
    applied = sorted(todo + done)
    review.write_json(record, dict(at=now(), ids=applied))
    return applied


async def run_system(
    run_root: Path,
    system: str,
    prereg: dict,
    *,
    workspace,
    config: dict,
    roles: dict,
    make_model,
    concurrency: int = 2,
    revise_concurrency: int = 2,
    timeout: float = 120,
) -> dict:
    options = dict(
        batch_size=prereg["plan"]["batch_size"],
        plant_rate=prereg["plan"]["plant_rate"],
        min_planted=prereg["plan"]["min_planted"],
        passes=prereg["passes"],
    )
    seed = prereg["plan"]["seed"]
    calibration = review.ROOT / prereg["calibration"]["path"]
    steps = []

    def initial_plan():
        return review.prepare(
            workspace,
            config,
            system,
            seed=seed,
            calibration=review.calibration_for(calibration, system),
            **options,
        )

    path = run_root / f"{system}-initial"
    make_plan = initial_plan
    for number in range(prereg["plan"]["rereview_rounds"] + 1):
        run, plan = stage(path, make_plan, workspace)
        if campaign.deviations(plan["manifest"], prereg, system):
            raise ValueError(
                f"{relative(path)} 与预先登记不符：{campaign.deviations(plan['manifest'], prereg, system)}"
            )
        result = await review.execute(
            run, plan, roles, make_model=make_model, timeout=timeout, concurrency=concurrency
        )
        steps.append(
            dict(run=relative(path), **{k: result[k] for k in ("completed", "cached", "expected")})
        )
        if result["failed"]:
            return dict(
                system=system, status="service_errors", failed=result["failed"], steps=steps
            )
        summary = review.merge(run, plan, roles)
        steps[-1].update(approved=summary["approved"], queued=summary["queued"])
        if not summary["queued"] or number == prereg["plan"]["rereview_rounds"]:
            break
        await review.revise(
            run,
            plan,
            roles,
            make_model=make_model,
            timeout=timeout,
            vendor_exception=(config.get("kb_review") or {}).get("reviser_vendor_exception"),
            concurrency=revise_concurrency,
        )
        changed = apply_pending(workspace, run, plan)
        steps[-1].update(revised=len(changed))
        if not changed:
            break
        path = run_root / f"{system}-rereview-{number + 1}"

        def make_plan(ids=changed, round_seed=seed + number + 1):
            return review.prepare(
                workspace, config, system, seed=round_seed, only_ids=ids, **options
            )

    return dict(system=system, status="done", steps=steps)


def status(run_root: Path) -> list[dict]:
    rows = []
    for manifest in sorted(run_root.glob("*/manifest.json")):
        path = manifest.parent
        plan = review.load_plan(path)
        expected = len(plan["batches"]) * len(review.REVIEWERS) * plan["manifest"]["passes"]
        merged = path / "merged.json"
        rows.append(
            dict(
                run=path.name,
                calls=f"{len(review.RunDir(path).calls())}/{expected}",
                errors=len(review.RunDir(path).errors()),
                queued=review.read_json(merged)["queued"] if merged.is_file() else None,
                applied=len(review.read_json(path / "applied.json")["ids"])
                if (path / "applied.json").is_file()
                else None,
            )
        )
    return rows


def accept(run_root: Path) -> dict:
    campaign.main(
        ["--run-root", str(run_root), "--output", str(run_root / "campaign"), "--write-ledger"]
    )
    workspace = review.Workspace()
    report = build(
        workspace.sources, review.ROOT / "data/kb.sqlite", workspace.rules, workspace.reviews
    )
    coverage = review.ROOT / "data/kb.coverage.json"
    (run_root / "coverage.json").write_bytes(coverage.read_bytes())
    return dict(kb_version=report["kb_version"], review_status=report.get("review_status"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pilot", "preregister", "run", "status", "accept"):
        command = commands.add_parser(name)
        command.add_argument("--run-root", type=Path, required=True)
        if name in ("pilot", "preregister"):
            command.add_argument("--calibration", type=Path, required=True)
        if name == "pilot":
            command.add_argument("--iteration", type=int, required=True)
        if name == "preregister":
            command.add_argument("--seed", type=int, default=1)
            command.add_argument("--rounds", type=int, default=ROUNDS)
            command.add_argument("--decisions", type=Path, help="负责人决定记录（JSON列表）")
            command.add_argument("--pilot-override", help="试跑未达标仍登记时，负责人写明的理由")
        if name in ("pilot", "run"):
            command.add_argument("--systems", nargs="*")
            command.add_argument("--concurrency", type=int, default=2)
            command.add_argument("--revise-concurrency", type=int, default=2)
    args = parser.parse_args(argv)
    load_dotenv(review.ROOT / ".env")
    config = review.load_config(review.ROOT)
    roles = review.load_roles(config)
    timeout = float((config.get("kb_review") or {}).get("timeout_s", 120))
    if args.command == "pilot":
        review.check_roles(roles, config, review.REVIEWERS)
        review.require_endpoints(roles, review.REVIEWERS)
        output = asyncio.run(
            run_pilot(
                args.run_root,
                args.iteration,
                args.calibration,
                workspace=review.Workspace(),
                config=config,
                roles=roles,
                make_model=paid_models(config, args.run_root, timeout),
                systems=args.systems or campaign.SYSTEMS,
                concurrency=args.concurrency,
                timeout=timeout,
            )
        )
    elif args.command == "preregister":
        decisions = json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions else []
        output = preregister(
            args.run_root,
            args.calibration,
            config,
            roles,
            seed=args.seed,
            rounds=args.rounds,
            decisions=decisions,
            pilot_override=args.pilot_override,
        )
    elif args.command == "run":
        prereg_path = args.run_root / campaign.PREREGISTRATION
        if not prereg_path.is_file():
            raise ValueError("请先运行 preregister；未登记的活动不能开始审核")
        prereg = review.read_json(prereg_path)
        review.check_roles(roles, config, (*review.REVIEWERS, "reviser"))
        review.require_endpoints(roles, (*review.REVIEWERS, "reviser"))
        make_model = paid_models(config, args.run_root, timeout)
        output = []
        for system in args.systems or prereg["systems"]:
            result = asyncio.run(
                run_system(
                    args.run_root,
                    system,
                    prereg,
                    workspace=review.Workspace(),
                    config=config,
                    roles=roles,
                    make_model=make_model,
                    concurrency=args.concurrency,
                    revise_concurrency=args.revise_concurrency,
                    timeout=timeout,
                )
            )
            output.append(result)
            print(json.dumps(result, ensure_ascii=False))
            if result["status"] != "done":
                print("有调用失败：稍后用同一命令续跑，已完成的调用不会重复。")
                break
    elif args.command == "status":
        output = status(args.run_root)
    else:
        output = accept(args.run_root)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    main()
