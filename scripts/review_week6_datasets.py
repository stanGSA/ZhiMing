"""Week 6 dataset finalisation and structural review (not a human dictionary review).

name_strokes.yaml: records how the 19 needs_review characters are finalised in code (default
written form = the dataset answer; real alternative spellings ask the user to confirm).
dream_annotations.yaml: gold symbols, alternatives and out-of-vocabulary probes against the
dream knowledge partition, plus the items whose notes ask for gentle or non-predictive wording.
multiturn.yaml: the scripts week 5 deferred to week 6 now find every tool they need.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import yaml

from app import ROOT
from plugins.dream.match import DreamMatcher
from plugins.name.strokes import char_strokes
from scripts.review_week5_datasets import LATER_TOOLS, review_multiturn

POLICY = {
    "confirm": "默认写法即数据集答案；存在真实的另一种写法，工具返回默认值与备选笔画，并要求说明、请用户按证件确认",
    "fixed": "姓氏繁体惯例（不随通用简繁转换），没有需要用户选择的另一种写法，直接定稿",
}


def finalise_strokes() -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/name_strokes.yaml").read_text(encoding="utf-8"))
    rows, problems = [], []
    for item in data["items"]:
        if item["status"] != "needs_review":
            continue
        result = char_strokes(item["char"], item["role"])
        if result["strokes"] != item["expected_kangxi_strokes"]:
            problems.append(f"{item['char']}: 默认笔画与数据集答案不一致")
        policy = "confirm" if result["needs_confirmation"] else "fixed"
        rows.append(
            dict(
                id=item["id"],
                char=item["char"],
                role=item["role"],
                default=dict(form=result["form"], strokes=result["strokes"]),
                alternatives=[
                    dict(form=a["form"], strokes=a["strokes"]) for a in result["alternatives"]
                ],
                policy=policy,
                dataset_reasons=item.get("review_reasons", []),
            )
        )
    return dict(
        dataset="name_strokes",
        items=len(data["items"]),
        needs_review=len(rows),
        finalised=rows,
        policies=POLICY,
        status_note="定稿记录在plugins/name/strokes.py（SURNAME_FORMS、GIVEN_FORMS、ALTERNATIVES），数据集金标未改动；"
        "仍建议上线前对照康熙字典人工抽查。",
        problems=problems,
    )


def review_dreams(kb_path: Path) -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/dream_annotations.yaml").read_text(encoding="utf-8"))
    db = sqlite3.connect(kb_path.resolve().as_uri() + "?mode=ro", uri=True)
    matcher = DreamMatcher(db, "review")
    problems = []
    vocabulary = set(data["vocabulary_used"]["keys"])
    gold = {s for item in data["items"] for s in item["gold_symbols"]}
    if gold != vocabulary:
        problems.append("vocabulary_used 与金标意象集合不一致")
    missing = sorted(vocabulary - set(matcher.entries))
    if missing:
        problems.append(f"知识库缺少种子意象：{missing}")
    oov = sorted({o for item in data["items"] for o in item["out_of_vocabulary"]})
    in_kb = [o for o in oov if o in matcher.aliases]
    if in_kb:
        problems.append(f"词典外意象被收录为条目或同义词：{in_kb}")
    alternatives = sorted(
        {
            a
            for item in data["items"]
            for a in item.get("acceptable_alternative") or []
            if a not in matcher.entries
        }
    )
    db.close()
    sensitive = [
        dict(id=item["id"], note=item["note"])
        for item in data["items"]
        if item.get("note")
        and any(w in item["note"] for w in ("不得", "不能", "温和", "健康", "去世", "彩票"))
    ]
    return dict(
        dataset="dream_annotations",
        status=data["status"],
        items=len(data["items"]),
        gold_keys=len(gold),
        kb_symbols=len(matcher.entries),
        missing_seed_keys=missing,
        oov_terms=oov,
        # Labels used only in acceptable alternatives; they are not knowledge entries, so an
        # extractor can never produce them and those alternatives cannot be matched exactly.
        alternative_labels_outside_kb=alternatives,
        wording_constraints=sensitive,
        problems=problems,
    )


def review_deferred_multiturn() -> dict:
    result = review_multiturn()
    from app import create_runtime

    registered = set()
    for mode in ("single", "multi"):
        runtime = create_runtime(user_id="dataset-review", provider="demo", mode=mode)
        try:
            registered |= set(runtime.registry.tools)
            if mode == "multi":
                registered |= set(
                    runtime.registry.tools["consult_specialist"].handler.__self__.specs
                )
        finally:
            runtime.close()
    missing = {
        script: sorted(set(needs) - registered)
        for script, needs in result["deferred_to_week6"].items()
        if set(needs) - registered
    }
    return dict(
        dataset="multiturn",
        deferred_from_week5=result["deferred_to_week6"],
        tools_now_registered=sorted(LATER_TOOLS & registered),
        specialists_now_registered=sorted({"name", "dream"} & registered),
        still_missing=missing,
        problems=result["problems"] + [f"{k}: 仍缺工具 {v}" for k, v in missing.items()],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb", type=Path, default=ROOT / "data/kb.sqlite")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = [finalise_strokes(), review_dreams(args.kb), review_deferred_multiturn()]
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(1 if any(r["problems"] for r in result) else 0)


if __name__ == "__main__":
    main()
