"""Five-grid (五格剖象法) numbers and the three-talent (三才) configuration.

天格 = 单姓笔画 + 1（复姓为两字之和）；人格 = 姓末字 + 名首字；地格 = 单名 + 1（多字名为各字之和）；
外格 = 天格 + 地格 − 人格（单姓单名为 2，与“假数”约定一致）；总格 = 全名笔画之和（不加假数）。
数理超过 81 时按惯例减 80 循环。三才取天、人、地格尾数：1、2 木，3、4 火，5、6 土，7、8 金，9、0 水。
"""

from __future__ import annotations

import hashlib
import json

from plugins.name.strokes import RULE_VERSION, char_strokes

ELEMENTS = ("木", "火", "土", "金", "水")
GENERATES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
GRIDS = ("天格", "人格", "地格", "外格", "总格")
# Common Chinese compound surnames; any other two-character surname needs user confirmation.
COMPOUND_SURNAMES = frozenset(
    "欧阳 司马 上官 诸葛 东方 皇甫 尉迟 公孙 慕容 长孙 宇文 司徒 夏侯 轩辕 令狐 端木 澹台 万俟 "
    "呼延 南宫 独孤 百里 西门 申屠 闻人 赫连 钟离 太史 东郭 公冶 宗政 濮阳 淳于 单于 太叔 "
    "仲孙 左丘 拓跋 鲜于 闾丘 司空 亓官 司寇 子车 颛孙 壤驷 公良 漆雕 乐正 宰父 谷梁 第五".split()
)


def element(number: int) -> str:
    return ELEMENTS[((number - 1) % 10) // 2]


def shuli(number: int) -> int:
    while number > 81:
        number -= 80
    return number


def relation(source: str, target: str) -> str:
    """Relation of source to target: 生 (source feeds target), 被生, 克, 被克 or 同."""
    if source == target:
        return "同"
    if GENERATES[source] == target:
        return "生"
    if GENERATES[target] == source:
        return "被生"
    return "克" if CONTROLS[source] == target else "被克"


def grids(surname: list[int], given: list[int]) -> dict[str, int]:
    heaven = surname[0] + 1 if len(surname) == 1 else sum(surname)
    person = surname[-1] + given[0]
    earth = given[0] + 1 if len(given) == 1 else sum(given)
    return {
        "天格": heaven,
        "人格": person,
        "地格": earth,
        "外格": heaven + earth - person,
        "总格": sum(surname) + sum(given),
    }


def analyze(surname: str, given: str, forms: dict[str, str] | None = None) -> dict:
    """Deterministic analysis; characters without Kangxi data are returned, never guessed."""
    forms = forms or {}
    chars = []
    for role, text in (("surname", surname), ("given", given)):
        for char in text:
            chars.append(char_strokes(char, role, forms.get(char)))
    unknown = [c["char"] for c in chars if c["status"] != "ok"]
    if unknown:
        return dict(status="unknown_chars", unknown=unknown, chars=chars)
    numbers = grids(
        [c["strokes"] for c in chars if c["role"] == "surname"],
        [c["strokes"] for c in chars if c["role"] == "given"],
    )
    sancai = "".join(element(numbers[g]) for g in ("天格", "人格", "地格"))
    payload = json.dumps([RULE_VERSION, surname, given, sorted(forms.items())], ensure_ascii=False)
    return dict(
        status="ok",
        name_id="nm" + hashlib.sha256(payload.encode()).hexdigest()[:12],
        surname=surname,
        given=given,
        full_name=surname + given,
        compound_surname=len(surname) == 2,
        chars=chars,
        grids=numbers,
        shuli={g: shuli(n) for g, n in numbers.items()},
        sancai=dict(
            key=sancai,
            elements=dict(zip(("天格", "人格", "地格"), sancai, strict=True)),
            heaven_to_person=relation(sancai[0], sancai[1]),
            person_to_earth=relation(sancai[1], sancai[2]),
        ),
        ambiguities=[
            dict(
                char=c["char"],
                default=dict(form=c["form"], strokes=c["strokes"]),
                alternatives=c["alternatives"],
                notes=c["notes"],
            )
            for c in chars
            if c["needs_confirmation"]
        ],
        conventions=dict(
            strokes="康熙笔画：繁体字形，部首按原字计（氵4、扌4、艹6、辶7、左阝8、右阝7、王5），数字按数值",
            heaven="单姓加假数1；复姓两字相加",
            earth="单名加假数1；多字名各字相加",
            outer="外格=天格+地格−人格",
            total="总格=全名实际笔画之和",
            over_81="数理超过81减80",
            sancai="天人地格尾数定五行：12木34火56土78金90水",
            school="五格剖象法属民间约定，数理吉凶各家有分歧，只作自我反思参考",
            rule_version=RULE_VERSION,
        ),
    )
