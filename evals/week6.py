"""Week 6 gates: Kangxi strokes, same-day daily fortune, dream matching, knowledge coverage.

Everything here is deterministic and offline. The dream precision/recall uses the dictionary
scan baseline (no LLM) on dream_annotations.yaml; the plan's ≥0.85/≥0.8 target is for LLM
extraction and is reported, not claimed, by this suite.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app import ROOT, create_runtime
from evals.week23 import execute
from knowledge.build import build
from knowledge.kb import KnowledgeBase
from plugins.dream.match import DreamMatcher
from plugins.name.strokes import char_strokes
from plugins.name.wuge import analyze
from plugins.tarot.draw import draw_tarot

# Hand-checked five-grid examples (strokes from the Kangxi rule, formulas from wuge.py).
GRID_CASES = [
    ("张", "三", {"天格": 12, "人格": 14, "地格": 4, "外格": 2, "总格": 14}),
    ("王", "思远", {"天格": 5, "人格": 13, "地格": 26, "外格": 18, "总格": 30}),
    ("李", "一", {"天格": 8, "人格": 8, "地格": 2, "外格": 2, "总格": 8}),
    ("李", "逸", {"天格": 8, "人格": 22, "地格": 16, "外格": 2, "总格": 22}),
    ("欧阳", "子涵", {"天格": 32, "人格": 20, "地格": 15, "外格": 27, "总格": 47}),
    ("欧阳", "修", {"天格": 32, "人格": 27, "地格": 11, "外格": 16, "总格": 42}),
    ("赵", "一鸣", {"天格": 15, "人格": 15, "地格": 15, "外格": 15, "总格": 29}),
    # Compound surname 万俟 keeps 万 (3), unlike the single surname 万 → 萬 (15).
    ("万俟", "明", {"天格": 12, "人格": 17, "地格": 9, "外格": 4, "总格": 20}),
]
BIRTH = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 30.66,
    "lon": 104.07,
    "time_known": True,
}


def strokes_report() -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/name_strokes.yaml").read_text(encoding="utf-8"))
    rows = []
    for item in data["items"]:
        result = char_strokes(item["char"], item["role"])
        rows.append(
            dict(
                id=item["id"],
                char=item["char"],
                role=item["role"],
                expected=item["expected_kangxi_strokes"],
                actual=result["strokes"],
                form=result["form"],
                dataset_status=item["status"],
                needs_confirmation=result["needs_confirmation"],
                alternatives=[(a["form"], a["strokes"]) for a in result["alternatives"]],
                ok=result["strokes"] == item["expected_kangxi_strokes"]
                and result["form"] == item["traditional"],
            )
        )
    known = [i for i in data["items"] if "known_value" in i]
    review = [r for r in rows if r["dataset_status"] == "needs_review"]
    return dict(
        items=len(rows),
        correct=sum(r["ok"] for r in rows),
        known_surnames=len(known),
        known_correct=sum(
            char_strokes(i["char"], i["role"])["strokes"] == i["known_value"] for i in known
        ),
        review_items=len(review),
        review_confirm=[r["char"] for r in review if r["needs_confirmation"]],
        review_fixed=[r["char"] for r in review if not r["needs_confirmation"]],
        failures=[r for r in rows if not r["ok"]],
        review=review,
    )


def grids_report() -> dict:
    rows = []
    for surname, given, expected in GRID_CASES:
        actual = analyze(surname, given)["grids"]
        rows.append(dict(name=surname + given, expected=expected, actual=actual))
    return dict(cases=len(rows), correct=sum(r["expected"] == r["actual"] for r in rows), rows=rows)


def dream_report(kb: KnowledgeBase) -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/dream_annotations.yaml").read_text(encoding="utf-8"))
    matcher = DreamMatcher(kb.db, kb.version, kb.rules("dream")["match_threshold"])
    tp = fp = fn = exact = 0
    rows = []
    for item in data["items"]:
        predicted = set(matcher.scan(item["text"]))
        gold = set(item["gold_symbols"])
        alternative = item.get("acceptable_alternative")
        if alternative is not None and predicted == set(alternative):
            gold = set(alternative)
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
        exact += predicted == gold
        rows.append(dict(id=item["id"], predicted=sorted(predicted), gold=sorted(gold)))
    oov = sorted({o for item in data["items"] for o in item["out_of_vocabulary"]})
    unmatched = [o for o in oov if matcher.match(o)["key"] is None]
    # A mapping the item's own annotation lists as gold or acceptable is not a false hit.
    annotated = {
        o: set(item["gold_symbols"]) | set(item.get("acceptable_alternative") or [])
        for item in data["items"]
        for o in item["out_of_vocabulary"]
    }
    mapped = {o: matcher.match(o)["key"] for o in oov if o not in unmatched}
    handled = len(unmatched) + sum(key in annotated[o] for o, key in mapped.items())
    seeds = data["vocabulary_used"]["keys"]
    synonyms = data["vocabulary_used"]["synonym_examples"]
    return dict(
        method="离线词典扫描基线（非LLM抽取）：最长不重叠匹配知识库意象与同义词",
        items=len(rows),
        precision=tp / (tp + fp) if tp + fp else 1.0,
        recall=tp / (tp + fn) if tp + fn else 1.0,
        exact_match=exact,
        symbols=len(matcher.entries),
        seed_keys=len(seeds),
        seed_covered=sum(k in matcher.entries for k in seeds),
        synonym_examples=sum(len(v) for v in synonyms.values()),
        synonym_examples_hit=sum(
            matcher.match(s)["key"] == k for k, values in synonyms.items() for s in values
        ),
        oov_terms=len(oov),
        oov_unmatched=len(unmatched),
        oov_matched=mapped,
        oov_handled=handled,
        rows=rows,
    )


async def daily_report(workspace: Path, repeats: int = 10) -> dict:
    user = "week6-daily-" + uuid.uuid4().hex[:6]
    outputs = []
    reused = []
    for attempt in range(repeats):
        runtime = create_runtime(workspace, user_id=user, provider="demo", seed=attempt)
        try:
            if attempt == 0:
                for field, value in BIRTH.items():
                    runtime.session.profile = runtime.store.update_profile(
                        user, field, value, "合成评估资料"
                    )
            runtime.session.append_user("今天运势怎么样？")
            started = await execute(runtime, "start_reading", dict(question="今天运势怎么样？"))
            assert started.ok
            called = await execute(
                runtime, "daily_fortune", dict(date=runtime.session.calendar_anchor)
            )
            if not called.ok or called.data.get("status") == "needs_input":
                raise RuntimeError(f"daily_fortune failed: {called.error or called.data}")
            result = called.data
            reused.append(result["cache_reused"])
            outputs.append(
                json.dumps(
                    {k: v for k, v in result.items() if k != "cache_reused"},
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        finally:
            runtime.close()
    first = json.loads(outputs[0])
    plugin_seed = first["seed"]
    draws = {
        json.dumps(draw_tarot("single", f"daily:{first['date']}", plugin_seed)["cards"])
        for _ in range(100)
    }
    return dict(
        date=first["date"],
        repeats=repeats,
        identical=len(set(outputs)) == 1,
        distinct_outputs=len(set(outputs)),
        cache_reused=reused,
        card=first["card"]["name"],
        day_pillar=first["day"]["pillar"],
        events=len(first["events"]),
        seed_repeats=100,
        seed_identical=len(draws) == 1,
    )


async def evaluate(output: Path) -> dict:
    target = output / ("week6-" + uuid.uuid4().hex[:8])
    workspace = target / "workspace"
    workspace.mkdir(parents=True)
    shutil.copyfile(ROOT / "config.yaml", workspace / "config.yaml")
    coverage = build(
        ROOT / "knowledge/sources", workspace / "data/kb.sqlite", ROOT / "knowledge/rules"
    )
    kb = KnowledgeBase(workspace / "data/kb.sqlite")
    try:
        dream = dream_report(kb)
    finally:
        kb.close()
    strokes = strokes_report()
    grids = grids_report()
    daily = await daily_report(workspace)
    partitions = coverage["partitions"]
    gates = {
        "strokes_all_correct": dict(
            met=strokes["correct"] == strokes["items"],
            value=f"{strokes['correct']}/{strokes['items']}",
            target="200/200（计划关口：笔画全对）",
        ),
        "daily_same_day_unchanged": dict(
            met=daily["identical"] and daily["seed_identical"],
            value=f"{daily['repeats']}次调用{daily['distinct_outputs']}种结果；同seed抽牌100次一致="
            + str(daily["seed_identical"]),
            target="100%一致（计划关口：同日结果不变）",
        ),
        "kb_coverage": dict(
            met=all(partitions[s]["coverage"] == 1 for s in ("name", "dream", "daily")),
            value={s: partitions[s]["entries"] for s in ("name", "dream", "daily")},
            target="姓名、解梦、每日运势分区覆盖率100%，解梦意象≥300",
        ),
        "dream_seed_vocabulary": dict(
            met=dream["seed_covered"] == dream["seed_keys"]
            and dream["oov_handled"] == dream["oov_terms"],
            value=f"种子意象{dream['seed_covered']}/{dream['seed_keys']}，"
            f"词典外意象未命中{dream['oov_unmatched']}/{dream['oov_terms']}，"
            f"其余映射{dream['oov_matched']}均为该条标注认可的意象",
            target="89个种子意象全部收录；词典外意象未命中，或映射到该条标注认可的意象",
        ),
    }
    report = dict(
        generated_at=datetime.now(UTC).isoformat(),
        suite="week6",
        scope="离线确定性验收：笔画、五格公式、每日运势缓存与种子、解梦词典与匹配基线。不代表真实模型的意象抽取、工具选择或解读质量。",
        coverage=coverage,
        strokes=strokes,
        grids=grids,
        dream=dream,
        daily=daily,
        gates=gates,
        reviewed_rate={s: partitions[s]["reviewed_rate"] for s in ("name", "dream", "daily")},
    )
    (target / "week6-eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 第六周离线验收",
        "",
        report["scope"],
        "",
        "| 关口 | 结果 | 目标 | 是否达到 |",
        "|---|---|---|---|",
        *[
            f"| {name} | {gate['value']} | {gate['target']} | {'是' if gate['met'] else '否'} |"
            for name, gate in gates.items()
        ],
        "",
        f"- 37个公认姓氏笔画：{strokes['known_correct']}/{strokes['known_surnames']}",
        f"- 19个待定稿字：需要确认写法 {len(strokes['review_confirm'])} 个（"
        + "、".join(strokes["review_confirm"])
        + f"）；按姓氏惯例直接定稿 {len(strokes['review_fixed'])} 个（"
        + "、".join(strokes["review_fixed"])
        + "）",
        f"- 五格公式手算样例：{grids['correct']}/{grids['cases']}",
        f"- 解梦离线扫描基线：precision {dream['precision']:.3f}，recall {dream['recall']:.3f}，"
        f"完全一致 {dream['exact_match']}/{dream['items']}（不是LLM抽取，不作为0.85/0.8关口结果）",
        f"- 同义词示例命中：{dream['synonym_examples_hit']}/{dream['synonym_examples']}",
        f"- 每日运势：{daily['date']}，流日{daily['day_pillar']}，每日一牌{daily['card']}，"
        f"当日精确相位{daily['events']}个；缓存复用 {sum(daily['cache_reused'])}/{daily['repeats'] - 1}",
        f"- 人工审核率：{report['reviewed_rate']}",
    ]
    (target / "week6-eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["output_dir"] = str(target)
    return report
