"""Dream output checks over every user-visible field.

A symbol may be interpreted only when this reading's lookup matched it. Whether the symbol is
quoted does not matter: any knowledge-base alias used as the subject of an interpretation
(梦见X, X象征/代表/意味…, 「X」) must belong to a hit, unless the sentence says the symbol is
not in the dictionary. Unmatched words may only be reported as unmatched, dreams are never
prophecies, and a dream-only reading has no event timeline.
"""

import re

from common.facts import public_texts

PROPHECY = re.compile(r"预示|预兆|征兆|兆头|预言|将会发生|会发生|一定会|必定|必然会|注定")
NEGATION = re.compile(r"不|非|没有|无|并未|别")
UNMATCHED = re.compile(
    r"未收录|没有收录|未命中|无法解读|不作解读|不解读|没有依据|暂无|词典外|不在词典"
)
QUOTED = re.compile(r"[「“【《]([^」”】》]{1,8})[」”】》]")
INTERPRETS = re.compile(
    r"\s*(?:的?意象|这个意象|这一意象|的梦|这个梦)?\s*(?:常常|往往|通常|多半|多)?\s*"
    r"(?:象征|代表|意味|寓意|暗示|预示|说明|反映|提示|对应|是在|与.{0,8}有关|常与|多与)"
)
DREAMED = re.compile(
    r"梦(?:见|到|里|中)(?:了|的)?(?:自己在|我在|在)?"
    r"(?:一[只条个头匹片棵把部座位群张]|很多|好多|许多)?(?:很|特别)?(?:大|小)?$"
)


def results(state):
    return [
        v for k, v in (state.get("calculations") or {}).items() if k.startswith("dream_result:")
    ]


def interpreted(sentence, matcher):
    """Knowledge keys the sentence interprets, found by longest alias match."""
    keys = set()
    for start, end, _, key in matcher.spans(sentence):
        if INTERPRETS.match(sentence, end) or DREAMED.search(sentence[:start]):
            keys.add(key)
    for term in QUOTED.findall(sentence):
        key = matcher.aliases.get(term) or matcher.match(term)["key"]
        if key:
            keys.add(key)
    return keys


def validate_output(reading, state, matcher):
    found = results(state)
    if not found:
        return None
    texts = public_texts(reading)
    if reading.systems_used == ["dream"] and reading.timeline:
        return "解梦只提供心理层面的线索，不安排事件时间表；请删去timeline"
    hits = {h["key"] for r in found for h in r["hits"]}
    misses = {m for r in found for m in r["misses"]}
    for text in texts:
        for match in PROPHECY.finditer(text):
            if not NEGATION.search(text[max(0, match.start() - 6) : match.start()]):
                return "解梦只提供心理层面的线索，不能把梦境说成现实事件的预兆"
        for sentence in re.split(r"[。；;！!？?\n]", text):
            if UNMATCHED.search(sentence):
                continue
            for miss in misses:
                if miss in sentence:
                    return f"意象“{miss}”未在词典中命中，只能说明未收录，不能解读"
            extra = interpreted(sentence, matcher) - hits
            if extra:
                return f"“{'、'.join(sorted(extra))}”不是本次命中的意象，不能解读"
    return None
