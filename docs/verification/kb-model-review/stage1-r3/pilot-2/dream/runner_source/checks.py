"""Content checks that code can decide, run before any model review (plan 4.4 step 1).

Ranges, ids, keys and aliases are hard errors in ``knowledge.build``. The checks here are
findings: they go to the report and the revision queue, never fail the build, because a
reader must decide them (a reversed card may honestly stay negative, only less so).

Certainty words and restricted negated disclaimers use the same policy as replies
(common.output_policy).
"""

from __future__ import annotations

from common.output_policy import certainty_claim


def certainty_finding(text: str) -> str | None:
    """The first certainty word that is not part of a negated disclaimer."""
    return certainty_claim([text])


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
