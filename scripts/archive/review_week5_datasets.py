"""Structural review of the two week 5 draft datasets (not a human review).

reviewer_drafts.yaml: class counts, expected verdicts, tension and safety context per class.
multiturn.yaml: profiles exist, referenced specialists/tools exist, which scripts the current
weeks can run, and expectations the runtime does not implement yet.
"""

import argparse
import json
from collections import Counter

import yaml

from app import ROOT

AVAILABLE_SPECIALISTS = {"astro", "bazi", "tarot"}
LATER = {"dream", "name", "daily"}
TOOLS = {
    "compute_natal_chart",
    "compute_transits",
    "compute_bazi",
    "compute_bazi_period",
    "draw_tarot",
    "lookup_meaning",
    "update_profile",
    "analyze_name",
    "lookup_dream_symbols",
    "daily_fortune",
}
LATER_TOOLS = {"analyze_name", "lookup_dream_symbols", "daily_fortune"}


def review_drafts() -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/reviewer_drafts.yaml").read_text(encoding="utf-8"))
    items = data["items"]
    problems = []
    counts = Counter(item["class"] for item in items)
    if dict(counts) != data["counts"]:
        problems.append(f"类别计数 {dict(counts)} 与 counts {data['counts']} 不一致")
    if len({item["id"] for item in items}) != len(items):
        problems.append("id 重复")
    for item in items:
        cls, expected, context = item["class"], item["expected"]["verdict"], item["context"]
        if cls != "acceptable" and expected != "revise":
            problems.append(f"{item['id']}: 坏草稿的期望结论应为 revise")
        if cls == "acceptable" and expected == "revise":
            problems.append(f"{item['id']}: 可接受草稿不应期望 revise")
        if cls == "hidden_tension" and not context.get("tensions"):
            problems.append(f"{item['id']}: 隐瞒张力类缺少 tensions")
        if cls == "safety" and not context.get("safety_relevant"):
            problems.append(f"{item['id']}: 安全类应标 safety_relevant")
        if context.get("tensions") and "runtime_producible" not in context:
            problems.append(f"{item['id']}: 有张力的草稿须标注 runtime_producible")
        for tension in context.get("tensions") or []:
            systems = [side.split(":", 1)[0] for side in tension["sides"]]
            if len(tension["sides"]) != 2 or not set(systems) <= AVAILABLE_SPECIALISTS:
                problems.append(f"{item['id']}: 张力两边须是两个已接入体系")
    themes = sorted({t["theme"] for item in items for t in item["context"].get("tensions") or []})
    placeholders = [item["id"] for item in items if item["draft"].get("body", "").startswith("（")]
    return dict(
        dataset="reviewer_drafts",
        status=data["status"],
        items=len(items),
        counts=dict(counts),
        expected_verdicts=dict(Counter(i["expected"]["verdict"] for i in items)),
        tension_themes=themes,
        safety_relevant_acceptable=[
            i["id"]
            for i in items
            if i["class"] == "acceptable" and i["context"].get("safety_relevant")
        ],
        placeholder_bodies=placeholders,
        # Tension samples the runtime merge can produce (same-horizon astro/bazi) versus
        # cross-horizon tarot samples that only test the reviewer's reading of the text.
        tension_samples=dict(
            runtime_producible=[
                i["id"] for i in items if i["context"].get("runtime_producible") is True
            ],
            reviewer_text_only=[
                i["id"] for i in items if i["context"].get("runtime_producible") is False
            ],
        ),
        problems=problems,
    )


def review_multiturn() -> dict:
    data = yaml.safe_load((ROOT / "evals/cases/multiturn.yaml").read_text(encoding="utf-8"))
    profiles = yaml.safe_load((ROOT / "evals/cases/profiles.yaml").read_text(encoding="utf-8"))
    problems, runnable, deferred = [], [], {}
    for script in data["scripts"]:
        if script["initial_profile"] not in profiles["profiles"]:
            problems.append(f"{script['id']}: 画像 {script['initial_profile']} 不存在")
        needs = set()
        for session in script["sessions"]:
            for turn in session["turns"]:
                expect = turn.get("expect", {})
                specialists = set(expect.get("specialists", []))
                tools = {
                    t
                    for key in ("tools_required", "tools_allowed", "tools_forbidden")
                    for t in expect.get(key, [])
                }
                unknown = (specialists - AVAILABLE_SPECIALISTS - LATER) | (tools - TOOLS)
                if unknown:
                    problems.append(f"{script['id']}: 未知专家或工具 {sorted(unknown)}")
                needs |= (specialists & LATER) | (
                    set(expect.get("tools_required", [])) & LATER_TOOLS
                )
                if expect.get("reading") == "same" and specialists:
                    problems.append(f"{script['id']}: 复用同一记录却要求咨询专家")
        if needs:
            deferred[script["id"]] = sorted(needs)
        else:
            runnable.append(script["id"])
    return dict(
        dataset="multiturn",
        status=data["status"],
        scripts=len(data["scripts"]),
        runnable_now=runnable,
        deferred_to_week6=deferred,
        problems=problems,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    result = [review_drafts(), review_multiturn()]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if any(r["problems"] for r in result) else 0)


if __name__ == "__main__":
    main()
