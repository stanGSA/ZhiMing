"""Dream output checks over every user-visible field.

A symbol may be interpreted only when this reading's lookup matched it. Whether the symbol is
quoted does not matter: any knowledge-base alias used as the subject of an interpretation
(梦见X, X象征/代表/意味…, 「X」) must belong to a hit, unless that particular mention is
explicitly excluded. An abstention never exempts another symbol in the same sentence.
Unmatched words may only be reported as unmatched, dreams are never
prophecies, and a dream-only reading has no event timeline.
"""

import re

from common.facts import public_texts

PROPHECY = re.compile(r"预示|预兆|征兆|兆头|预言|将会发生|会发生|一定会|必定|必然会|注定")
NEGATION = re.compile(r"不|非|没有|无|并未|别")
# A denial after the prophecy word in the same clause: 现实中会发生什么并不由梦决定.
# Kept specific, since 梦预示你会发生不好的事 still predicts an event.
DENIED_AFTER = re.compile(
    r"并不由|不由梦|不取决于|与梦(?:境)?无关|并非由梦|不是(?:由)?梦(?:境)?(?:能|可以|来)?决定|"
    r"梦(?:境)?(?:并)?(?:不能|无法)(?:预测|决定)"
)
UNMATCHED = re.compile(
    r"未收录|没有收录|未命中|无法解读|不作解读|不解读|没有依据|暂无|词典外|不在词典"
)
QUOTED = re.compile(r"[「“【《]([^」”】》]{1,8})[」”】》]")
INTERPRETS = re.compile(
    r"\s*(?:(?:的|这个|这一)?(?:意象|形象|出现|场景|含义)|的梦|这个梦)?\s*"
    r"(?:常常|往往|通常|多半|多|可能|也许|似乎)?\s*"
    r"(?:象征|代表|意味|寓意|暗示|预示|说明|反映|提示|对应|是在|与.{0,8}有关|常与|多与)"
)
CLAUSES = re.compile(r"[。；;！!？?\n，,]|但是|可是|不过|然而|但")
ABSENT = re.compile(r"不在.{0,6}(?:描述|梦境)|不是本次.{0,4}意象|未(?:梦见|梦到)|没有(?:梦见|梦到)")
DREAMED = re.compile(
    r"梦(?:见|到|里|中)(?:了|的)?(?:自己在|我在|在)?"
    r"(?:一[只条个头匹片棵把部座位群张]|很多|好多|许多)?(?:很|特别)?(?:大|小)?$"
)


def results(state):
    return [
        v for k, v in (state.get("calculations") or {}).items() if k.startswith("dream_result:")
    ]


def excluded_mention(clause, start, end, boundary):
    """Scope an abstention to its object, stopping before the next mentioned symbol."""
    tail = clause[end:boundary]
    prefix = clause[:start]
    exclusion = UNMATCHED.search(tail) or ABSENT.search(tail)
    # '蛇象征变化所以不作解读' still contains an affirmative interpretation.
    if exclusion and not INTERPRETS.search(tail[: exclusion.start()]):
        return True
    return bool(
        re.search(r"(?:未收录|未命中|不解读|不作解读)(?:的)?\s*[「“【《]?$", prefix)
        or re.search(r"(?:没有|并未|未)(?:梦见|梦到)\s*[「“【《]?$", prefix)
    )


def ungrounded(clause, matcher, hits, misses):
    """Return a bad mention, preserving its ownership when clauses contain many objects."""
    mentions = [(a, b, alias, key) for a, b, alias, key in matcher.spans(clause)]
    for quote in QUOTED.finditer(clause):
        term = quote.group(1)
        key = matcher.aliases.get(term) or matcher.match(term)["key"]
        if key:
            start, end = quote.span(1)
            mentions = [m for m in mentions if not (start <= m[0] < end)]
            mentions.append((start, end, term, key))
    for miss in misses:
        for match in re.finditer(re.escape(miss), clause):
            # An OOV phrase is one object; aliases inside it do not split its abstention.
            mentions = [m for m in mentions if not (match.start() <= m[0] < match.end())]
            mentions.append((match.start(), match.end(), miss, None))
    mentions.sort(key=lambda item: item[0])
    for index, (start, end, alias, key) in enumerate(mentions):
        boundary = mentions[index + 1][0] if index + 1 < len(mentions) else len(clause)
        if excluded_mention(clause, start, end, boundary):
            continue
        if key is None:
            return f"意象“{alias}”未在词典中命中，只能说明未收录，不能解读"
        if key not in hits:
            quoted = (
                start > 0
                and clause[start - 1] in "「“【《"
                and end < len(clause)
                and clause[end] in "」”】》"
            )
            if quoted or INTERPRETS.match(clause, end) or DREAMED.search(clause[:start]):
                return f"“{key}”不是本次命中的意象，不能解读"
    return None


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
            after = CLAUSES.split(text[match.end() :], maxsplit=1)[0]
            if not NEGATION.search(
                text[max(0, match.start() - 6) : match.start()]
            ) and not DENIED_AFTER.search(after):
                return "解梦只提供心理层面的线索，不能把梦境说成现实事件的预兆"
        for clause in CLAUSES.split(text):
            error = ungrounded(clause, matcher, hits, misses)
            if error:
                return error
    return None
