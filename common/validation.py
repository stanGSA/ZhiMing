import re

from common.facts import validate_calculation_facts
from common.output_policy import (
    authored_texts,
    care_error,
    certainty_error,
    normalize_reading,
    warn,
)
from common.safety import CRISIS as CRISIS  # Backwards-compatible public import.

HIGH_RISK = re.compile(r"疾病|癌|诊断|停药|治疗|健康|投资|股票|基金|借贷|法律|诉讼|判刑|死亡|寿命")
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


def report_matches_profile(report: dict, profile: dict) -> bool:
    """Compare the fields the expert actually depends on; older reports use their version."""
    dependencies = report.get("profile_dependencies")
    if dependencies is None:
        return report.get("profile_version", 0) == profile.get("version", 0)
    return all(profile.get(field) == value for field, value in dependencies.items())


def validate_reading(reading, session) -> str | None:
    """Hard checks on facts and safety; wording is repaired first, style is only recorded."""
    state = session.state
    if not state.get("tarot_result") and not state.get("calculations"):
        return "必须先调用确定性计算工具"
    normalize_reading(reading, state)
    actual_systems = {s["system"] for s in state["signals"]}
    if set(reading.systems_used) != actual_systems or len(reading.systems_used) != len(
        actual_systems
    ):
        return "systems_used 必须恰好等于本次调用的体系，不能声称使用未调用的体系"
    refs = state["allowed_refs"]
    if any(item.ref_id not in refs for item in reading.evidence):
        return "evidence 引用必须来自本次工具生成的信号"
    if any(ref not in refs for section in reading.sections for ref in section.ref_ids):
        return "sections 的 ref_ids 必须来自本次工具生成的信号"
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
        if not re.search(r"(?:倾向|优先|更支持|建议选择|先核实)\s*[AB]", first):
            warn(state, "二选一summary第一句宜明确A/B倾向并写现实条件")
        if not re.search(r"前提|条件|如果|若|先核实|待.*确认", reading.summary):
            warn(state, "二选一宜说明暂定建议的现实条件")
    if state.get("response_mode") != "followup" and reading.question_type == "timing":
        if re.search(r"是否|适合|适宜|什么时候|何时|时机", state["question"]):
            if not re.search(r"适合|适宜|可以|不宜|暂缓|建议(?:开始|启动|等待|推迟)", first):
                warn(state, "时机问题summary第一句宜直接回答行动倾向并说明现实前提")
    # Recorded only: the verdict, layer titles and actions are read first and must not need
    # training to understand. A term the user asked about may be named.
    lead = [reading.summary, *[s.title for s in reading.sections], *reading.advice, reading.closing]
    terms = list(dict.fromkeys(t for text in lead for t in JARGON.findall(text) if t not in asked))
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
    error = certainty_error(authored_texts(reading)) or care_error(authored_texts(reading))
    if error:
        return error
    current_question = session.user_messages[-1] if session.user_messages else ""
    if HIGH_RISK.search(state["question"] + current_question):
        if not reading.safety.flag or not reading.safety.note:
            return "涉及健康、投资、法律或生死，必须标注安全说明"
        if re.search(
            r"(?<!不)(?<!不能)(?<!无法)保证收益|一定会|稳赚|必死|(?<!不)可以停药|必然确诊", text
        ):
            return "不能给出健康、投资或生死的确定性结论"
    return None
