import re

from common.facts import validate_calculation_facts
from common.safety import CRISIS as CRISIS  # Backwards-compatible public import.

HIGH_RISK = re.compile(r"疾病|癌|诊断|停药|治疗|健康|投资|股票|基金|借贷|法律|诉讼|判刑|死亡|寿命")


def validate_reading(reading, session) -> str | None:
    state = session.state
    if not state.get("tarot_result") and not state.get("calculations"):
        return "必须先调用确定性计算工具"
    actual_systems = {s["system"] for s in state["signals"]}
    if set(reading.systems_used) != actual_systems or len(reading.systems_used) != len(
        actual_systems
    ):
        return "systems_used 必须恰好等于本次调用的体系，不能声称使用未调用的体系"
    refs = state["allowed_refs"]
    if any(item.ref_id not in refs for item in reading.evidence):
        return "evidence 引用必须来自本次工具生成的信号"
    text = reading.model_dump_json()
    public_text = " ".join(
        [
            reading.summary,
            *[e.reading for e in reading.evidence],
            *reading.advice,
            reading.safety.note,
        ]
    )
    if re.search(
        r"active_reading_id|missing_dependency|submit_reading|存储错误|保存失败|未能保存|知识库|未人工审核",
        public_text,
    ):
        return "正文不能包含内部状态、审核或存储错误信息"
    if re.search(r"仅供参考|仅供娱乐|仅供.*反思", public_text):
        return "免责声明由应用统一添加，正文不要重复"
    if (
        state.get("response_mode") != "followup"
        and (state.get("tarot_result") or {}).get("spread") == "decision"
    ):
        if not re.search(
            r"(?:倾向|优先|更支持|建议选择|先核实)\s*[AB]", reading.summary.split("。")[0]
        ):
            return "二选一summary第一句须明确A/B倾向并写现实条件"
        if not re.search(r"前提|条件|如果|若|先核实|待.*确认", reading.summary):
            return "二选一须说明暂定建议的现实条件"
    if state.get("response_mode") != "followup" and reading.question_type == "timing":
        if re.search(r"是否|适合|适宜|什么时候|何时|时机", state["question"]):
            if not re.search(
                r"适合|适宜|可以|不宜|暂缓|建议(?:开始|启动|等待|推迟)",
                reading.summary.split("。")[0],
            ):
                return "时机问题summary第一句须直接回答行动倾向并说明现实前提"
    for validator in session.output_validators.values():
        error = validator(reading, state)
        if error:
            return error
    error = validate_calculation_facts(reading, state)
    if error:
        return error
    if (
        any(not signal["reviewed"] for signal in state["signals"])
        and reading.confidence.level != "low"
    ):
        return "释义尚未人工审核，confidence 必须为 low 并解释原因"
    current_question = session.user_messages[-1] if session.user_messages else ""
    if HIGH_RISK.search(state["question"] + current_question):
        if not reading.safety.flag or not reading.safety.note:
            return "涉及健康、投资、法律或生死，必须标注安全说明"
        if re.search(
            r"(?<!不)(?<!不能)(?<!无法)保证收益|一定会|稳赚|必死|(?<!不)可以停药|必然确诊", text
        ):
            return "不能给出健康、投资或生死的确定性结论"
    return None
