"""Dream output checks: no prophecy, no interpretation of unmatched or absent symbols."""

import re

from plugins.name.validation import text_of

PROPHECY = re.compile(r"预示|预兆|征兆|兆头|预言|将会发生|会发生|一定会|必定|必然会|注定")
NEGATION = re.compile(r"不|非|没有|无|并未|别")
UNMATCHED = re.compile(
    r"未收录|没有收录|未命中|无法解读|不作解读|不解读|没有依据|暂无|词典外|不在词典"
)
QUOTED = re.compile(r"[「“【《]([^」”】》]{1,8})[」”】》]")


def results(state):
    return [
        v for k, v in (state.get("calculations") or {}).items() if k.startswith("dream_result:")
    ]


def validate_output(reading, state, matcher):
    found = results(state)
    if not found:
        return None
    text = text_of(reading)
    for match in PROPHECY.finditer(text):
        if not NEGATION.search(text[max(0, match.start() - 6) : match.start()]):
            return "解梦只提供心理层面的线索，不能把梦境说成现实事件的预兆"
    hits = {h["key"] for r in found for h in r["hits"]}
    misses = {m for r in found for m in r["misses"]}
    for sentence in re.split(r"[。；;！!？?\n]", text):
        for miss in misses:
            if miss in sentence and not UNMATCHED.search(sentence):
                return f"意象“{miss}”未在词典中命中，只能说明未收录，不能解读"
        for term in QUOTED.findall(sentence):
            key = matcher.aliases.get(term)
            if key and key not in hits and not UNMATCHED.search(sentence):
                return f"“{term}”不是本次命中的意象，不能解读"
    return None
