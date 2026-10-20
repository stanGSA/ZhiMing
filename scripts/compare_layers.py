"""Fixed-question comparison of real-model replies between two code versions.

The same questions, synthetic birth data, consultation dates, tarot seed and calendar anchor
are replayed against any checkout, so an old and a new version can be compared turn by turn:

    git worktree add ../zm-old main
    python scripts/compare_layers.py run --root ../zm-old --data-from . --label old \
        --mode single --model <m>
    python scripts/compare_layers.py run --root .         --label new --mode single --model <m>
    python scripts/compare_layers.py run ... --mode multi          (both versions again)
    python scripts/compare_layers.py report reports/compare/old-single reports/compare/new-single

Run it as a file (not ``-m``) so the code under ``--root`` is the code that is imported. Each
run keeps every reply, structured output and trace under ``reports/compare/<label>-<mode>``.
The report adds length, layering, evidence share, rejection/resubmission, review and
recomputation figures; whether a reply explains "作用关系 → 挑战/机遇 → 应对" is left to the
human checklist it writes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ANCHOR = "2026-10-15"
SEED = 42
BIRTH = "合成资料：我是男性，2001年11月25日上午10点出生于中国北京市，按公历，不用真太阳时。"
BACKGROUND = "我在读研究生，正在做一个多智能体项目的开发，最近压力很大。"
CLARIFY = "合成资料：出生地是中国北京市，钟表为北京时间，公历，不用真太阳时，其余按默认口径。"

# 2001-11-25 10:00 Beijing gives 辛巳 己亥 壬辰 乙巳, the chart of the reference answer.
SCENARIOS = [
    dict(
        id="bazi-month",
        kind="八字时机+连续追问",
        turns=[
            BIRTH
            + BACKGROUND
            + "根据我的八字，看看这个月（2026年10月8日到11月6日）有什么值得关注的，会有好事还是坏事？",
            "具体怎么做：玄学层面怎么给自己补充一点“水”的能量？",
        ],
    ),
    dict(
        id="bazi-timing",
        kind="八字时机",
        turns=[BIRTH + "下个月（2026年11月1日到11月30日）适合换实习单位吗？用八字看。"],
    ),
    dict(
        id="astro-trait",
        kind="占星本命",
        turns=[BIRTH + "看看我的本命星盘，工作方式上有什么特点？"],
    ),
    dict(
        id="astro-timing",
        kind="占星行运",
        turns=[BIRTH + "2026年11月1日到11月30日的行运对我的项目进展有什么影响？用占星看。"],
    ),
    dict(
        id="tarot-three",
        kind="塔罗+追问",
        turns=["用三张塔罗看看我最近的工作状态。", "第二张牌具体什么意思？"],
    ),
    dict(
        id="tarot-decision",
        kind="二选一",
        turns=["A公司稳定但成长慢，B公司是创业团队但机会多，用二选一牌阵看看选A还是B？"],
    ),
    dict(
        id="combined-timing",
        kind="多体系时机",
        turns=[BIRTH + "结合八字和占星，看看下个月（2026年11月1日到11月30日）适合跳槽吗？"],
    ),
    dict(
        id="daily",
        kind="每日运势",
        turns=[BIRTH + "今天（2026年10月15日）运势怎么样？"],
    ),
]
RECOMPUTE = {
    "draw_tarot",
    "compute_bazi",
    "compute_bazi_period",
    "compute_natal_chart",
    "compute_transits",
    "consult_specialist",
    "daily_fortune",
    "analyze_name",
    "lookup_dream_symbols",
}


def load_code(root: Path):
    """Import the checkout under ``root`` (its app, plugins and knowledge build)."""
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv

    load_dotenv(root / ".env")  # credentials stay in the environment, never copied
    from app import create_runtime
    from knowledge.build import build

    return create_runtime, build


def share_data(root: Path, source: Path) -> None:
    """Give a scratch checkout the verified data files it lacks (ephemeris, places, Unihan)."""
    for name in ("ephe", "geo", "unihan"):
        target, origin = root / "data" / name, source / "data" / name
        if target.exists() or not origin.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(origin, target_is_directory=True)
        except OSError:  # Windows without symlink rights
            shutil.copytree(origin, target)


def workdir(
    root: Path, out: Path, build, provider, model, mode, orchestrator_thinking=None
) -> Path:
    import yaml

    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    config["mode"] = mode
    if provider:
        config["llm"]["provider"] = provider
    if model:
        config["llm"]["model"] = model
        config["models"] = dict.fromkeys(config.get("models") or {}, model)
    if orchestrator_thinking is not None:
        if config["llm"]["provider"] != "deepseek":
            raise ValueError("--orchestrator-thinking requires DeepSeek")
        options = config.setdefault("model_options", {}).setdefault("orchestrator", {})
        options["thinking"] = "enabled" if orchestrator_thinking == "low" else "disabled"
        options["reasoning_effort"] = "low" if orchestrator_thinking == "low" else None
    (work / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    shutil.copytree(root / "knowledge/sources", work / "sources")
    shutil.copytree(root / "knowledge/rules", work / "rules")
    build(work / "sources", work / "data/kb.sqlite", work / "rules")
    return work


def pin_calendar(runtime) -> None:
    runtime.session.calendar_anchor = ANCHOR
    for message in runtime.session.messages:
        if message["role"] == "system" and message["content"].startswith("本轮日历基准"):
            message["content"] = (
                f"本轮日历基准（Asia/Shanghai）：{ANCHOR}；按用户指定日期范围优先，不猜系统月份。"
            )


def records(runtime) -> list[dict]:
    directory = runtime.tracer.user_dir(runtime.session.user_id)
    rows = [
        json.loads(line)
        for path in (sorted(directory.glob("*.jsonl")) if directory.exists() else [])
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    own = runtime.session.id
    return sorted(
        (r for r in rows if own in (r["session_id"], r.get("parent_session_id"))),
        key=lambda r: r["timestamp"],
    )


def visible_chars(output: dict) -> dict:
    sections = output.get("sections") or []
    analysis = (
        len(output.get("summary", ""))
        + sum(len(s["title"]) + len(s["body"]) for s in sections)
        + sum(len(a) for a in output.get("advice", []))
        + len(output.get("closing", ""))
        + sum(len(t["period"]) + len(t["note"]) for t in output.get("timeline", []))
        + sum(
            len(t["how_to_read"]) + sum(len(s) for s in t["sides"])
            for t in output.get("tensions", [])
        )
    )
    evidence = sum(len(e["reading"]) for e in output.get("evidence", []))
    return dict(
        analysis_chars=analysis,
        evidence_chars=evidence,
        evidence_share=round(evidence / (analysis + evidence), 3) if analysis + evidence else None,
        sections=len(sections),
        section_titles=[s["title"] for s in sections],
        advice=len(output.get("advice", [])),
        closing=bool(output.get("closing")),
        evidence_items=len(output.get("evidence", [])),
    )


REJECTION_CATEGORIES = ("fact", "expression", "safety", "schema", "review", "disclosure", "other")


def rejection_category(result) -> str:
    """Keep reviewer retries and schema/policy errors out of factual-error counts.

    Legacy validators return prose rather than typed fact errors. Classify only known
    diagnostics; retain unrecognized failures as 'other' together with their original code.
    """
    code, message = result.get("code"), result.get("error") or ""
    if code == "review_revise":
        return "review"
    if code == "invalid_arguments":
        return "schema"
    if code != "validation_failed":
        return "other"
    if re.search(r"劝阻就医|安全说明|健康、投资|危机|停药", message):
        return "safety"
    if re.search(r"(?:专家|体系).*未完成.*(?:须|必须)说明|缺少.*体系.*原因", message):
        return "disclosure"
    if re.search(
        r"时间范围问题需要相应行运或流期计算|必须先调用确定性计算工具|systems_used", message
    ):
        return "fact"
    if re.search(
        r"确定性说法|免责声明|内部状态|审核|confidence.level|summary第一句|二选一", message
    ):
        return "expression"
    if re.search(
        r"相位|干支|柱位|落座|宫位|四轴|行运日期|容许度|牌面|未抽出的牌|ref_ids?|笔画|三才|格.*不符",
        message,
    ):
        return "fact"
    return "other"


def repository_metadata(root: Path) -> dict:
    """Archives and machines without Git can still run the comparison.

    Unknown dirtiness is null, never false: lack of metadata is not a clean checkout.
    """
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"], stderr=subprocess.DEVNULL
            )
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return dict(revision=None, dirty=None, revision_error=type(exc).__name__)
    return dict(revision=revision, dirty=dirty, revision_error=None)


def turn_row(scenario, index, question, outcome, events, runtime, latency) -> dict:
    own = runtime.session.id
    calls = [r for r in events if r["event"] == "tool_result"]
    submits = [r for r in calls if r["session_id"] == own and r["call"]["name"] == "submit_reading"]
    reports = [r for r in calls if r["call"]["name"] == "submit_report"]
    usage = [r for r in events if r["event"] == "model_response"]
    output = outcome.data.get("reading") or {}
    return dict(
        scenario=scenario["id"],
        kind=scenario["kind"],
        turn=index,
        question=question,
        status=outcome.status,
        latency_s=round(latency, 2),
        reply_chars=len(outcome.text),
        **visible_chars(output),
        submit_attempts=len(submits),
        submit_rejections=[r["result"].get("error") for r in submits if not r["result"]["ok"]],
        report_rejections=[r["result"].get("error") for r in reports if not r["result"]["ok"]],
        rejection_details=[
            dict(
                tool=r["call"]["name"],
                code=r["result"].get("code"),
                category=rejection_category(r["result"]),
                error=r["result"].get("error"),
            )
            for r in submits + reports
            if not r["result"]["ok"]
        ],
        reviews=[
            dict(verdict=r.get("verdict"), issues=r.get("issues"), notes=r.get("notes"))
            for r in events
            if r["event"] == "review_finished"
        ],
        warnings=outcome.data.get("warnings"),
        tools=[r["call"]["name"] for r in calls if r["session_id"] == own],
        recomputed=[r["call"]["name"] for r in calls if r["call"]["name"] in RECOMPUTE],
        model_calls=len(usage),
        input_tokens=sum(r.get("input_tokens") or 0 for r in usage),
        output_tokens=sum(r.get("output_tokens") or 0 for r in usage),
        reasoning_tokens=sum(r.get("reasoning_tokens") or 0 for r in usage),
        finish_reasons=[r.get("finish_reason") for r in usage],
        returned_models=sorted({r["returned_model"] for r in usage if r.get("returned_model")}),
        errors=[
            r["event"]
            for r in events
            if r["event"]
            in ("model_error", "limit_reached", "timeout", "output_truncated", "usage_unavailable")
        ],
        text=outcome.text,
        output=output,
    )


async def run(args) -> Path:
    root = Path(args.root).resolve()
    out = Path(args.out).resolve() / f"{args.label}-{args.mode}"
    out.mkdir(parents=True, exist_ok=True)
    if args.data_from:
        share_data(root, Path(args.data_from).resolve())
    create_runtime, build = load_code(root)
    work = workdir(
        root, out, build, args.provider, args.model, args.mode, args.orchestrator_thinking
    )
    metadata = repository_metadata(root)
    rows = []
    for scenario in SCENARIOS:
        runtime = create_runtime(root=work, user_id=f"compare-fixed-{scenario['id']}", seed=SEED)
        pin_calendar(runtime)
        try:
            for index, question in enumerate(scenario["turns"], 1):
                before = len(records(runtime))
                started = time.perf_counter()
                outcome = await runtime.turn(question)
                clarified = None
                if outcome.status == "ask_user":
                    # One fixed clarification keeps the run unattended; it is reported.
                    clarified = outcome.text
                    outcome = await runtime.turn(CLARIFY)
                row = turn_row(
                    scenario,
                    index,
                    question,
                    outcome,
                    records(runtime)[before:],
                    runtime,
                    time.perf_counter() - started,
                )
                row["clarified"] = clarified
                rows.append(row)
                name = f"{scenario['id']}-{index}"
                (out / "replies").mkdir(exist_ok=True)
                (out / "replies" / f"{name}.md").write_text(
                    f"# {name}（{scenario['kind']}）\n\n## 问题\n\n{question}\n\n"
                    + (f"## 追问（自动补答）\n\n{clarified}\n\n" if clarified else "")
                    + f"## 回复\n\n{outcome.text}\n\n## 结构化输出\n\n```json\n"
                    + json.dumps(row["output"], ensure_ascii=False, indent=2)
                    + "\n```\n",
                    encoding="utf-8",
                )
                (out / "results.json").write_text(
                    json.dumps(
                        dict(
                            label=args.label,
                            mode=args.mode,
                            provider=args.provider or getattr(runtime.model, "provider", None),
                            model=getattr(runtime.model, "model", args.model),
                            user_id_scheme="compare-fixed-{scenario}",
                            orchestrator_thinking=args.orchestrator_thinking,
                            anchor=ANCHOR,
                            seed=SEED,
                            **metadata,
                            rows=rows,
                        ),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(f"{name}: {row['status']} {row['reply_chars']}字", flush=True)
        finally:
            trace_dir = runtime.tracer.user_dir(runtime.session.user_id)
            if trace_dir.exists():
                shutil.copytree(trace_dir, out / "traces" / scenario["id"], dirs_exist_ok=True)
            try:
                await runtime.close_model()
            finally:
                runtime.close()
    return out


# Directness, read from saved rows so earlier results.json files can be re-reported: a first
# sentence opening on a condition, boundary notes explained to the user, a chart-basis layer.
HEDGE = re.compile(r"有条件|前提")
CAVEAT = re.compile(r"不能当作|不能当成|不能用来|不能据此|不能扩展|不代表|不意味着|并不表示")
BASIS = re.compile(r"基准|口径")
# Plain language: terms a reader without training cannot parse. Same list as
# common.validation.JARGON, copied so that old checkouts can still be reported.
JARGON = re.compile(
    r"七杀|偏官|正官|正财|偏财|正印|偏印|枭神|印星|财星|官星|食神|伤官|食伤|劫财|十神|"
    r"日主(?![题要持角动导])|喜用神?|用神|"
    r"(?<!自)[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]|"
    r"[子丑寅卯辰巳午未申酉戌亥]{2}相?[冲合刑害破]|"
    r"(?:对分|四分|三分|六分|刑|拱)相|第[一二三四五六七八九十\d]{1,2}宫"
)


def first_sentence(output: dict) -> str:
    return re.split(r"[。！？!?]", output.get("summary") or "")[0]


def lead_jargon(row: dict) -> int:
    """Terms in the verdict, layer titles, advice and closing that the user did not ask about."""
    output = row.get("output") or {}
    lead = [
        output.get("summary") or "",
        *(row.get("section_titles") or []),
        *(output.get("advice") or []),
        output.get("closing") or "",
    ]
    asked = row.get("question") or ""
    return sum(t not in asked for text in lead for t in JARGON.findall(text))


def summarize(rows) -> dict:
    done = [r for r in rows if r["status"] == "submit_reading"]
    count = len(done) or 1
    # Reclassify saved diagnostics with today's rules without rewriting historical
    # replies or their collection-time categories. Category-only legacy data stays usable.
    categories = [
        rejection_category(detail) if "code" in detail else detail.get("category", "other")
        for row in rows
        for detail in row.get("rejection_details", [])
    ]
    return dict(
        turns=len(rows),
        submitted=len(done),
        avg_reply_chars=round(sum(r["reply_chars"] for r in done) / count),
        avg_analysis_chars=round(sum(r["analysis_chars"] for r in done) / count),
        avg_evidence_share=round(sum(r["evidence_share"] or 0 for r in done) / count, 3),
        layered_turns=sum(r["sections"] >= 2 for r in done),
        hedged_first=sum(bool(HEDGE.search(first_sentence(r.get("output") or {}))) for r in done),
        avg_caveats=round(sum(len(CAVEAT.findall(r.get("text") or "")) for r in done) / count, 1),
        basis_sections=sum(
            any(BASIS.search(title) for title in r.get("section_titles") or []) for r in done
        ),
        avg_jargon=round(sum(len(JARGON.findall(r.get("text") or "")) for r in done) / count, 1),
        avg_lead_jargon=round(sum(lead_jargon(r) for r in done) / count, 1),
        rejections=sum(len(r["submit_rejections"]) + len(r["report_rejections"]) for r in rows),
        **{
            f"{category}_rejections": categories.count(category)
            for category in REJECTION_CATEGORIES
        },
        unclassified_legacy_rejections=sum(
            len(r["submit_rejections"]) + len(r["report_rejections"])
            for r in rows
            if "rejection_details" not in r
        ),
        resubmitted_turns=sum(r["submit_attempts"] > 1 for r in rows),
        review_revise=sum(any(v["verdict"] == "revise" for v in r["reviews"]) for r in rows),
        followup_recompute=sum(bool(r["recomputed"]) for r in rows if r["turn"] > 1),
        clarified=sum(bool(r.get("clarified")) for r in rows),
    )


CHECKLIST = (
    "- [ ] 先表态：第一句直接回答所问，前提放在第二句；再概括整体气象\n"
    "- [ ] 说白话：不懂命理也能看懂结论、小标题和建议；正文术语附白话解释，不讲推算方法\n"
    "- [ ] 正文不向用户逐条解释写作边界；没问到时不单独写排盘基准\n"
    "- [ ] 分层推演：每层讲清作用关系 → 挑战／机遇 → 应对，而不是把依据拆成几个标题\n"
    "- [ ] 行动建议具体可执行\n"
    "- [ ] 使用了用户明确提供的背景，未编造个人信息\n"
    "- [ ] 追问承接前文，未重抽、未重算（看 recomputed）\n"
    "- [ ] 事实与排盘一致；提到身体时有就医提醒；无“一定/必然”"
)


def report(paths) -> str:
    runs = [json.loads((Path(p) / "results.json").read_text(encoding="utf-8")) for p in paths]
    lines = ["# 新旧版本回复对照", ""]
    for r in runs:
        lines.append(
            f"- {r['label']}-{r['mode']}：provider={r.get('provider')}，model={r.get('model')}，"
            f"日历基准={r.get('anchor')}，seed={r.get('seed')}"
        )
        lines.append(
            f"  代码版本={r.get('revision') or '未知'}，dirty={r.get('dirty')}，"
            f"版本读取错误={r.get('revision_error') or '无记录'}"
        )
    lines.append("")
    lines.append("| 指标 | " + " | ".join(f"{r['label']}（{r['mode']}）" for r in runs) + " |")
    lines.append("|---|" + "---|" * len(runs))
    sums = [summarize(r["rows"]) for r in runs]
    for key in sums[0]:
        lines.append(f"| {key} | " + " | ".join(str(s[key]) for s in sums) + " |")
    lines += ["", "## 逐题", ""]
    lines.append(
        "| 题目 | 版本 | 状态 | 回复字数 | 正文字数 | 依据占比 | 层数 | 提交/拒绝 | 审校 | 警告 | 追问重算 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    keyed = [{(row["scenario"], row["turn"]): row for row in r["rows"]} for r in runs]
    for key in keyed[0]:
        for run_, rows in zip(runs, keyed, strict=True):
            row = rows.get(key)
            if row is None:
                continue
            lines.append(
                f"| {key[0]}-{key[1]} | {run_['label']}-{run_['mode']} | {row['status']} | {row['reply_chars']} | "
                f"{row['analysis_chars']} | {row['evidence_share']} | {row['sections']} | "
                f"{row['submit_attempts']}/{len(row['submit_rejections'])} | "
                f"{','.join(v['verdict'] or '-' for v in row['reviews']) or '-'} | "
                f"{len(row['warnings'] or [])} | {','.join(row['recomputed']) if key[1] > 1 else '-'} |"
            )
    lines += ["", "## 人工检查（每题对照完整回复 replies/*.md）", ""]
    for key in keyed[0]:
        lines += [f"### {key[0]}-{key[1]}", "", CHECKLIST, ""]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--root", default=".", help="要测试的代码检出目录")
    runner.add_argument("--label", required=True, help="如 old / new")
    runner.add_argument("--mode", choices=("single", "multi"), default="single")
    runner.add_argument("--provider", default=None, help="默认沿用config.yaml")
    runner.add_argument("--model", default=None, help="固定模型名；不填沿用该检出的config.yaml")
    runner.add_argument("--orchestrator-thinking", choices=("disabled", "low"), default=None)
    runner.add_argument("--out", default="reports/compare")
    runner.add_argument(
        "--data-from",
        default=None,
        help="从该检出共享已核验的data/ephe、geo、unihan（旧版本检出用）",
    )
    reporter = sub.add_parser("report")
    reporter.add_argument("paths", nargs="+")
    reporter.add_argument("--output", default=None)
    args = parser.parse_args()
    if args.command == "run":
        print(asyncio.run(run(args)))
    else:
        text = report(args.paths)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
