"""Replay two r3 refusals offline against the exact run's fact sheet and KB."""

import json
import sqlite3
from pathlib import Path

from plugins.dream.match import DreamMatcher
from plugins.dream.validation import phrase_aliases, text_error

root = Path.cwd()
path = next((root / "reports/p2-r3/Dream-pipeline").glob("*/live.json"))
report = json.loads(path.read_text(encoding="utf8"))
connection = sqlite3.connect(
    (path.parent / "workspace/data/kb.sqlite").resolve().as_uri() + "?mode=ro", uri=True
)
matcher = DreamMatcher(connection, "r3-offline-replay")
examples = [
    (
        "dream_late_grandmother",
        0,
        "如果你最近确实有些累，不妨给自己留一点像“回家吃饭”那样的松弛时刻，比如好好做一顿饭、早点休息，或回一趟让你安心的地方。",
        "条件式建议，无梦境解读",
    ),
    (
        "dream_late_grandmother",
        0,
        "如果你近期忙得顾不上吃饭休息，可以从小事上补回来：按时吃一顿热饭、给自己煮点爱吃的东西，都是很实在的照顾。",
        "另一条候选原句；实际未触发",
    ),
    (
        "dream_teeth_falling",
        2,
        "你梦见牙齿一颗一颗掉下来。",
        "仅复述原题中已规范化为掉牙的完整原话",
    ),
]
results = []
for case, repeat, text, explanation in examples:
    row = next(r for r in report["results"] if r["id"] == case and r["repeat"] == repeat)
    facts = next(v for k, v in row["calculated_facts"].items() if k.startswith("dream_result:"))
    actual = text_error(
        text,
        matcher,
        {h["key"] for h in facts["hits"]},
        set(facts["misses"]),
        aliases=phrase_aliases(matcher, facts["hits"]),
    )
    results.append(
        dict(
            answer=f"{case}#{repeat + 1}",
            text=text,
            explanation=explanation,
            hits=facts["hits"],
            actual_error=actual,
        )
    )
connection.close()
output = root / "reports/p2-r3/false-rejection-replay.json"
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8")
print(json.dumps(results, ensure_ascii=False, indent=2))
