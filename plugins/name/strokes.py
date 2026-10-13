"""Kangxi stroke counts for the five-grid (五格) convention, from Unicode Unihan 18.0.

Rule (same as evals/generators/gen_names.py, so the dataset answer is the implementation
contract): traditional form (surname conventions override Unihan) → first kRSUnicode value
(a restoring radical is preferred when several exist) → original radical strokes + residual
strokes. 氵 counts as 水 (4), 扌 as 手 (4), 艹 as 艸 (6), 辶 as 辵 (7), left 阝 as 阜 (8),
right 阝 as 邑 (7), 王 as 玉 (5) automatically, because the radical number is that of the
original character. Numerals 一 to 十 count by value.

A character with more than one accepted written form returns the default plus every
alternative and is flagged for confirmation; an unknown character is never guessed.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

UNIHAN = Path(__file__).resolve().parents[2] / "data/unihan"
FIELDS = ("kRSUnicode", "kTraditionalVariant", "kTotalStrokes")
RULE_VERSION = "kangxi-strokes-v1"
NUMERALS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
# Radicals whose original-character strokes differ from the written component; when Unihan
# lists several radical assignments, the restoring one follows Kangxi dictionary practice.
RESTORING = {140, 162, 170, 163, 85, 64, 61, 94, 113, 145, 130, 96}
# Surname spellings that differ from generic simplified→traditional conversion.
SURNAME_FORMS = {
    "于": ("于", "姓氏“于”不转写为“於”"),
    "余": ("余", "姓氏“余”不转写为“餘”"),
    "范": ("范", "姓氏“范”不转写为“範”"),
    "姜": ("姜", "姓氏“姜”不转写为“薑”"),
    "钟": ("鍾", "姓氏多写作“鍾”，而不是“鐘”"),
    "肖": ("肖", "大陆证件多写“肖”；港台多写“蕭”"),
    "叶": ("葉", "姓氏“叶”繁体为“葉”"),
    "胡": ("胡", "姓氏“胡”不转写为“衚”“鬍”"),
    "朱": ("朱", "姓氏“朱”不转写为“硃”"),
    "沈": ("沈", "姓氏“沈”不转写为“瀋”"),
    "向": ("向", "姓氏“向”不转写为“嚮”“曏”"),
    "苏": ("蘇", "姓氏“苏”繁体为“蘇”，不是“囌”"),
    "万": ("萬", "姓氏“万”繁体多写“萬”；复姓“万俟”保留“万”"),
}
GIVEN_FORMS = {"郁": ("郁", "名字中“郁”多为本字，简繁转换会误映射到“鬱”")}
# Week 6 finalisation of the 19 needs_review characters: the default stays the dataset
# answer; these characters also expose real alternative spellings and ask for confirmation.
ALTERNATIVES = {
    ("surname", "肖"): ("蕭",),
    ("surname", "万"): ("万",),
    ("surname", "钟"): ("鐘",),
    ("given", "丽"): ("丽",),
    ("given", "强"): ("强",),
    ("given", "艳"): ("豔",),
    ("given", "杰"): ("杰",),
    ("given", "郁"): ("鬱",),
    ("given", "胜"): ("胜",),
}


class UnihanMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class Unihan:
    rs: dict[str, str]
    traditional: dict[str, str]
    total: dict[str, str]


def _load(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        codepoint, value = line.split("\t", 1)
        if ".." in codepoint:
            first, last = (int(x, 16) for x in codepoint.split(".."))
            for code in range(first, last + 1):
                values[chr(code)] = value
        else:
            values[chr(int(codepoint, 16))] = value
    return values


@lru_cache(maxsize=2)
def unihan(directory: Path = UNIHAN) -> Unihan:
    paths = [directory / f"{field}.txt" for field in FIELDS]
    if not all(path.is_file() for path in paths):
        raise UnihanMissing("缺少Unihan数据，请先运行 python -m scripts.fetch_data")
    return Unihan(*(_load(path) for path in paths))


def radical_strokes(number: int) -> int:
    for last, strokes in (
        (6, 1), (29, 2), (60, 3), (94, 4), (117, 5), (146, 6), (166, 7), (175, 8), (186, 9),
        (194, 10), (200, 11), (204, 12), (208, 13), (210, 14), (211, 15), (213, 16), (214, 17),
    ):  # fmt: skip
        if number <= last:
            return strokes
    raise ValueError("radical out of range")


def radical_char(number: int) -> str:
    return unicodedata.normalize("NFKC", chr(0x2F00 + number - 1))


def form_strokes(form: str, data: Unihan) -> dict | None:
    """Kangxi strokes of one written form, or None when Unihan has no radical data."""
    values = data.rs.get(form, "").split()
    if not values:
        return None

    def parse(value):
        radical, residual = value.split(".")
        return int(radical.replace("'", "")), int(residual), "'" in radical

    chosen = values[0]
    if len(values) > 1:
        restoring = [v for v in values if parse(v)[0] in RESTORING]
        chosen = restoring[0] if restoring else values[0]
    radical, residual, simplified = parse(chosen)
    strokes = radical_strokes(radical) + residual
    return dict(
        form=form,
        strokes=strokes,
        rs=chosen,
        radical=radical_char(radical),
        radical_number=radical,
        radical_strokes=radical_strokes(radical),
        residual=residual,
        simplified_radical=simplified,
        modern_strokes=int(data.total[form].split()[0]) if form in data.total else None,
        other_rs={v: radical_strokes(parse(v)[0]) + parse(v)[1] for v in values if v != chosen},
    )


def char_strokes(char: str, role: str, chosen_form: str | None = None, data=None) -> dict:
    """Default (or user-confirmed) written form, its strokes and any alternatives."""
    if role not in ("surname", "given"):
        raise ValueError("role must be surname or given")
    data = data or unihan()
    notes, rules = [], []
    if role == "surname" and char in SURNAME_FORMS:
        default, why = SURNAME_FORMS[char]
        rules.append("姓氏繁体惯例")
        notes.append(why)
    elif role == "given" and char in GIVEN_FORMS:
        default, why = GIVEN_FORMS[char]
        rules.append("名字用字惯例")
        notes.append(why)
    else:
        variants = [chr(int(x[2:], 16)) for x in data.traditional.get(char, "").split()]
        others = [v for v in variants if v != char]
        default = others[0] if others else char
    alternatives = list(ALTERNATIVES.get((role, char), ()))
    if role == "given" and char not in GIVEN_FORMS:
        variants = [chr(int(x[2:], 16)) for x in data.traditional.get(char, "").split()]
        alternatives += [v for v in variants if v not in (char, default)]
    alternatives = [a for a in dict.fromkeys(alternatives) if a != default]
    base = form_strokes(default, data)
    if base is None or base["simplified_radical"]:
        return dict(char=char, role=role, status="unknown", notes=["Unihan没有该字的康熙部首数据"])
    if len(set(base["other_rs"].values()) | {base["strokes"]}) > 1:
        notes.append("Unihan给出多个部首归属，按康熙字典习惯取" + base["rs"])
    options = [dict(form=default, strokes=base["strokes"], default=True)]
    for form in alternatives:
        other = form_strokes(form, data)
        if other and not other["simplified_radical"]:
            options.append(dict(form=form, strokes=other["strokes"], default=False))
    if char in NUMERALS:
        rules.append(f"数字按数值计：{NUMERALS[char]}")
        for option in options:
            option["strokes"] = NUMERALS[char]
    selected = options[0]
    if chosen_form is not None:
        selected = next((o for o in options if o["form"] == chosen_form), None)
        if selected is None:
            raise ValueError(f"「{char}」没有写法「{chosen_form}」")
    detail = form_strokes(selected["form"], data)
    rules.append(
        f"部首还原：{detail['radical']}（第{detail['radical_number']}部，"
        f"{detail['radical_strokes']}画）+ 余笔{detail['residual']}"
    )
    distinct = {o["strokes"] for o in options}
    return dict(
        char=char,
        role=role,
        status="ok",
        form=selected["form"],
        strokes=selected["strokes"],
        default_form=default,
        confirmed=chosen_form is not None,
        alternatives=[o for o in options if o["form"] != selected["form"]],
        needs_confirmation=chosen_form is None and len(distinct) > 1,
        rules=rules,
        notes=notes,
        modern_strokes=detail["modern_strokes"],
    )
