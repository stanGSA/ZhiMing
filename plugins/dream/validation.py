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
from common.output_policy import clause_before, denial_negated, negates_claim
from plugins.dream.match import NORMALISATIONS

# Only entity-free constructions can authorise alternative output phrases. A lookup
# rule such as 被追 also names different pursuers, which must remain independently grounded.
OUTPUT_NORMALISATIONS = {
    "掉牙": NORMALISATIONS["掉牙"],
    # 找不到路 is already an alias of 迷路; the same construction with 出口/出路/方向, none of
    # them a dictionary entity, is that symbol too (r5 dream_lost_in_mall).
    "迷路": re.compile(
        r"(?:到处|四处|一直)?(?:找|寻)不(?:到|着)(?:出口|出路|方向|路)"
        r"|(?:出口|出路)(?:很|太|总|也|都)?(?:难找|找不到)"
    ),
}

PROPHECY = re.compile(r"预示|预兆|征兆|兆头|预言|将会发生|会发生|一定会|必定|必然会|注定")
# A prophecy word is cancelled only by a negation that governs it (output_policy.negates_claim),
# never by a stray negative character in front of it: 这不是坏事，它预示…, 不是坏事而是预示…,
# 这是不幸的预兆, 这无疑预示…, 别人… and 不久会发生… all still assert one (r6 review).
# As a noun, 预兆 is also cancelled by what denies or dismisses it: 不是健康的预兆, 没有什么预兆,
# 不作为现实预兆, 别把梦当成预兆, 不必担心预兆. Comparisons need a safe continuation too.
# A modifier between the denial and the noun is one short word, never 一般/普通 (不是一般的预兆
# says the opposite), and a contrast (而是, 但 …) starts a new assertion.
DENIED_OMEN = re.compile(
    r"(?:"
    r"(?:不是|并不是|并非|绝非|而非|并无|毫无|没有|并没有|无关|不算|不属于|不等于|不作为|不作|"
    r"不谈|(?:不能|不应|不要|不必|别)(?:当作|当成|作为|说成|写成|看成|视为))"
    r"(?:什么|任何|一种|一个)?"
    r"|(?:不必|不用|不要|别|无需|无须|用不着|没必要)(?:去|再|太|过于|总)?"
    r"(?:担心|害怕|纠结|在意|琢磨|当成|当作|看成|看作|视为)(?:什么|任何|这是|它是)?"
    r"|(?<!不)(?<!非)(?<!不是)(?<!没有)(?<!不得)(?<!不能)(?<!不可)(?<!不可以)"
    r"(?:不|并不|不能|不可|不可以|不应|不应该|不应当|不必|不用|不要|别|不是|并不是|并非)"
    r"(?:把|将)(?:梦|梦境|这个梦|这场梦|它)"
    r"(?:当成|当作|看成|看作|视为|理解为|理解成|想成)(?:什么|任何)?"
    r"|(?<!不)(?<!非)(?<!不是)(?<!没有)(?<!不得)(?<!不能)(?<!不可)(?<!不可以)"
    r"(?:不|并不|不能|不可|不可以|不应|不应该|不应当|不必|不要)被"
    r"(?:当成|当作|看成|看作|视为|理解为|理解成|想成)(?:什么|任何)?"
    r")"
    # The modifier is no second negation either: 不是不作预兆解读 affirms (PR #53 review), while the
    # whole adjectives 不幸/不祥/不好/不利/不吉 only qualify the omen (r12 review: 不是不幸的预兆).
    r"(?:(?:不幸|不祥|不好|不利|不吉|(?![不没非无别]|一般|普通)[\u4e00-\u9fff]){1,2}的?)?$"
)
OMEN = re.compile(r"预兆|征兆|兆头|预言")
OMEN_COMPARISON = re.compile(
    r"(比|与其)(?:去|总|总是|反复|一直)?(?:担心|害怕|纠结|琢磨|猜测|在意)"
    r"(?:它|这)?(?:是不是|是否|会不会)?(?:什么|所谓的)?$"
)
# These are complete continuations, not prefixes: 等着它成真 and 相信它会带来好运
# must not inherit the exemption from 比担心/与其担心. Keep the known r6 wording and
# concrete self-care alternatives; other comparisons can be rewritten during repair.
SAFE_OMEN_COMPARISON = {
    "比": re.compile(r"更(?:有用|重要|能照顾自己)"),
    "与其": re.compile(
        r"[，,]?\s*不如(?:先)?(?:好好)?(?:休息|照顾自己|照顾好自己|关注当下|放松一下)"
    ),
}
UNMATCHED = re.compile(
    r"未收录|没有收录|未命中|无法解读|不作解读|不解读|没有依据|暂无|词典外|不在词典"
)
QUOTED = re.compile(r"[「“【《]([^」”】》]{1,8})[」”】》]")
# An adverb between a symbol and its verb (猫都象征…, 被追和猫也代表…) does not hide it (r6 review).
INTERPRETS = re.compile(
    r"\s*(?:(?:的|这个|这一)?(?:意象|形象|出现|场景|含义)|的梦|这个梦)?\s*"
    r"(?:都|也|还|则|就|均|同样|一起|共同|其实)?\s*"
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


def phrase_aliases(matcher, hits):
    """Exact suffix aliases in a matched source phrase, bound to that hit's key.

    奶奶 in 去世的奶奶 may name the matched 去世的亲人. This does not authorise
    the other aliases of 祖父母 (爷爷, 外公, …), or add another dictionary fact.
    """
    aliases = {}
    for hit in hits:
        phrase = hit.get("phrase") or ""
        for start, end, _, key in matcher.spans(phrase):
            if key != hit["key"] or end != len(phrase):
                continue
            # The suffix must belong to a literal alias of this hit, not just occur
            # somewhere in its source phrase (蛇和猫 does not make 猫 an alias of 蛇).
            aliases.update(
                (alias, key)
                for alias in matcher.aliases
                if alias != phrase and len(alias) <= end - start and phrase.endswith(alias)
            )
    return aliases


# The dreamer's own running in a chase (被人追着一直跑) is the matched 被追, so the dictionary's
# word for that running, 奔跑, names the hit rather than 跑步 (r6 dream_chased_to_exam#2).
# Only when the user's own clause runs from the chase, joined by at most an adverb: a run told
# elsewhere (被狗追，后来去操场跑步) stays 跑步, and 跑步 itself is never bound to the chase.
CHASE_RUN = re.compile(
    NORMALISATIONS["被追"].pattern
    + r"(?:着|得)?(?:一直|一路|拼命|使劲|不停地?|到处|四处|赶紧|飞快地?)?(?:地)?(?:往前)?(?:跑|奔跑)"
)
CHASE_RUN_ALIASES = ("奔跑",)


def chase_aliases(hits, question):
    """奔跑 → 被追 when 被追 is a hit and the user's clause runs from that chase."""
    keys = {hit["key"] for hit in hits}
    if "被追" not in keys or "跑步" in keys or not CHASE_RUN.search(question or ""):
        return {}
    return dict.fromkeys(CHASE_RUN_ALIASES, "被追")


def hit_aliases(matcher, hits, question):
    """Every pipeline-only alias of a hit: suffixes of its phrase, and the chase's running."""
    return {**phrase_aliases(matcher, hits), **chase_aliases(hits, question)}


def phrase_hits(hits, matcher=None):
    """Bind only controlled normalisation spans, preserving other objects in a source phrase.

    A source phrase that is, as a whole, one alias of another symbol is the hit itself:
    去世的奶奶 matched 祖父母 (r9 dream_late_grandmother#1), so retelling those words does not
    name 去世的亲人. Only that exact phrase is bound; the other symbol's other aliases
    (去世的亲人, 去世的爷爷) stay unmatched, and a phrase of several objects binds nothing.
    """
    phrases = {}
    for hit in hits:
        phrase = hit.get("phrase") or ""
        rule = NORMALISATIONS.get(hit["key"])
        if rule:
            phrases.update((match[0], hit["key"]) for match in rule.finditer(phrase))
        if matcher is not None and phrase:
            spans = matcher.spans(phrase)
            if len(spans) == 1 and spans[0][:2] == (0, len(phrase)) and spans[0][3] != hit["key"]:
                phrases.setdefault(phrase, hit["key"])
    return phrases


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


def ungrounded(clause, matcher, hits, misses, *, aliases=None, phrases=None):
    """Return a bad mention, preserving its ownership when clauses contain many objects."""
    mentions = [(a, b, alias, key) for a, b, alias, key in matcher.spans(clause)]
    symbol_quotes = []
    for quote in QUOTED.finditer(clause):
        term = quote.group(1)
        # Everyday advice may quote a phrase without naming a dream symbol. A quote
        # used as an interpretation's subject or introduced as dreamed content does name one.
        symbolic = (
            clause[quote.start()] == "「"
            or INTERPRETS.match(clause, quote.end())
            or DREAMED.search(clause[: quote.start()])
        )
        start, end = quote.span(1)
        if symbolic:
            symbol_quotes.append((start, end))
        key = matcher.aliases.get(term) or (matcher.match(term)["key"] if symbolic else None)
        # A fuzzy match for a compound quote must not erase its other symbols (猫和蛇).
        inner = [m for m in mentions if start <= m[0] < end]
        if key and all(m[3] == key for m in inner):
            mentions = [m for m in mentions if not (start <= m[0] < end)]
            mentions.append((start, end, term, key))
    bound = [(re.escape(phrase), key) for phrase, key in (phrases or {}).items()]
    # The same controlled construction in other words (一颗颗 for 一颗一颗) is that hit too.
    bound += [
        (OUTPUT_NORMALISATIONS[key].pattern, key)
        for key in set((phrases or {}).values())
        if key in OUTPUT_NORMALISATIONS
    ]
    for pattern, key in bound:
        for match in re.finditer(pattern, clause):
            # Only the recognised construction is one object, not its whole source phrase.
            mentions = [m for m in mentions if not (match.start() <= m[0] < match.end())]
            mentions.append((match.start(), match.end(), match[0], key))
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
        key = (aliases or {}).get(alias, key)
        if key not in hits:
            quoted = any(a <= start and end <= b for a, b in symbol_quotes) or (
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
    # Only the active dream pipeline submission uses source-phrase aliases. A later
    # agent turn has no pipeline_run marker and retains the ordinary plugin rules.
    pipeline = bool(state.get("pipeline_run") and reading.systems_used == ["dream"])
    matched = [h for r in found for h in r["hits"]]
    aliases = hit_aliases(matcher, matched, state.get("question")) if pipeline else {}
    phrases = phrase_hits(matched, matcher) if pipeline else {}
    for text in texts:
        error = text_error(text, matcher, hits, misses, aliases=aliases, phrases=phrases)
        if error:
            return error
    return None


# 没有 directly before the verb denies it (r10: 这个梦没有预示什么), unless it is itself denied
# (不是没有预示). A declined analysis may list the prophecy word with another one (r10 single:
# 不作诊断或预兆解读 / 不作诊断或预示解读).
# Either denial is void under an outer one, adjacent or across a short subject (PR #53
# review F1: 这个梦不可能没有预示…, 不能说这个梦没有预示…, 这个梦不是不提供预言).
# A degree word belongs to the inner denial (r12 review: 这个梦不可能完全没有预示…), so the outer
# one is still found before it.
NO_PROPHECY = re.compile(r"(?:并)?(?:完全|根本|压根|从来|丝毫|一点也|一点都)?没(?:有)?$")
DECLINED = re.compile(
    r"(?:不作|不做|不进行|不提供|不给出)(?:[\u4e00-\u9fff]{1,4}(?:或|和|与|、|及|以及))?$"
)
LEADING_SUBJECT = re.compile(r"(?:这个梦|这场梦|梦境|梦|它|这)$")
OUTER_DENIAL = re.compile(r"(?:不可能|不会|未必|不见得|难说|很难说)(?:说)?$")


def inner_denial(pattern, before):
    """A denial ending ``before`` that no outer denial governs."""
    match = pattern.search(before)
    if match is None:
        return None
    prefix = before[: match.start()]
    if denial_negated(prefix) or OUTER_DENIAL.search(LEADING_SUBJECT.sub("", prefix)):
        return None
    return match


def prophecy_negated(text, match) -> bool:
    """Whether a negation or a dismissal in its own clause governs this prophecy word."""
    before = clause_before(text, match.start(), 40)
    if inner_denial(DECLINED, before):
        return True
    if match[0] in ("预示", "预言") and inner_denial(NO_PROPHECY, before):
        return True
    comparison = OMEN_COMPARISON.search(before)
    if comparison and OMEN.fullmatch(match[0]):
        after = re.split(r"[。；;！!？?\n]", text[match.end() :], maxsplit=1)[0].strip()
        return bool(SAFE_OMEN_COMPARISON[comparison[1]].fullmatch(after))
    if negates_claim(before):
        return True
    if not OMEN.fullmatch(match[0]):
        return False
    # A contrast starts a new assertion: 不是坏事而是预兆 affirms it.
    before = re.split(r"但是|然而|不过|反而|而是|可是|却|但", before)[-1]
    return bool(inner_denial(DENIED_OMEN, before))


def text_error(text, matcher, hits, misses, *, aliases=None, phrases=None):
    """The first problem of one user-visible text: a prophecy, or an ungrounded symbol."""
    for match in PROPHECY.finditer(text):
        if not prophecy_negated(text, match):
            return "解梦只提供心理层面的线索，不能把梦境说成现实事件的预兆"
    for clause in CLAUSES.split(text):
        error = ungrounded(clause, matcher, hits, misses, aliases=aliases, phrases=phrases)
        if error:
            return error
    return None
