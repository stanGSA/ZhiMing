import json
import re

from common.evidence import calculation_evidence_texts, fill_evidence
from common.facts import validate_calculation_facts
from common.output_policy import (
    authored_texts,
    care_error,
    certainty_claim,
    certainty_error,
    normalize_reading,
    warn,
)
from common.safety import CRISIS as CRISIS  # Backwards-compatible public import.
from harness.models import ValidationMessage
from harness.refs import short

# What counts as a high-risk question, and the safety note code writes for each kind
# (pipeline/render.py). One list, so recognising a risk and writing its note cannot drift apart.
RISKS = (
    (
        "investment",
        r"投资|股票|基金|借贷|借钱|贷款|期货|理财|积蓄|炒币|杠杆",
        "这不构成投资建议；涉及大额资金请结合自身财务状况，必要时咨询持牌专业人士。",
    ),
    (
        "health",
        r"疾病|癌|诊断|停药|治疗|健康",
        "这不能代替诊断；如有身体不适，请及时就医，以医生的诊断为准。",
    ),
    ("law", r"法律|诉讼|判刑", "这不构成法律意见；具体问题请咨询专业律师。"),
    (
        "life",
        r"死亡|寿命",
        "生死与寿命不作预测；如有健康方面的担忧，请及时就医或联系信任的人。",
    ),
)
HIGH_RISK = re.compile("|".join(pattern for _, pattern, _ in RISKS))


def risk_note(text: str) -> str | None:
    """The safety note for the first kind of risk the text carries, if any."""
    return next((note for _, pattern, note in RISKS if re.search(pattern, text)), None)


# Questions that ask whether or when to act; only these call for "适合/暂不适合" as an answer.
SUITABILITY = re.compile(
    r"是否|适合|适宜|适不适|要不要|该不该|能不能|可不可以|可以.{0,12}[吗么]|什么时候|何时|时机"
)
# Terms a reader without training cannot parse: 十神, 干支 pillars, branch clashes, aspects and
# house numbers. “自己未来” is not the pillar 己未, nor “节日主题” the 日主.
JARGON = re.compile(
    r"七杀|偏官|正官|正财|偏财|正印|偏印|枭神|印星|财星|官星|食神|伤官|食伤|劫财|十神|"
    r"日主(?![题要持角动导])|喜用神?|用神|"
    r"(?<!自)[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]|"
    r"[子丑寅卯辰巳午未申酉戌亥]{2}相?[冲合刑害破]|"
    r"(?:对分|四分|三分|六分|刑|拱)相|第[一二三四五六七八九十\d]{1,2}宫"
)


def requested_jargon(term: str, asked: str) -> bool:
    """An explicitly requested result may name a value the user does not yet know."""
    if term in asked:
        return True
    if re.fullmatch(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", term):
        return bool(re.search(r"干支|四柱|[年月日时]柱|大运|首运", asked))
    if re.fullmatch(r"第[一二三四五六七八九十\d]{1,2}宫", term):
        return bool(re.search(r"宫位|[几哪]个?宫", asked))
    if term.endswith("相") and "相位" in asked:
        return True
    return "十神" in asked and term in (
        "七杀|偏官|正官|正财|偏财|正印|偏印|枭神|印星|财星|官星|食神|伤官|食伤|劫财"
    ).split("|")


def report_matches_profile(report: dict, profile: dict) -> bool:
    """Compare the fields the expert actually depends on; older reports use their version."""
    dependencies = report.get("profile_dependencies")
    if dependencies is None:
        return report.get("profile_version", 0) == profile.get("version", 0)
    return all(profile.get(field) == value for field, value in dependencies.items())


def citation_error(session, cited, allowed, rendered=None) -> str | None:
    """Every invalid reference of a draft at once, by field path, with what may be cited.

    ``cited`` holds (path, reference, needs rendered text) for each reference in the draft.
    The model knows references by their R-numbers, so the message names them that way.
    """
    state = session.state
    seen = set(state.get("ref_alias", {}).values())
    rendered = rendered or {}
    problems = []
    for path, ref, needs_text in cited:
        if ref in allowed:
            if needs_text and ref not in rendered:
                problems.append(
                    (path, ref, "没有可渲染的事实文本，须自写reading或改用下列编号", "missing_text")
                )
            continue
        if ref in (state.get("kb_refs") or ()):
            why = "是知识库释义条目，不是本次计算事实"
            reason = "knowledge_entry"
        elif ref in seen:
            why = "不属于本次记录的计算事实"
            reason = "other_reading"
        else:
            why = "不是工具返回过的编号"
            reason = "unknown_reference"
        problems.append((path, ref, why, reason))
    if not problems:
        return None
    for ref in sorted(set(allowed) - seen):
        short(ref, session)  # Number unseen citable facts in a stable order.
    names = {full: alias for alias, full in state["ref_alias"].items()}
    usable = sorted(((names[ref], ref) for ref in allowed), key=lambda item: int(item[0][1:]))
    listed = "、".join(
        f"{alias}（{rendered[ref][:40]}）" if ref in rendered else alias
        for alias, ref in usable[:24]
    )
    more = f"等共{len(usable)}条" if len(usable) > 24 else ""
    message = (
        "引用无效，请只修改这些编号后重新提交，正文可保持不变："
        + "；".join(f"{path}={names.get(ref, ref)}{why}" for path, ref, why, _ in problems)
        + f"。本次可引用：{listed or '无'}{more}。"
    )
    # Paths, duplicate occurrences and rendered hints can change without repairing the refs.
    identity = sorted({(ref, reason) for _, ref, _, reason in problems})
    return ValidationMessage(message, retry_key="invalid_citation:" + json.dumps(identity))


def validate_reading(reading, session) -> str | None:
    """Hard checks on facts and safety; wording is repaired first, style is only recorded."""
    state = session.state
    if not state.get("tarot_result") and not state.get("calculations"):
        return "必须先调用确定性计算工具"
    fill_evidence(reading, state)
    cited = [
        (f"evidence.{i}.ref_id", item.ref_id, not item.reading)
        for i, item in enumerate(reading.evidence)
    ]
    cited += [
        (f"sections.{i}.ref_ids.{j}", ref, False)
        for i, section in enumerate(reading.sections)
        for j, ref in enumerate(section.ref_ids)
    ]
    error = citation_error(session, cited, state["allowed_refs"], calculation_evidence_texts(state))
    if error:
        return error
    normalize_reading(reading, state)
    actual_systems = {s["system"] for s in state["signals"]}
    if set(reading.systems_used) != actual_systems or len(reading.systems_used) != len(
        actual_systems
    ):
        return "systems_used 必须恰好等于本次调用的体系，不能声称使用未调用的体系"
    text = reading.model_dump_json()
    public_text = " ".join(authored_texts(reading))
    # Normalization already removed such sentences; whatever is left is a field made only of them.
    if re.search(
        r"active_reading_id|missing_dependency|submit_reading|存储错误|保存失败|未能保存|知识库|未人工审核",
        public_text,
    ):
        return "正文不能包含内部状态、审核或存储错误信息"
    if re.search(r"仅供参考|仅供娱乐|仅供.*反思", public_text):
        return "免责声明由应用统一添加，正文不要重复"
    first = reading.summary.split("。")[0]
    decision = (state.get("tarot_result") or {}).get("spread") == "decision"
    asked = state["question"] + " " + (session.user_messages[-1] if session.user_messages else "")
    if state.get("response_mode") != "followup":
        # Recorded only: a verdict hedged in its first sentence reads as no answer at all.
        if "前提" in first:
            warn(state, "summary第一句宜先表态，前提放到第二句")
        if "有条件适合" in first and not decision and not SUITABILITY.search(asked):
            warn(state, "非时机问题的第一句宜直接回答所问，不套用“有条件适合”")
    if state.get("response_mode") != "followup" and decision:
        if reading.verdict not in ("prefer_a", "prefer_b"):
            warn(state, "二选一summary第一句宜明确A/B倾向并写现实条件")
        if not re.search(r"前提|条件|如果|若|先核实|待.*确认", reading.summary):
            warn(state, "二选一宜说明暂定建议的现实条件")
    if state.get("response_mode") != "followup" and reading.question_type == "timing":
        if re.search(r"是否|适合|适宜|什么时候|何时|时机", state["question"]):
            if reading.verdict not in ("suitable", "not_now", "conditional"):
                warn(state, "时机问题summary第一句宜直接回答行动倾向并说明现实前提")
    # Recorded only: the verdict, layer titles and actions are read first and must not need
    # training to understand. A term the user asked about may be named.
    lead = [reading.summary, *[s.title for s in reading.sections], *reading.advice, reading.closing]
    terms = list(
        dict.fromkeys(
            t for text in lead for t in JARGON.findall(text) if not requested_jargon(t, asked)
        )
    )
    if terms:
        warn(
            state,
            f"summary、小标题、advice和closing宜用白话，术语（{'、'.join(terms[:5])}）"
            "放进正文并附白话解释",
        )
    # Fresh readings must use reports calculated with the current dependent profile
    # fields. Historical follow-ups deliberately retain their saved facts.
    if state.get("response_mode") != "followup":
        for report in (state.get("specialist_reports") or {}).values():
            if report["status"] == "ok" and not report_matches_profile(report, session.profile):
                return f"{report['label']}所需画像已更正，须重新咨询该专家后再提交"
    for validator in session.output_validators.values():
        error = validator(reading, state)
        if error:
            return error
    error = validate_calculation_facts(reading, state)
    if error:
        return error
    if session.policy_judge is not None:
        from common.policy_judge import HARD, candidates

        texts = authored_texts(reading)
        if any(HARD.search(text) for text in texts):
            return "不能给出确定性结果或停药建议，请改写"
        state["policy_candidates"] = candidates(texts)
        error = None
    else:
        error = certainty_error(authored_texts(reading)) or care_error(authored_texts(reading))
    if error:
        return error
    current_question = session.user_messages[-1] if session.user_messages else ""
    if HIGH_RISK.search(state["question"] + current_question):
        if not reading.safety.flag or not reading.safety.note:
            return "涉及健康、投资、法律或生死，必须标注安全说明"
        # 一定会 counts only where no negation governs it, as everywhere else: "不一定会" and
        # "这不代表这只股票一定会涨" are the hedges these answers are asked to write.
        if certainty_claim(authored_texts(reading)) or re.search(
            r"(?<!不)(?<!不能)(?<!无法)保证收益|稳赚|必死|(?<!不)可以停药|必然确诊", text
        ):
            return "不能给出健康、投资或生死的确定性结论"
    return None
