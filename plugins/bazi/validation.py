"""Bazi output checks: every 干支 and pillar must come from this reading's calculations.

Whether the answer repeats a computed fact the question asked for (日主, 起运日期, 首步大运) is
recorded as a warning, not a rejection. 喜用神 and 补五行 advice are allowed as traditional
inference; the prompts ask for them to be argued from the computed chart.
"""

import re

from common.output_policy import warn

GANZHI = r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]"
PILLAR = re.compile(
    rf"(候选)?(流年(?:年?柱)?|(?:节气)?流月(?:月?柱)?|流日(?:日?柱)?|流时(?:时?柱)?|[年月日时]柱)"
    rf"\s*(?:是|为|：|:)?\s*({GANZHI})"
)
SCOPES = re.compile(r"原局|本命|出生|你(?:的)?|流年|流月|流日|流时|流期|period:")
KEYS = {"年": "year", "月": "month", "日": "day", "时": "time"}


def reading_parts(reading):
    """Keep field and clause boundaries: a flow label must not change another field's scope."""
    for field in ("summary", "closing"):
        yield field, getattr(reading, field)
    for index, section in enumerate(reading.sections):
        yield f"sections.{index}", section.title + "\n" + section.body
    for field in ("advice", "resonances", "followups"):
        for index, value in enumerate(getattr(reading, field)):
            yield f"{field}.{index}", value
    for index, item in enumerate(reading.evidence):
        yield f"evidence.{index}.reading", item.reading
    for index, item in enumerate(reading.timeline):
        yield f"timeline.{index}", item.period + "\n" + item.note
    for index, item in enumerate(reading.tensions):
        yield f"tensions.{index}.theme", item.theme
        yield f"tensions.{index}.how_to_read", item.how_to_read
        for side, value in enumerate(item.sides):
            yield f"tensions.{index}.sides.{side}", value
    yield "confidence.reason", reading.confidence.reason
    yield "safety.note", reading.safety.note


def pillar_error(text, bazi, periods):
    previous_end = 0
    for match in PILLAR.finditer(text):
        candidate, label, value = match.groups()
        name = next(name for name in KEYS if name in label)
        key = KEYS[name]
        # The nearest explicit scope in this clause wins, including a later 原局 marker.
        prefix = re.split(r"[。！？；;\n]", text[previous_end : match.start()])[-1]
        previous_end = match.end()
        scopes = SCOPES.findall(prefix)
        scope = scopes[-1] if scopes else ""
        temporal = "流" in label or scope in ("流年", "流月", "流日", "流时", "流期", "period:")
        if temporal:
            expected = {p["pillars"][key] for p in periods if key in p["pillars"]}
            if value not in expected:
                return f"流期柱位与干支不符：{label}{value}；本次{label}可用值为{'、'.join(sorted(expected)) or '无，请先计算对应流期'}"
            continue
        if candidate and any(c.get(key) == value for c in bazi.get("alternatives", [])):
            continue
        expected = bazi.get("pillars", {}).get(key)
        if key == "time" and bazi and not bazi.get("time_known"):
            return "出生时辰未知，禁止编造时柱"
        if expected != value:
            return f"原局柱位与干支不符：{name}柱写成{value}，本次原局{name}柱应为{expected or '未知'}；流期干支须明确标注流年、流月、流日或流时"
    return None


def validate_output(reading, state):
    parts = list(reading_parts(reading))
    text = " ".join(value for _, value in parts)
    daily = state.get("daily_result") or {}
    bazi = state.get("bazi_result") or daily.get("bazi") or {}
    question = state.get("question", "")
    if bazi:
        if "日主" in question and bazi.get("day_master") and bazi["day_master"] not in text:
            warn(state, "原问题要求说明日主，回答中没有写出")
        dayun = bazi.get("dayun")
        if state.get("response_mode") != "followup" and re.search(
            r"起运日期|起运时间|什么时候.*(?:起运|走大运)|何时.*(?:起运|走大运)", question
        ):
            if dayun:
                date = dayun["start_solar"]
                year, month, day = map(int, date.split("-"))
                if date not in text and f"{year}年{month}月{day}日" not in text:
                    warn(state, "原问题要求起运日期，回答中没有写出计算出的日期")
            elif not re.search(r"未提供|未知|无法|不能|不排", text):
                warn(state, "无法排大运时宜说明原因")
        if (
            state.get("response_mode") != "followup"
            and re.search(r"首步大运|首运|第一步大运", question)
            and dayun
            and dayun["sequence"][0]["ganzhi"] not in text
        ):
            warn(state, "原问题要求首步大运，回答中没有写出")
    periods = list((state.get("bazi_period_result") or {}).get("periods", []))
    periods.extend(
        {"pillars": {"day": segment["pillar"]}}
        for segment in (daily.get("day") or {}).get("segments", [])
    )
    gz = set(g for g in bazi.get("pillars", {}).values() if g)
    for candidate in bazi.get("alternatives", []):
        gz.update(candidate.values())
    gz.update(d["ganzhi"] for d in (bazi.get("dayun") or {}).get("sequence", []))
    for p in periods:
        gz.update(p["pillars"].values())
    gz.update(segment["pillar"] for segment in (daily.get("day") or {}).get("segments", []))
    for field, value in parts:
        for ganzhi in re.findall(GANZHI, value):
            if ganzhi not in gz:
                return f"{field}：本次工具结果没有该干支（{ganzhi}），不能编造"
        error = pillar_error(value, bazi, periods)
        if error:
            return f"{field}：{error}"
    return None
