"""Name output checks.

Every grid number, 三才 configuration and stroke count is bound to one analysed name: the
evidence ref names it, or the nearest full name written before the claim in the same field.
With several names, a claim that cannot be bound is rejected rather than checked against the
union of all names. An unconfirmed written form must be explained wherever its name was
analysed, whether or not the answer mentions the character.
"""

import re

from common.facts import public_texts, rendered_texts

GRID = re.compile(
    r"(天格|人格|地格|外格|总格)(?:数理|数)?\s*(?:为|是|=|：|:|得|共)?\s*(\d{1,3})(?!\d)"
)
STROKE = re.compile(
    r"[「“\"《【]?([㐀-鿿])[」”\"》】]?(?:字)?\s*(?:按|为|是|计|算|作|有|共)?\s*(?:康熙)?(?:笔画)?\s*(\d{1,2})\s*画"
)
SANCAI = re.compile(r"三才(?:配置|组合|五行)?\s*(?:为|是|：|:)?\s*[「“【]?([木火土金水]{3})")
FATALISM = re.compile(
    r"(?:注定|一定会|必然|必定)(?:会)?(?:失败|不幸|短命|破财|离婚|成功|富贵|发财)"
)


def name_results(state) -> dict:
    return {
        v["name_id"]: v
        for k, v in (state.get("calculations") or {}).items()
        if k.startswith("name_result:")
    }


def stroke_options(result) -> dict[str, set[int]]:
    """Allowed counts per written character of one name.

    The character as typed may stand for any of its forms (杰 → 傑12 or 杰8); a distinct form
    allows only its own count (傑 is 12, never 8).
    """
    options = {}
    for char in result["chars"]:
        forms = [(char["form"], char["strokes"])] + [
            (a["form"], a["strokes"]) for a in char["alternatives"]
        ]
        options.setdefault(char["char"], set()).update(n for _, n in forms)
        for form, strokes in forms:
            if form != char["char"]:
                options.setdefault(form, set()).add(strokes)
    return options


def check_claims(text, bound, results):
    """Check one field; claims bind to the last full name written before them."""
    names = sorted(
        ((m.start(), r) for r in results.values() for m in re.finditer(r["full_name"], text)),
        key=lambda item: item[0],
    )

    def owner(position):
        before = [r for start, r in names if start <= position]
        return before[-1] if before else bound

    for match in GRID.finditer(text):
        result = owner(match.start())
        grid, number = match.group(1), int(match.group(2))
        if result is None:
            return f"有多个姓名时，{grid}{number}须写明是哪个名字"
        if number not in (result["grids"][grid], result["shuli"][grid]):
            return f"{result['full_name']}的{grid}{number}与本次计算不符"
    for match in SANCAI.finditer(text):
        result = owner(match.start())
        if result is None:
            return "有多个姓名时，三才配置须写明是哪个名字"
        if match.group(1) != result["sancai"]["key"]:
            return f"{result['full_name']}的三才配置与本次计算不符"
    for match in STROKE.finditer(text):
        char, number = match.group(1), int(match.group(2))
        result = owner(match.start())
        candidates = [result] if result is not None else list(results.values())
        known = [stroke_options(r)[char] for r in candidates if char in stroke_options(r)]
        if (
            result is not None
            and not known
            and any(char in stroke_options(r) for r in results.values())
        ):
            return f"“{char}”不属于{result['full_name']}，笔画不能串用"
        if known and not any(number in allowed for allowed in known):
            return f"“{char}”的笔画与本次计算不符"
    return None


def ambiguity_prompt(result, ambiguity) -> str:
    """A copyable, user-facing disclosure built from the calculated form/count pairs."""
    default = ambiguity["default"]
    alternatives = "、".join(f"{a['form']}{a['strokes']}画" for a in ambiguity["alternatives"])
    return (
        f"{result['full_name']}的“{ambiguity['char']}”默认按{default['form']}{default['strokes']}画，"
        f"备选写法为{alternatives}，请按证件写法确认。"
    )


def ambiguity_explained(texts, ambiguity) -> bool:
    """Require each written form with its own count and a still-pending confirmation."""
    forms = {ambiguity["char"], ambiguity["default"]["form"]}
    forms |= {a["form"] for a in ambiguity["alternatives"]}
    required = {
        (a["form"], a["strokes"]) for a in [ambiguity["default"], *ambiguity["alternatives"]]
    }
    for text in texts:
        for sentence in re.split(r"[。；;！!？?\n]", text):
            if not any(f in sentence for f in forms):
                continue
            pairs = {(char, int(count)) for char, count in STROKE.findall(sentence)}
            # '写原字为8画' explicitly refers to this character, not an unrelated number.
            original = re.findall(
                r"(?:原字|本字|简体)(?:为|是|按|计|算|作)?\s*(\d{1,2})\s*画", sentence
            )
            pairs.update((ambiguity["char"], int(n)) for n in original)
            default = ambiguity["default"]
            default_named = re.search(
                rf"默认(?:按|用|为|是)?(?:繁体|写法)?\s*[「“【《]?{re.escape(default['form'])}"
                rf"[」”】》]?\s*(?:为|是|按|计)?\s*{default['strokes']}\s*画",
                sentence,
            )
            pending = re.search(r"请.{0,12}确认|待.{0,6}确认|需要.{0,6}确认|须.{0,6}确认", sentence)
            already = re.search(r"已(?:经)?确认|确认过|确认好了", sentence)
            if required <= pairs and default_named and pending and not already:
                return True
    return False


def validate_output(reading, state):
    results = name_results(state)
    texts = public_texts(reading)
    joined = " ".join(texts)
    if not results:
        if "name" in reading.systems_used and GRID.search(joined):
            return "本记录没有姓名计算，不能给出五格数值"
        return None
    single = next(iter(results.values())) if len(results) == 1 else None
    fields = [(e.reading, e.ref_id) for e in reading.evidence]
    fields += [(text, None) for text in texts if text not in {e.reading for e in reading.evidence}]
    for text, ref in fields:
        bound = single
        if ref and ref.startswith("name:"):
            bound = results.get(ref.split(":")[1], bound)
        error = check_claims(text, bound, results)
        if error:
            return error
    if FATALISM.search(joined):
        return "姓名数理是民间约定，不能作命运断言"
    for result in results.values():
        for ambiguity in result["ambiguities"]:
            if not ambiguity_explained(rendered_texts(reading), ambiguity):
                options = "/".join(
                    f"{o['form']}{o['strokes']}画"
                    for o in [ambiguity["default"], *ambiguity["alternatives"]]
                )
                return (
                    f"{result['full_name']}的“{ambiguity['char']}”有多种写法（{options}），"
                    "须在用户可见的摘要、分析或建议中说明各字形笔画并请用户确认。可使用："
                    + ambiguity_prompt(result, ambiguity)
                )
    return None
