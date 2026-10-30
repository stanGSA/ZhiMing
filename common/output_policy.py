"""Expression-layer policy for authored readings and specialist reports.

Facts stay strict: plugin validators still reject invented 干支, 落座, 宫位, 相位, 牌面, dates
and ref_ids. Wording is no longer policed by rejection where code can repair it, because every
rejection teaches the model to write less:

* disclaimers and internal words are removed (the app adds one disclaimer itself);
* HTML line breaks (``<br>``) become real line breaks;
* ``confidence`` and ``systems_used`` are filled in from what this session actually computed;
* a skipped specialist is disclosed in ``confidence.reason``;
* a remark about the body gets a visible "see a doctor if unwell" note.

Rejection on wording is reserved for certainty claims (一定会/必然/注定…) and for discouraging
medical care. Trends may be stated with 倾向/容易/往往. Checks that only judge style or
completeness are recorded as warnings.
"""

from __future__ import annotations

import re

from common.facts import rendered_texts
from knowledge.review import lowest, review_status

DISCLAIMER = re.compile(r"仅供参考|仅供娱乐|仅供[^。！？!?\n]{0,10}反思")
INTERNAL = re.compile(
    r"active_reading_id|missing_dependency|submit_reading|submit_report|"
    r"存储错误|保存失败|未能保存|未经?人工审核"
)
KB_WORD = re.compile(r"知识库(?:的|中的|里的)?(?:释义|条目|解释)?")
# Replies are plain text; a model writing HTML line breaks would show them literally.
BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
SENTENCE = re.compile(r"[^。！？!?\n]*(?:[。！？!?]+|\n|$)")

CERTAINTY = re.compile(r"一定会|一定能|一定是|必然|必定|注定|肯定会|绝对会|百分之百|毫无疑问|铁定")
# Shared with source checks. Only enumerated subjects and predicates are accepted;
# an intervening predicate or contrast must not hide a separate affirmative claim.
DISCLAIMER_CLAIM = (
    r"(?:现实运势或事件|现实事件|现实发展|现实生活|实际情况|使用此数的人|个人|精力|事件|困扰|状态|负担)?"
    r"(?:必然|一定会?|注定)(?:会)?"
    r"(?:发生|出现|如此|成立|消退|好转|减轻|顺利|不利|受牵扯|遭遇波折|具备|具有)"
)
NEGATED_DISCLAIMER = re.compile(
    r"(?:并不|并非|不)(?:代表|表示|意味着?|等于|预示|说明)"
    + DISCLAIMER_CLAIM
    + rf"(?:(?:或|以及){DISCLAIMER_CLAIM})*"
)
# A negation cancels a certainty word only when it governs that word: directly ("不一定会",
# "并非注定", "不是必然") or through a negated framing verb earlier in the clause ("不代表事件
# 必然发生", "并不意味着一定会"). A stray negative character ("不久后你一定会…") does not.
DIRECT_NEGATION = re.compile(
    r"(?:不|并不|并非|非|未|绝非|不是|并不是|不会|不能|无法)(?:是|会|就|能)?$"
)
NEGATED_FRAME = re.compile(
    r"(?:不|并不|并非|未|没有|不能|无法|不会|并不会|没人能|没有人能|谁也不能)"
    r"(?:代表|意味着?|等于|说明|表示|保证|确定|断定|断言|预示|预言|预告|告诉|说|认为|觉得)"
    r"|(?:别|不要)(?:以为|认为|觉得)"
)
# "不是说/并非指" report a clause, and "并非/绝非" negate one ("并非股价一定会涨"): both govern
# its subject, as a framing verb does. A bare "不是" names what something is ("这不是坏事"), so
# a clause after it is a new one unless it starts with a pronoun or a demonstrative ("不是你一定
# 会失败", "不是这只股票一定会涨").
NEGATED_SUBJECT = re.compile(r"(?:并非|绝非|并不是|不是)(?:说|指)|并非|绝非")
COPULA = re.compile(r"(?:并不是|不是)")
# What a negation governs is the claim's own subject. Regular expressions cannot parse it, so
# the phrase is held to the shape of one short noun phrase, such as "行情", "某件事", "具体事件",
# "留下就", "你们的关系" or "你今天": anything that might be a second clause is refused. A
# negation, a contrast, a claim of its own, or a second subject (a pronoun, a demonstrative, a
# noun after a predicate) ends what it governs: "不认为这很难你一定会成功" negates "很难",
# "这不是坏事这只股票一定会涨" negates "坏事", neither the claim.
SUBJECT_TEXT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9“”‘’「」]*")
MODIFIERS = re.compile(r"(?:就|也|都|会|能|将|真的|最终|近期|这个月|下个月|以后|未来|现实中)+$")
SUBJECT_BREAK = re.compile(
    r"[不没非无]|未(?!来)|但|而|或|却|可是|然而|就算|即使|" + CERTAINTY.pattern
)
PRONOUNS = r"你们|我们|他们|她们|咱们|你|您|我|他|她|它"
DEMONSTRATIVE = r"(?:这|那|该|某)(?:只|个|次|段|份|笔|些|种|件|张|位|家|条)?"
# A noun phrase: an optional pronoun, demonstrative and "…的", then its head. A head of four
# characters could be two words, a predicate and a new subject ("亏损行情", "过去的亏损股价"),
# whatever is in front of it, so it needs a modifier of its own ("具体事件", "全部投入");
# otherwise three at most.
LEAD = re.compile(
    rf"(?:(?:{PRONOUNS})(?:的|俩)?)?(?:{DEMONSTRATIVE}的?)?(?:[\u4e00-\u9fffA-Za-z0-9]{{1,4}}的)?"
)
HEAD = re.compile(r"[\u4e00-\u9fffA-Za-z0-9“”‘’「」]{0,4}")
HEAD_MODIFIER = re.compile(r"具体|全部|所有|整体|实际|现实|近期|未来")
# "行情对你必然有利": a pronoun after 对/给/让… is an object, not a new subject.
TRAILING_OBJECT = re.compile(rf"(?:对|给|让|和|跟|与|向|替|为)(?:{PRONOUNS})$")
LEADING = re.compile(rf"^(?:(?:{PRONOUNS})(?:的|俩)?)?(?:{DEMONSTRATIVE}的?)?")
LATER_SUBJECT = re.compile(rf"(?:{PRONOUNS})|(?:这|那)(?=[\u4e00-\u9fff])")
SUBJECT_START = re.compile(rf"(?:{PRONOUNS}|{DEMONSTRATIVE})")
# The certainty word as a noun under a negation: "这不是一种必然", "没有什么是注定的",
# "不必把这理解为必然".
NEGATED_NOUN = re.compile(
    r"(?:不是|并不是|并非|绝非)(?:一种|一个)$"
    r"|(?:没有|并没有)(?:什么|哪种|哪个|任何)(?:结果|事情|事|结局)?(?:是|会是)$"
    r"|(?:不必|不要|别|不用)把(?:这|它|这些|这张牌|牌面)?(?:理解为|看作|看成|当作|当成|视为)$"
)
CLAUSE_START = re.compile(r".*[，,。；;：:！!？?\n]")

HEALTH = re.compile(
    r"健康|身体|体力|透支|睡眠|失眠|熬夜|免疫|疲劳|脏腑|[心肝脾肺肾]脏|肾|肝|脾胃|肠胃|"
    r"泌尿|血压|头痛|头疼|疾病|生病|病症|症状|养生|养肾|养肝"
)
# Seeking care, as an action; "医院附近" or "医生朋友" are not advice.
CARE_ACTION = re.compile(
    r"就医|就诊|看医生|找医生|咨询医生|请医生|去医院|到医院|医院检查|做检查|体检|"
    r"专业医疗|医疗帮助|医疗机构"
)
DISCOURAGE = re.compile(
    r"(?:无需|无须|不用|不必|没必要|不需要|用不着|不建议|不推荐|不应当?|不应该|"
    r"不能|不可|不得|别|不要|免得|省得|避免)"
    r"(?:再|去|特意|专门|马上|立即|及时|尽快|主动|直接|考虑|寻求|接受|进行)*$"
)
ADVISE = re.compile(r"请|应当|应该|应|建议|及时|尽快|务必|最好|宜|需要|如有|若有|如果|一旦|记得")
# Medical negation deliberately excludes "不代表/不说明": these can govern a
# separate diagnosis, as in "这不代表你有病不需要就医".
CARE_NEGATED_BELIEF = re.compile(
    r"(?:不要|别|不能|不可|不应|不应该|并不|不)(?:以为|认为|觉得)"
    r"(?:你们|我们|你|您|我)?"
    r"(?:(?:身体不适|有症状|生病|有病)(?:时|的时候))?$"
)
CARE_DIRECT_NEGATION = re.compile(r"(?:并非|绝非|并不是|不是)$")
CARE_CONDITION = re.compile(r"(?:如果|若|万一|一旦)(?:你们|我们|你|您|我)?(?:暂时|一时)?$")
HEALTH_NOTE = "如有身体不适，请及时就医，以医生的诊断为准。"
# Lowest review level of the meanings used → confidence cap and the fact the reason must state.
# Model cross-review is never written as human review (项目完善计划书 4.2; cap: stage 1 decision 2).
REVIEW_CAP = {"draft": "low", "model_reviewed": "medium", "human_reviewed": None}
REVIEW_NOTE = {"draft": "释义未经审核", "model_reviewed": "释义经模型交叉审核，未经人工审核"}
# Wordings that already state the level; any other clause about 审核 is replaced by the note.
REVIEW_STATED = {
    "draft": re.compile(r"未经?(?:人工)?审核|没有(?:经过)?(?:人工)?审核"),
    "model_reviewed": re.compile(r"模型交叉审核.*未经?人工审核|未经?人工审核.*模型交叉审核"),
}
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
REASON_CLAUSE = re.compile(r"[^，,。；;\n]*(?:[，,。；;\n]+|$)")


def warn(state: dict, message: str) -> None:
    """Record a style or completeness finding without rejecting the answer."""
    warnings = state.setdefault("output_warnings", [])
    if message not in warnings:
        warnings.append(message)


def normalize_breaks(text: str) -> str:
    """Normalize plain-text line breaks without removing metadata or changing identifiers."""
    return BREAK_TAG.sub("\n", text)


def clean(text: str) -> str:
    """Drop sentences carrying a disclaimer or internal state; keep the rest verbatim."""
    if not text:
        return text
    text = normalize_breaks(text)
    kept = [
        piece
        for piece in SENTENCE.findall(text)
        if piece and not DISCLAIMER.search(piece) and not INTERNAL.search(piece)
    ]
    result = KB_WORD.sub("传统释义", "".join(kept)).strip()
    # A field that is nothing but a disclaimer stays as written; the hard check rejects it.
    return result or text


def clean_list(values: list[str]) -> list[str]:
    """List items that are nothing but a disclaimer or internal note are dropped."""
    cleaned = [clean(value) for value in values]
    return [v for v in cleaned if not (DISCLAIMER.search(v) or INTERNAL.search(v))]


def authored_texts(reading) -> list[str]:
    """Every authored string of a reading, for policy checks (confidence.reason excluded)."""
    return [
        reading.summary,
        *[part for s in reading.sections for part in (s.title, s.body)],
        *[e.reading for e in reading.evidence],
        *reading.advice,
        reading.closing,
        *reading.resonances,
        *[part for t in reading.tensions for part in (t.theme, *t.sides, t.how_to_read)],
        *[part for t in reading.timeline for part in (t.period, t.note)],
        *reading.followups,
        reading.safety.note,
    ]


def clause_before(text: str, start: int, width: int = 16) -> str:
    """The part of the clause in front of a match, at most ``width`` characters."""
    return CLAUSE_START.sub("", text[max(0, start - width) : start])


def certainty_claim(texts) -> str | None:
    """The first certainty word that no negation in its clause governs."""
    for text in texts:
        text = NEGATED_DISCLAIMER.sub(" ", text or "")
        for match in CERTAINTY.finditer(text):
            before = clause_before(text, match.start(), 40)
            if negates_claim(before):
                continue
            return match.group()
    return None


def negates_claim(before: str) -> bool:
    """Only a governing negation cancels a claim, never an unrelated negative character.

    A subject may intervene in “并非你一定会…”. A contrast starts a new assertion even
    without a comma (“不代表过去不好但你一定会…”).
    """
    before = re.split(r"但是|然而|不过|反而|而是|但", before)[-1].strip()
    return bool(
        DIRECT_NEGATION.search(before)
        or NEGATED_NOUN.search(before)
        or any(
            claim_subject(before[match.end() :])
            for pattern in (NEGATED_FRAME, NEGATED_SUBJECT)
            for match in pattern.finditer(before)
        )
        or any(
            claim_subject(rest) and (not rest or SUBJECT_START.match(rest))
            for match in COPULA.finditer(before)
            for rest in [MODIFIERS.sub("", before[match.end() :].strip())]
        )
    )


def claim_subject(phrase: str) -> bool:
    """Whether ``phrase`` is no more than the subject of the claim that follows it."""
    phrase = TRAILING_OBJECT.sub("", MODIFIERS.sub("", phrase.strip()))
    if not SUBJECT_TEXT.fullmatch(phrase) or SUBJECT_BREAK.search(phrase):
        return False
    lead = LEAD.match(phrase).group()
    head = phrase[len(lead) :]
    if not HEAD.fullmatch(head) or (len(head) == 4 and not HEAD_MODIFIER.match(head)):
        return False
    return not LATER_SUBJECT.search(LEADING.sub("", phrase, count=1))


def certainty_error(texts) -> str | None:
    word = certainty_claim(texts)
    if word:
        return f"不能使用“{word}”这类确定性说法；趋势可以写“倾向/容易/往往”，请改写后重新提交"
    return None


def clean_reading(reading) -> None:
    reading.summary = clean(reading.summary)
    for section in reading.sections:
        section.title = clean(section.title)
        section.body = clean(section.body)
    for item in reading.evidence:
        item.reading = clean(item.reading)
    reading.advice = clean_list(reading.advice)
    reading.closing = clean(reading.closing)
    reading.resonances = clean_list(reading.resonances)
    for tension in reading.tensions:
        tension.theme = normalize_breaks(tension.theme)
        tension.how_to_read = clean(tension.how_to_read)
        tension.sides = [clean(side) for side in tension.sides]
    for item in reading.timeline:
        item.period = normalize_breaks(item.period)
        item.note = clean(item.note)
    reading.followups = clean_list(reading.followups)
    reading.safety.note = clean(reading.safety.note)
    reading.confidence.reason = normalize_breaks(reading.confidence.reason)


def mark_unreviewed(confidence, signals) -> None:
    """Cap confidence by the least reviewed meaning used; code sets it instead of rejecting.

    The reason must state that level. A clause about 审核 that states something else (for
    example that a draft was reviewed by a person) is dropped and the note added.
    """
    level = lowest(review_status(s) for s in signals)
    cap = REVIEW_CAP[level]
    if cap is None:
        return
    if CONFIDENCE_RANK[confidence.level] > CONFIDENCE_RANK[cap]:
        confidence.level = cap
    stated = REVIEW_STATED[level]
    clauses = [c for c in REASON_CLAUSE.findall(confidence.reason) if c]
    kept = [c for c in clauses if "审核" not in c or stated.search(c)]
    reason = confidence.reason if kept == clauses else "".join(kept).strip("，, ")
    if not stated.search(reason):
        note = REVIEW_NOTE[level]
        reason = f"{reason.rstrip('。；;，, ')}；{note}。" if reason.strip() else f"{note}。"
    confidence.reason = reason


def care_advice(texts) -> tuple[bool, str | None]:
    """(an affirmative "see a doctor" advice is present, the first discouraging phrase)."""
    advised, discouraged = False, None
    for text in texts:
        for match in CARE_ACTION.finditer(text or ""):
            before = clause_before(text, match.start(), 40)
            negative = DISCOURAGE.search(before)
            if negative:
                prefix = before[: negative.start()]
                suffix = text[match.end() :]
                # A conditional inability to obtain care is neither a prohibition nor
                # affirmative advice. Other clauses still need checking independently.
                if negative.group().startswith(("不能", "不可")) and (
                    CARE_CONDITION.search(prefix)
                    or re.match(r"(?:时|的时候|的话|的情况下)", suffix)
                ):
                    continue
                # “不要以为不必就医” negates the discouragement; “不建议就医” does not.
                if CARE_DIRECT_NEGATION.search(prefix) or CARE_NEGATED_BELIEF.search(prefix):
                    advised = True
                else:
                    discouraged = discouraged or (negative.group() + match.group())
            elif ADVISE.search(before):
                advised = True
    return advised, discouraged


def care_error(texts) -> str | None:
    _, discouraged = care_advice(texts)
    if discouraged:
        return (
            f"不能劝阻就医（“{discouraged}”）；谈到身体时保留“如有不适请及时就医”的建议，"
            "请改写后重新提交"
        )
    return None


def add_health_note(reading) -> None:
    """A remark about the body needs a visible, affirmative "see a doctor" advice.

    Only what the user actually sees counts (see rendered_texts); a mention of a hospital or
    a note hidden in an unrendered field does not. Discouraging care is rejected separately.
    """
    if not any(HEALTH.search(t) for t in authored_texts(reading) if t):
        return
    if care_advice(rendered_texts(reading))[0]:
        return
    if care_advice([reading.safety.note])[0]:
        reading.safety.flag = True  # The advice was written but would not have been shown.
        return
    note = reading.safety.note.strip()
    reading.safety.note = f"{note}{'' if not note or note[-1] in '。！!' else '。'}{HEALTH_NOTE}"
    reading.safety.flag = True


def normalize_reading(reading, state: dict) -> None:
    """Repair what code can repair before the hard checks run (idempotent)."""
    state["output_warnings"] = []
    clean_reading(reading)
    signals = state.get("signals") or []
    actual = {s["system"] for s in signals}
    if actual and set(reading.systems_used) != actual:
        ordered = [s for s in dict.fromkeys(reading.systems_used) if s in actual]
        ordered += sorted(actual - set(ordered))
        reading.systems_used = ordered
    mark_unreviewed(reading.confidence, signals)
    if state.get("response_mode") != "followup":
        for system, report in (state.get("specialist_reports") or {}).items():
            if report["status"] == "ok":
                continue
            reason = reading.confidence.reason
            if report["label"] in reason or system in reason:
                continue
            why = report.get("failure") or (
                "需要补充资料" if report["status"] == "needs_input" else "未完成"
            )
            reading.confidence.reason = (
                f"{reason.rstrip('。；; ')}；缺少{report['label']}：{why}。"
                if reason.strip()
                else f"缺少{report['label']}：{why}。"
            )
    add_health_note(reading)


def normalize_report(report, signals) -> None:
    """The specialist counterpart of normalize_reading."""
    report.answer = clean(report.answer)
    report.analysis = clean(report.analysis)
    for point in report.points:
        point.text = clean(point.text)
    report.missing = clean_list(report.missing)
    report.confidence.reason = normalize_breaks(report.confidence.reason)
    mark_unreviewed(report.confidence, signals)
