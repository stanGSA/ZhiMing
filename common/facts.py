import re

from plugins.astro.calculator import BODY_ZH, SIGN_ZH


def validate_calculation_facts(reading, state):
    text = " ".join(
        [
            reading.summary,
            *[e.reading for e in reading.evidence],
            *reading.advice,
            *[t.note for t in reading.timeline],
        ]
    )
    natal = state.get("natal_result") or {}
    bazi = state.get("bazi_result") or {}
    question = state.get("question", "")
    if bazi:
        if "日主" in question and bazi.get("day_master") and bazi["day_master"] not in text:
            return "原问题要求说明日主，最终回答不能遗漏"
        dayun = bazi.get("dayun")
        if state.get("response_mode") != "followup" and re.search(
            r"起运日期|起运时间|什么时候起运", question
        ):
            if dayun:
                date = dayun["start_solar"]
                year, month, day = map(int, date.split("-"))
                if date not in text and f"{year}年{month}月{day}日" not in text:
                    return "原问题要求起运日期，须准确说明计算出的日期"
            elif not re.search(r"未提供|未知|无法|不能|不排", text):
                return "无法排大运时须明确原因"
        if (
            state.get("response_mode") != "followup"
            and re.search(r"首步大运|首运|第一步大运", question)
            and dayun
            and dayun["sequence"][0]["ganzhi"] not in text
        ):
            return "原问题要求首步大运，最终回答不能遗漏"
    periods = (state.get("bazi_period_result") or {}).get("periods", [])
    gz = set(g for g in bazi.get("pillars", {}).values() if g)
    for candidate in bazi.get("alternatives", []):
        gz.update(candidate.values())
    gz.update(d["ganzhi"] for d in (bazi.get("dayun") or {}).get("sequence", []))
    for p in periods:
        gz.update(p["pillars"].values())
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
    if bazi and re.search(
        r"(?:喜用神|用神)(?:是|为|：|:)|(?:喜|忌)[木火土金水].{0,5}(?:补|佩戴|颜色)", text
    ):
        return "MVP不下喜用神结论"
    positions = {p["body_zh"]: p for p in natal.get("planets", [])}
    planet_pattern = "|".join(BODY_ZH.values()) + "|上升|天顶|下降|天底"
    sign_pattern = "|".join(SIGN_ZH)
    for body, sign in re.findall(
        rf"({planet_pattern})\s*(?:落在|位于|在|落入|落|为|是)?\s*({sign_pattern})(?:座)?", text
    ):
        if body in positions:
            if positions[body]["sign_zh"] != sign:
                return "行星落座与本次计算不符"
        elif body in ("上升", "天顶", "下降", "天底"):
            axes = natal.get("axes")
            key = {"上升": "asc", "天顶": "mc", "下降": "dsc", "天底": "ic"}[body]
            if axes is None or SIGN_ZH[int(axes[key] // 30)] != sign:
                return "四轴不可用或与本次计算不符"
        else:
            return "没有占星计算，不能编造行星落座"
    for body, house in re.findall(
        rf"({planet_pattern})\s*(?:落在|位于|在|落入)?\s*(?:(?:{sign_pattern})(?:座)?\s*)?第?([0-9]+)宫",
        text,
    ):
        if body not in positions or positions[body]["house"] != int(house):
            return "宫位不可用或与本次计算不符"
    if (
        natal
        and not natal.get("time_known")
        and re.search(
            r"(?:上升|天顶)(?:星座)?(?:是|为|：|:)\s*\S|(?:第\d+宫)(?:说明|代表|表明)", text
        )
    ):
        return "出生时间未知，不能使用宫位或四轴解读"
    if state.get("response_mode") != "followup":
        temporal = {s["system"] for s in state["signals"] if s["horizon"] == "short_term"}
        q = state.get("question", "")
        if reading.question_type == "timing" or re.search(
            r"下个月|本月|今年|明年|时机|什么时候|\d{4}-\d{2}-\d{2}\s*(?:至|到)\s*\d{4}-\d{2}", q
        ):
            for system in set(reading.systems_used) & {"astro", "bazi"}:
                if system not in temporal:
                    return "时间范围问题需要相应行运或流期计算，不能只用原局"
    return None
