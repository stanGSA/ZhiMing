"""Dream matching before and after the stage 1 review: removed aliases and the scan baseline.

The same (current) matcher runs on an earlier knowledge edition and on the current one, so
the effect of the reviewed synonym edits is measured rather than assumed. Offline and
deterministic; the earlier edition is read from data/kb_versions like any saved reading.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from app import ROOT
from evals.week6 import dream_report
from knowledge.kb import KnowledgeBase
from plugins.dream.match import BARE_FRAGMENTS, DISTINCT_HEADS, DreamMatcher

CHANGES = ROOT / "docs/verification/kb-model-review/20261021-live/content-changes.json"
SCAN_FIELDS = ("items", "precision", "recall", "exact_match", "synonym_examples_hit")


def removed_aliases(changes: list[dict]) -> list[tuple[str, str]]:
    return [
        (alias, change["before"]["key"])
        for change in changes
        if change["before"]["system"] == "dream" and change["before"]["kind"] == "symbol"
        for alias in sorted(set(change["before"]["synonyms"]) - set(change["after"]["synonyms"]))
    ]


def matcher(kb: KnowledgeBase) -> DreamMatcher:
    return DreamMatcher(kb.db, kb.version, kb.rules("dream")["match_threshold"])


def compare(old: KnowledgeBase, new: KnowledgeBase, changes: list[dict]) -> dict:
    before, after = matcher(old), matcher(new)
    rows = []
    for alias, key in removed_aliases(changes):
        now = after.match(alias)
        outcome = "same" if now["key"] == key else "unmatched" if now["key"] is None else "other"
        rows.append(
            dict(
                alias=alias,
                old_key=before.match(alias)["key"],
                reviewed_key=key,
                now=now["key"],
                method=now["method"],
                outcome=outcome,
            )
        )
    old_scan, new_scan = dream_report(old), dream_report(new)
    return dict(
        method="同一份当前匹配代码分别作用于旧版与当前知识库；离线词典扫描基线，非LLM抽取",
        old_version=old.version,
        current_version=new.version,
        removed_aliases=dict(
            total=len(rows), outcomes=dict(Counter(r["outcome"] for r in rows)), rows=rows
        ),
        scan_baseline=dict(
            old={k: old_scan[k] for k in SCAN_FIELDS},
            current={k: new_scan[k] for k in SCAN_FIELDS},
            synonym_examples=new_scan["synonym_examples"],
            changed_items=[
                dict(id=o["id"], gold=o["gold"], old=o["predicted"], current=n["predicted"])
                for o, n in zip(old_scan["rows"], new_scan["rows"], strict=True)
                if o["predicted"] != n["predicted"]
            ],
        ),
        unmatched_by_design=dict(
            distinct_heads=list(DISTINCT_HEADS), fragments=sorted(BARE_FRAGMENTS)
        ),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-version", required=True)
    parser.add_argument("--changes", type=Path, default=CHANGES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    changes = json.loads(args.changes.read_text(encoding="utf-8"))
    new = KnowledgeBase(ROOT / "data/kb.sqlite")
    old = KnowledgeBase(ROOT / "data/kb.sqlite", version=args.old_version)
    try:
        report = compare(old, new, changes)
    finally:
        old.close()
        new.close()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "removed_aliases"},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(json.dumps(report["removed_aliases"]["outcomes"], ensure_ascii=False))


if __name__ == "__main__":
    main()
