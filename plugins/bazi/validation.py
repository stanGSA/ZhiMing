import re


def validate_output(reading, state):
    text = " ".join(
        [
            reading.summary,
            *[e.reading for e in reading.evidence],
            *reading.advice,
            *[t.period + " " + t.note for t in reading.timeline],
            *reading.resonances,
            *[t.how_to_read for t in reading.tensions],
            *[side for t in reading.tensions for side in t.sides],
            *reading.followups,
            reading.safety.note,
        ]
    )
    bazi = state.get("bazi_result") or {}
    question = state.get("question", "")
    if bazi:
        if "日主" in question and bazi.get("day_master") and bazi["day_master"] not in text:
            return "原问题要求说明日主，最终回答不能遗漏"
        dayun = bazi.get("dayun")
        if state.get("response_mode") != "followup" and re.search(
            r"起运日期|起运时间|什么时候.*(?:起运|走大运)|何时.*(?:起运|走大运)", question
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
    return None
