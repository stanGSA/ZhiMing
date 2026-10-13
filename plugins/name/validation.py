"""Name output checks: every grid number, stroke count and 三才 claim must be computed."""

import re

GRID = re.compile(
    r"(天格|人格|地格|外格|总格)(?:数理|数)?\s*(?:为|是|=|：|:|得|共)?\s*(\d{1,3})(?!\d)"
)
STROKE = re.compile(
    r"[「“\"《【]?([㐀-鿿])[」”\"》】]?(?:字)?\s*(?:按|为|是|计|算|作|有|共)?\s*(?:康熙)?(?:笔画)?\s*(\d{1,2})\s*画"
)
SANCAI = re.compile(r"三才(?:配置|组合|五行)?\s*(?:为|是|：|:)?\s*[「“【]?([木火土金水]{3})")
USEFUL_GOD = re.compile(
    r"喜用神(?:是|为)|(?:需要|应该|应当|建议|宜|要)(?:补|增加|加强)[木火土金水]|五行缺[木火土金水]"
)
FATALISM = re.compile(
    r"(?:注定|一定会|必然|必定)(?:会)?(?:失败|不幸|短命|破财|离婚|成功|富贵|发财)"
)


def text_of(reading):
    return " ".join(
        [
            reading.summary,
            *[e.reading for e in reading.evidence],
            *reading.advice,
            *reading.resonances,
            *[t.how_to_read for t in reading.tensions],
            *[side for t in reading.tensions for side in t.sides],
            *reading.followups,
            reading.safety.note,
        ]
    )


def name_results(state):
    return [v for k, v in (state.get("calculations") or {}).items() if k.startswith("name_result:")]


def validate_output(reading, state):
    results = name_results(state)
    text = text_of(reading)
    if not results:
        if "name" in reading.systems_used and GRID.search(text):
            return "本记录没有姓名计算，不能给出五格数值"
        return None
    for grid, number in GRID.findall(text):
        if not any(
            r["grids"][grid] == int(number) or r["shuli"][grid] == int(number) for r in results
        ):
            return f"{grid}{number}与本次姓名计算不符"
    chars = {}
    for result in results:
        for char in result["chars"]:
            values = {char["strokes"], *(a["strokes"] for a in char["alternatives"])}
            for key in (char["char"], char["form"], *(a["form"] for a in char["alternatives"])):
                chars.setdefault(key, set()).update(values)
    for char, number in STROKE.findall(text):
        if char in chars and int(number) not in chars[char]:
            return f"“{char}”的笔画与本次计算不符"
    keys = {r["sancai"]["key"] for r in results}
    for key in SANCAI.findall(text):
        if key not in keys:
            return "三才配置与本次计算不符"
    if USEFUL_GOD.search(text):
        return "MVP不判喜用神，不能据五行建议改名或补五行"
    if FATALISM.search(text):
        return "姓名数理是民间约定，不能作命运断言"
    pending = [a["char"] for r in results for a in r["ambiguities"]]
    for char in pending:
        if char in text and not re.search(r"写法|繁体|异体|两种|备选|另一种|确认", text):
            return f"“{char}”有多种写法，须说明默认写法并提示确认"
    return None
