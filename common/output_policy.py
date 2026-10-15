"""Expression-layer policy for authored readings and specialist reports.

Facts stay strict: plugin validators still reject invented 干支, 落座, 宫位, 相位, 牌面, dates
and ref_ids. Wording is no longer policed by rejection where code can repair it, because every
rejection teaches the model to write less:

* disclaimers and internal words are removed (the app adds one disclaimer itself);
* ``confidence`` and ``systems_used`` are filled in from what this session actually computed;
* a skipped specialist is disclosed in ``confidence.reason``;
* a remark about the body gets a "see a doctor if unwell" note.

Rejection on wording is reserved for certainty claims (一定会/必然/注定…). Trends may be stated
with 倾向/容易/往往. Checks that only judge style or completeness are recorded as warnings.
"""

from __future__ import annotations

import re

DISCLAIMER = re.compile(r"仅供参考|仅供娱乐|仅供[^。！？!?\n]{0,10}反思")
INTERNAL = re.compile(
    r"active_reading_id|missing_dependency|submit_reading|submit_report|"
    r"存储错误|保存失败|未能保存|未经?人工审核"
)
KB_WORD = re.compile(r"知识库(?:的|中的|里的)?(?:释义|条目|解释)?")
SENTENCE = re.compile(r"[^。！？!?\n]*(?:[。！？!?]+|\n|$)")

CERTAINTY = re.compile(r"一定会|一定能|一定是|必然|必定|注定|肯定会|绝对会|百分之百|毫无疑问|铁定")
NEGATION = re.compile(r"[不非未无没别]")
# "不管/不论/无论…都一定会" still asserts certainty.
CONCESSIVE = re.compile(r"不管|不论|无论")
CLAUSE_START = re.compile(r".*[，,。；;：:！!？?\n]")

HEALTH = re.compile(
    r"健康|身体|体力|透支|睡眠|失眠|熬夜|免疫|疲劳|脏腑|[心肝脾肺肾]脏|肾|肝|脾胃|肠胃|"
    r"泌尿|血压|头痛|头疼|疾病|生病|病症|养生|养肾|养肝"
)
MEDICAL_CARE = re.compile(r"就医|医生|医院|体检|就诊|专业医疗")
HEALTH_NOTE = "如有身体不适，请及时就医，以医生的诊断为准。"
UNREVIEWED_NOTE = "释义为未经人工审核的草稿"


def warn(state: dict, message: str) -> None:
    """Record a style or completeness finding without rejecting the answer."""
    warnings = state.setdefault("output_warnings", [])
    if message not in warnings:
        warnings.append(message)


def clean(text: str) -> str:
    """Drop sentences carrying a disclaimer or internal state; keep the rest verbatim."""
    if not text:
        return text
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


def certainty_claim(texts) -> str | None:
    """The first affirmative certainty word.

    A negation earlier in the same clause cancels it: "不一定会", "并非注定",
    "不代表事件必然发生" (wording the knowledge base itself uses) are not claims.
    """
    for text in texts:
        for match in CERTAINTY.finditer(text or ""):
            before = text[max(0, match.start() - 12) : match.start()]
            before = CLAUSE_START.sub("", before)
            if NEGATION.search(CONCESSIVE.sub("", before)):
                continue
            return match.group()
    return None


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
        tension.how_to_read = clean(tension.how_to_read)
        tension.sides = [clean(side) for side in tension.sides]
    for item in reading.timeline:
        item.note = clean(item.note)
    reading.followups = clean_list(reading.followups)
    reading.safety.note = clean(reading.safety.note)


def mark_unreviewed(confidence, signals) -> None:
    """Unreviewed meanings mean low confidence; code sets it instead of rejecting."""
    if all(s.get("reviewed") for s in signals):
        return
    confidence.level = "low"
    if "审核" not in confidence.reason:
        confidence.reason = (
            f"{confidence.reason.rstrip('。；; ')}；{UNREVIEWED_NOTE}。"
            if confidence.reason.strip()
            else f"{UNREVIEWED_NOTE}。"
        )


def add_health_note(reading) -> None:
    texts = [t for t in authored_texts(reading) if t]
    if not any(HEALTH.search(t) for t in texts):
        return
    if any(MEDICAL_CARE.search(t) for t in texts):
        if reading.safety.note and MEDICAL_CARE.search(reading.safety.note):
            reading.safety.flag = True
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
    mark_unreviewed(report.confidence, signals)
