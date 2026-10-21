"""Content checks that code can decide, run before any model review (plan 4.4 step 1).

Ranges, ids, keys and aliases are hard errors in ``knowledge.build``. The checks here are
findings: they go to the report and the revision queue, never fail the build, because a
reader must decide them (a reversed card may honestly stay negative, only less so).

Certainty words are judged the way replies are (common.output_policy), after removing the
project's own negated disclaimers such as “不代表事件必然发生” and “不表示现实事件必然发生”.
"""

from __future__ import annotations

import re

from common.output_policy import certainty_claim

# "不代表/不表示/并不意味着" + a short subject + 必然/一定/注定 + 发生: the disclaimer template.
DISCLAIMER = re.compile(
    r"(?:并不|并非|不)(?:代表|表示|意味着?|等于|预示|说明)"
    r"[^，,。；;！!？?\n]{0,8}?(?:必然|一定会?|注定)(?:会)?(?:发生|出现|如此|成立|消退)"
)


def certainty_finding(text: str) -> str | None:
    """The first certainty word that is not part of a negated disclaimer."""
    return certainty_claim([DISCLAIMER.sub("", text)])


def findings(entries: list[dict]) -> list[dict]:
    """One finding per (entry, check); ordered by entry id, then check."""
    found = []
    for entry in entries:
        word = certainty_finding(entry["text"])
        if word:
            found.append(dict(id=entry["id"], check="certainty", detail=f"确定性说法“{word}”"))
    cards = {e["key"]: e for e in entries if e["system"] == "tarot" and e["kind"] == "card"}
    for key, upright in sorted(cards.items()):
        if not key.endswith(":upright"):
            continue
        reversed_ = cards.get(key.removesuffix(":upright") + ":reversed")
        if reversed_ is None:
            continue
        for theme, value in sorted(upright["theme_map"].items()):
            opposite = reversed_["theme_map"].get(theme, 0)
            if value and opposite * value > 0:
                found.append(
                    dict(
                        id=upright["id"],
                        check="tarot_same_direction",
                        detail=f"{theme}：正位{value}，逆位{opposite}（{reversed_['id']}）",
                    )
                )
    return sorted(found, key=lambda f: (f["id"], f["check"], f["detail"]))


def summary(found: list[dict]) -> dict:
    by_check: dict[str, int] = {}
    for finding in found:
        by_check[finding["check"]] = by_check.get(finding["check"], 0) + 1
    return dict(count=len(found), by_check=dict(sorted(by_check.items())))
