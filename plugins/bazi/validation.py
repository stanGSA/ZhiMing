"""Bazi output checks: every 干支 and pillar must come from this reading's calculations.

Whether the answer repeats a computed fact the question asked for (日主, 起运日期, 首步大运) is
recorded as a warning, not a rejection. 喜用神 and 补五行 advice are allowed as traditional
inference; the prompts ask for them to be argued from the computed chart.
"""

import re

from common.evidence import calculation_evidence_texts
from common.facts import section_texts
from common.output_policy import warn
from harness.models import ValidationMessage

PILLAR_KEYS = {"年": "year", "月": "month", "日": "day", "时": "time"}
PILLAR_CLAIM = re.compile(
    r"(?:(?P<flow>流[年月日时])(?:的?(?P<flow_name>[年月日时])?柱)?|"
    r"(?:(?:今年|明年|去年|当年|该年)的?(?P<temporal_y>年)柱|"
    r"(?:本月|下月|这个月|下个月|当月|该月)的?(?P<temporal_m>月)柱|"
    r"(?:今天|今日|明天|明日|当日|当天)的?(?P<temporal_d>日)柱)|"
    r"(?P<scope>候选|原局|本命|出生|流期)?(?:的)?(?P<name>[年月日时])柱)"
    r"\s*(?:是|为|：|:)?\s*(?P<value>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)


def validate_output(reading, state):
    parts = [
        reading.summary,
        *section_texts(reading),
        *reading.advice,
        reading.closing,
        *[t.period + " " + t.note for t in reading.timeline],
        *reading.resonances,
        *[t.how_to_read for t in reading.tensions],
        *[side for t in reading.tensions for side in t.sides],
        *[t.theme for t in reading.tensions],
        *reading.followups,
        reading.confidence.reason,
        reading.safety.note,
    ]
    text = " ".join([*parts, *[e.reading for e in reading.evidence]])
    # Exact facts rendered from a matching calculation reference already have a known
    # scope. In particular, period:...:年柱:丁未 is a flow year, not a natal year.
    # A reference alone never exempts model-authored or altered evidence from checks.
    canonical = calculation_evidence_texts(state)
    claims = [
        *parts,
        *[e.reading for e in reading.evidence if canonical.get(e.ref_id) != e.reading],
    ]
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
    comparisons = {
        result["scope"]: result
        for result in state.get("calculations", {}).values()
        if result.get("scope") in ("dayun_first", "dayun_current")
    }
    comparisons.update(state.get("bazi_comparison_results", {}))
    periods = (state.get("bazi_period_result") or {}).get("periods", [])
    periods = [
        *periods,
        *[p for result in comparisons.values() for p in result.get("periods", [])],
    ]
    gz = set(g for g in bazi.get("pillars", {}).values() if g)
    for candidate in bazi.get("alternatives", []):
        gz.update(candidate.values())
    gz.update(d["ganzhi"] for d in (bazi.get("dayun") or {}).get("sequence", []))
    for p in periods:
        gz.update(p["pillars"].values())
    gz.update(segment["pillar"] for segment in (daily.get("day") or {}).get("segments", []))
    for value in re.findall(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]", text):
        if value not in gz:
            return ValidationMessage(
                f"本次工具结果没有该干支，不能编造（冲突片段：“{value}”）",
                retry_key=f"unknown_ganzhi:{value}",
            )
    # The daily fortune's day pillars are flow days as well.
    flows = [
        *periods,
        *({"pillars": {"day": s["pillar"]}} for s in (daily.get("day") or {}).get("segments", [])),
    ]
    for passage in claims:
        for match in PILLAR_CLAIM.finditer(passage):
            flow = match.group("flow")
            temporal = (
                match.group("temporal_y") or match.group("temporal_m") or match.group("temporal_d")
            )
            scope, name, value = match.group("scope", "name", "value")
            pillar_char = flow[-1] if flow else (temporal or name)
            key = PILLAR_KEYS[pillar_char]
            if flow or temporal or scope == "流期":
                if (flow and match["flow_name"] not in (None, flow[-1])) or not any(
                    p["pillars"].get(key) == value for p in flows
                ):
                    return ValidationMessage(
                        f"流期柱位与干支不符，请使用本次对应流年、流月或流日的计算结果（冲突片段：“{match.group(0)}”）",
                        retry_key=f"flow_pillar:{key}:{value}",
                    )
            elif scope == "候选" and any(c.get(key) == value for c in bazi.get("alternatives", [])):
                continue
            elif bazi.get("pillars", {}).get(key) != value:
                return ValidationMessage(
                    f"原局柱位与干支不符，请区分出生原局与流年、流月、流日（冲突片段：“{match.group(0)}”）",
                    retry_key=f"natal_pillar:{key}:{value}",
                )
    if (
        bazi
        and not bazi.get("time_known")
        and any(re.search(r"时柱(?:是|为|：|:|\s*[甲乙丙丁戊己庚辛壬癸])", p) for p in claims)
    ):
        return ValidationMessage("出生时辰未知，禁止编造时柱", retry_key="unknown_time_pillar")
    return None
