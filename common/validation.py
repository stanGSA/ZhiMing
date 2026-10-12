import re

from common.safety import CRISIS as CRISIS  # Backwards-compatible public import.
from plugins.tarot.catalogue import DECK

HIGH_RISK = re.compile(r"疾病|癌|诊断|停药|治疗|健康|投资|股票|基金|借贷|法律|诉讼|判刑|死亡|寿命")


def validate_reading(reading, session) -> str | None:
    state = session.state
    if not state.get("tarot_result"):
        return "必须先调用确定性计算工具"
    if reading.systems_used != ["tarot"]:
        return "第一周只提供塔罗；不能声称使用了未调用的体系"
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
    if state.get("response_mode") != "followup" and state["tarot_result"]["spread"] == "decision":
        if not re.search(
            r"(?:倾向|优先|更支持|建议选择|先核实)\s*[AB]", reading.summary.split("。")[0]
        ):
            return "二选一summary第一句须明确A/B倾向并写现实条件"
        if not re.search(r"前提|条件|如果|若|先核实|待.*确认", reading.summary):
            return "二选一须说明暂定建议的现实条件"
    if state.get("response_mode") != "followup" and re.search(r"下个月.*跳槽", state["question"]):
        if not re.search(
            r"下个月.*(?:适合|适宜|不宜|建议|可以).*跳槽|(?:适合|不适合|不宜|建议).*下个月.*跳槽",
            reading.summary.split("。")[0],
        ):
            return "跳槽时机summary第一句须直接回答下个月是否适合并说明前提"
    actual = set(state["facts"])
    for _, name in DECK:
        explicit = re.search(
            rf"(?:【|「|《){re.escape(name)}(?:】|」|》)|{re.escape(name)}(?:正位|逆位|牌)", text
        )
        # Full minor-arcana names are unambiguous; common major names need card context.
        if (
            explicit or (name.startswith(("权杖", "圣杯", "宝剑", "星币")) and name in text)
        ) and name not in actual:
            return f"正文提到未抽出的牌：{name}"
    cards_by_ref = {c["ref_id"]: c for c in state["tarot_result"]["cards"]}
    for evidence in reading.evidence:
        card = cards_by_ref[evidence.ref_id]
        orientation = "逆位" if card["reversed"] else "正位"
        opposite = "正位" if card["reversed"] else "逆位"
        if (
            f"{card['name']}{opposite}" in evidence.reading
            or f"{card['name']}】{opposite}" in evidence.reading
        ):
            return f"牌面方向错误，应为{orientation}"
    if re.search(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", text):
        return "本次没有八字工具结果，不能编造干支"
    if re.search(
        r"(?:太阳|月亮|水星|金星|火星|木星|土星|上升)(?:落在|位于|在|落入).{0,3}(?:白羊|金牛|双子|巨蟹|狮子|处女|天秤|天蝎|射手|摩羯|水瓶|双鱼)",
        text,
    ):
        return "本次没有占星工具结果，不能编造星体位置"
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
