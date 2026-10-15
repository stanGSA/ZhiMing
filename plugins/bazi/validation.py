"""Bazi output checks: every 干支 and pillar must come from this reading's calculations.

Whether the answer repeats a computed fact the question asked for (日主, 起运日期, 首步大运) is
recorded as a warning, not a rejection. 喜用神 and 补五行 advice are allowed as traditional
inference; the prompts ask for them to be argued from the computed chart.
"""

import re

from common.facts import section_texts
from common.output_policy import warn


def validate_output(reading, state):
    text = " ".join(
        [
            reading.summary,
            *section_texts(reading),
            *[e.reading for e in reading.evidence],
            *reading.advice,
            reading.closing,
            *[t.period + " " + t.note for t in reading.timeline],
            *reading.resonances,
            *[t.how_to_read for t in reading.tensions],
            *[side for t in reading.tensions for side in t.sides],
            *reading.followups,
            reading.safety.note,
        ]
    )
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
    periods = (state.get("bazi_period_result") or {}).get("periods", [])
    gz = set(g for g in bazi.get("pillars", {}).values() if g)
    for candidate in bazi.get("alternatives", []):
        gz.update(candidate.values())
    gz.update(d["ganzhi"] for d in (bazi.get("dayun") or {}).get("sequence", []))
    for p in periods:
        gz.update(p["pillars"].values())
    gz.update(segment["pillar"] for segment in (daily.get("day") or {}).get("segments", []))
    for value in re.findall(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", text):
        if value not in gz:
            return "本次工具结果没有该干支，不能编造"
    for candidate_label, name, value in re.findall(
        r"(候选)?([年月日时])柱\s*(?:是|为|：|:)?\s*([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])",
        text,
    ):
        key = {"年": "year", "月": "month", "日": "day", "时": "time"}[name]
        if candidate_label and any(c.get(key) == value for c in bazi.get("alternatives", [])):
            continue
        if (
            bazi.get("pillars", {}).get(
                {"年": "year", "月": "month", "日": "day", "时": "time"}[name]
            )
            != value
        ):
            return "原局柱位与干支不符"
    if (
        bazi
        and not bazi.get("time_known")
        and re.search(r"时柱(?:是|为|：|:|\s*[甲乙丙丁戊己庚辛壬癸])", text)
    ):
        return "出生时辰未知，禁止编造时柱"
    return None
