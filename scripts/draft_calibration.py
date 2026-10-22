"""Draft the labelled calibration set for the stage 1 second campaign (owner confirms, then freezes).

Drafted by Anthropic Claude on 2026-10-22 at the owner's request. Anthropic drafted the B1
directions and reviews nothing; this set never enters the knowledge base. Generation is
deterministic from the current sources, so the owner can rerun it and diff the result.

Two partitions per system: ``dev`` (20 items; daily 6) is reviewed in the pilot and may shape
the rubric; ``holdout`` (30 items; daily 18) is used once, in the pre-registered acceptance.
They share no source entry, except daily, which has only nine. Each partition holds:

- typical pass: a current entry chosen by the rule checks below, never by the 2026-10-21
  verdicts (choosing what models agreed on would inflate their agreement on this set);
- boundary pass: content that looks suspicious but the rubric accepts (a reversed card in its
  upright's direction, a legitimate synonym, a hidden-stem list in another order, ...);
- fail: another current entry with exactly one realistic defect, in the entries' own words.

Every label states the rule it rests on.

    python -m scripts.draft_calibration --output <校准集.yaml>
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
from pathlib import Path

import yaml
from lunar_python.util import LunarUtil

from knowledge.checks import certainty_finding
from knowledge.review import content_hash
from plugins.astro.calculator import BODY_ZH
from plugins.name.wuge import ELEMENTS, element
from scripts import model_review_kb as review
from scripts.draft_tarot import MAJOR_THEMES, SUIT_THEMES
from scripts.draft_week6 import DAY_COLORS, LUCKY, MIXED
from scripts.draft_week23 import DIGNITY, HOUSE_TEXT, HOUSE_THEME

SEED = 20261022
SYSTEMS = ("tarot", "astro", "bazi", "name", "dream", "daily")
# Items per label in each partition.
SIZES = dict(holdout=15, dev=10)
DAILY_SIZES = dict(holdout=9, dev=3)
THEME_ZH = dict(self="自我状态", career="事业", relationship="感情关系", finance="财务")
# Entries whose content still has a substantive or traditional dispute: no label is certain.
DISPUTED = {"kb:tarot:card:pentacles_four:reversed", "kb:name:sancai:火木水"}
# Anchor B: wording that states a direction (narrow) and wording that may hint at one (broad).
STATED = dict(
    self=r"自我|情绪|精力|心态|状态|自信|感受|内在",
    career=r"事业|职业|工作|任务|学业|职场",
    relationship=r"感情|关系|伴侣|亲密|人际|家庭|社群|同伴",
    finance=r"财务|金钱|收支|预算|消费",
)
HINTED = dict(
    self=STATED["self"] + r"|压力|心理|情感|休息|节奏|安全感|自我",
    career=STATED["career"] + r"|学习|项目|成果|职责|规范|竞争|责任|目标",
    relationship=STATED["relationship"] + r"|合作|相处|社交|团队|朋友|爱|情感|婚|恋|对方",
    finance=STATED["finance"] + r"|收入|资源|财|钱|价值|花费|开销",
)
PREDICTIONS = dict(
    tarot=(
        "抽到这张牌，预示近期会有一笔意外收入。",
        "这张牌出现时，往往预示一段新感情即将到来。",
        "它预示你很快会在工作上得到认可。",
    ),
    astro=(
        "这一配置预示你今年会迎来职位上的晋升。",
        "拥有这一配置的人，近期会遇到合适的伴侣。",
        "这一配置预示接下来几个月财运会明显好转。",
    ),
    bazi=(
        "命局中出现它，预示近两年会遇到贵人相助。",
        "有此组合的人，中年以后财运会明显上升。",
        "它出现在流年时，预示当年会有搬迁或换工作的变动。",
    ),
    name=("用这个数理的人，中年以后会财运亨通。", "这样的配置预示婚姻会比较美满。"),
    dream=(
        "梦到它预示近期会收到好消息。",
        "这个梦预示你很快会升职加薪。",
        "梦见它，往往预示家里将有喜事。",
        "这个梦预示近期会有一笔意外之财。",
    ),
)
OBJECTIVE = dict(
    sancai=("有这种三才配置的人，性格稳重、事业顺利。", "这种三才配置会让人一生较为顺利。"),
    shuli=("取用这一数理的人，往往人缘好、贵人多。", "名字里有这个数的人，做事容易成功。"),
)
# (dream key, alias, why it is not the same image): the dream anchor's own categories.
BAD_SYNONYMS = (
    ("医生", "护士", "不同人物：护士不是医生"),
    ("新郎", "新娘", "不同人物：新娘不是新郎"),
    ("图书馆", "书店", "不同场所：书店不是图书馆"),
    ("麒麟", "瑞兽", "上位泛称：瑞兽包含麒麟以外的神兽"),
    ("自杀", "想不开", "常见其他义项：想不开也常指一时纠结"),
    ("考试", "考场", "只是场所：考场不等于考试这件事"),
    ("杯子", "杯子碎了", "只是事件：杯子碎了是一个情节，不是杯子本身"),
    ("桥", "桥断了", "只是事件：桥断了是一个情节，不是桥本身"),
    ("星星", "流星", "不同事物：流星不是星星"),
    ("蜜蜂", "马蜂", "不同物种：马蜂不是蜜蜂"),
    ("狐狸", "狐狸精", "常见其他义项：狐狸精多指精怪或贬称"),
)
# Same image, other words (scripts.dream_alias_review "restore"): synonyms the rubric accepts.
GOOD_SYNONYMS = (
    ("剪头发", "理发"),
    ("坠落", "往下掉"),
    ("迷路", "走丢"),
    ("拥抱", "抱在一起"),
    ("地震", "地动山摇"),
    ("花", "花海"),
)
GENERIC = dict(
    hidden="在传统命理中，“藏干”指地支所对应的天干，具体按固定表列出。各藏干对应的十神需结合日主"
    "确定，不能仅凭藏干数量判断五行旺衰。这些是传统命理的分类规则，不代表对个人命运的确定判断。",
    branch="{key}是十二地支之一，属于传统干支体系的基本单位。地支的五行与藏干按传统表确定，五行"
    "数量不能直接决定旺衰。这些属性属于传统文化分类，不代表个人能力或生活结果的好坏。",
    relation="{key}是传统干支体系中的一种关系，需结合具体干支判断。它属于传统文化中的分类，不代表"
    "现实中的吉凶，也不能据此判断个人、事业、关系或财务的结果。",
)
STRONGER = {"入庙": "失势", "擢升": "落陷", "失势": "入庙", "落陷": "擢升"}
MODERN = ("Uranus", "Neptune", "Pluto")
# Bases kept for one recipe only (the position defects).
RESERVED = {"kb:tarot:position:three_card:1", "kb:tarot:position:decision:2"}
DISPUTED_NUMBERS = {27, 28, 40, 50, 71, 73, 75}
NEUTRAL_NOTE = "这一约定只作说明，不影响其他体系的判断。"
ANCHOR_OF = dict(
    unsupported_direction="锚点B",
    direction_contradicts_text="锚点B",
    prediction="锚点F",
    orientation_not_distinguished="塔罗规则：正逆位区分",
    position_mismatch="塔罗规则：牌位以 spread_positions 为准",
    dignity_wrong="锚点D：尊贵表",
    modern_planet_dignity="锚点D：现代行星不在尊贵表",
    house_topic_wrong="锚点D：十二宫主题",
    hidden_stems_wrong="锚点D：藏干表",
    branch_element_wrong="锚点D：地支五行",
    group_members_wrong="锚点D：三合三会",
    not_object_specific="锚点C",
    tail_digit_element_wrong="锚点D：尾数五行",
    shuli_level_wrong="锚点D：数理三档",
    sancai_relation_wrong="锚点D：五行生克",
    evaluation_as_fact="锚点E",
    synonym_not_same_image="解梦同义词锚点",
    color_wrong="锚点D：五行配色",
    luck_claim="每日运势规则：不暗示带来运气",
    nonzero_direction="每日运势规则：保持中性",
)


def conventional(entry: dict) -> set[str]:
    """Themes a direction may take by the system's convention (rubric reference facts)."""
    kind, key = entry["kind"], entry["key"]
    if entry["system"] == "tarot" and kind == "card":
        return set(SUIT_THEMES.get(key.split("_")[0], MAJOR_THEMES))
    if entry["system"] == "astro" and kind == "planet_house":
        house = key.split(":")[1]
        return {HOUSE_THEME[house]} if house in HOUSE_THEME else set()
    if entry["system"] == "bazi" and kind in ("ten_god", "god_pillar"):
        return {"self", "career"}
    if entry["system"] == "name" and kind == "shuli":
        return set(THEME_ZH)
    if entry["system"] == "name" and kind == "sancai":
        return {"self", "relationship", "career"}
    return set()


def predicts(text: str) -> bool:
    plain = re.sub(r"(?:不|并不|也不|不会|不能|未)(?:预示|预测)", "", text)
    return bool(re.search(r"预示|将会|近期会|很快会|必将", plain))


def listed_stems(entry):
    found = re.search(rf"{entry['key']}(?:的藏干为|藏)([甲乙丙丁戊己庚辛壬癸、]+)", entry["text"])
    return found.group(1).split("、") if found else None


def dignity_term(entry):
    found = re.search(r"为“?(入庙|擢升|失势|落陷)”?(?!并)", entry["text"])
    return found.group(1) if found else None


def table_dignity(entry):
    planet, sign = entry["key"].split(":")
    strong, weak = DIGNITY.get(planet, ({}, {}))
    return {**strong, **weak}.get(sign)


def checks(entry: dict) -> list[str] | None:
    """The rule checks a pass item satisfies, or None when one fails (conservative: a
    direction needs its convention or explicit wording, narrower than the rubric)."""
    text, system, kind = entry["text"], entry["system"], entry["kind"]
    if entry["id"] in DISPUTED or certainty_finding(text) or predicts(text):
        return None
    notes = ["无确定性词语，无对现实事件的预测"]
    for theme, value in entry["theme_map"].items():
        if not value:
            continue
        if theme in conventional(entry):
            notes.append(f"{THEME_ZH[theme]} {value:+g} 属本体系方向约定")
            continue
        stated = re.search(STATED[theme], text)
        if not stated:
            return None
        notes.append(f"{THEME_ZH[theme]} {value:+g} 有文字“{stated.group(0)}”")
    if not any(entry["theme_map"].values()):
        notes.append("theme_map 全为 0，与中性文字相容")
    if system == "daily" and any(entry["theme_map"].values()):
        return None
    if system == "bazi" and kind == "hidden":
        stems = listed_stems(entry)
        if not stems or sorted(stems) != sorted(LunarUtil.ZHI_HIDE_GAN[entry["key"]]):
            return None
        notes.append(f"藏干成员{'、'.join(stems)}与参考表一致（顺序不审）")
    if system == "bazi" and kind == "branch":
        if f"属{LunarUtil.WU_XING_ZHI[entry['key']]}" not in text:
            return None
        notes.append(f"地支五行属{LunarUtil.WU_XING_ZHI[entry['key']]}与参考表一致")
    if system == "name" and kind == "shuli":
        number = int(entry["key"])
        level = "吉" if number in LUCKY else "半吉" if number in MIXED else "凶"
        if f"“{level}”" not in text or f"对应{element(number)}" not in text:
            return None
        notes.append(f"归类“{level}”、尾数对应{element(number)}与参考表一致")
    if system == "astro" and kind == "planet_sign" and dignity_term(entry):
        if dignity_term(entry) != table_dignity(entry):
            return None
        notes.append(f"尊贵“{dignity_term(entry)}”与参考表一致")
    if system == "astro" and kind == "planet_house":
        house = int(entry["key"].split(":")[1])
        topics = re.split(r"与|、|和", HOUSE_TEXT[house - 1])
        if f"第{house}宫" in text and not any(t in text for t in topics):
            return None
    if system == "daily" and kind == "day_element":
        colors = DAY_COLORS[entry["key"]][1].split("传统配色为")[1]
        if colors not in text:
            return None
        notes.append(f"配色{colors}与参考表一致")
    if system == "dream" and entry["synonyms"]:
        notes.append(f"同义词{'、'.join(entry['synonyms'])}均指同一意象")
    return notes


def theme_change(entry, rng, *, flip):
    values = entry["theme_map"]
    if flip:
        # A stated direction, or a card's single tone: the flipped sign contradicts the text.
        signs = {v > 0 for v in values.values() if v}
        toned = (
            entry["system"] == "tarot" and len(signs) == 1 and max(map(abs, values.values())) >= 0.3
        )
        # Small values (±0.05) are too faint for a label nobody could dispute.
        themes = [
            t
            for t, v in values.items()
            if abs(v) >= 0.15 and (toned or re.search(STATED[t], entry["text"]))
        ]
    else:  # outside the convention, and no wording that could even hint at the theme
        themes = [
            t
            for t, v in values.items()
            if not v and t not in conventional(entry) and not re.search(HINTED[t], entry["text"])
        ]
    if not themes:
        return None
    theme = rng.choice(sorted(themes))
    old = entry["theme_map"][theme]
    new = -old if flip else rng.choice((0.3, -0.3))
    variant = copy.deepcopy(entry)
    variant["theme_map"][theme] = new
    if flip:
        lean = "顺" if old > 0 else "阻"
        stated = re.search(STATED[theme], entry["text"])
        detail = (
            f"text 对{THEME_ZH[theme]}的表述偏{lean}"
            if stated
            else f"牌义整体偏{lean}（各主题方向一致）"
        ) + f"，theme_map.{theme} 却是 {new:+g}（原为 {old:+g}）"
    else:
        detail = f"text 没有{THEME_ZH[theme]}方面的表述，theme_map.{theme} 却标为 {new:+g}"
    return variant, detail, dict(field=f"theme_map.{theme}", before=old, after=new)


def replace_text(entry, old, new, detail):
    if old not in entry["text"]:
        return None
    variant = copy.deepcopy(entry)
    variant["text"] = entry["text"].replace(old, new, 1)
    return variant, detail, dict(field="text", before=old, after=new)


def append_text(entry, sentence, detail):
    variant = copy.deepcopy(entry)
    variant["text"] = entry["text"] + sentence
    return variant, detail, dict(field="text", before="（无）", after=sentence)


def with_synonym(entry, alias, detail):
    if alias in entry["synonyms"]:
        return None
    variant = copy.deepcopy(entry)
    variant["synonyms"] = [*entry["synonyms"], alias]
    return variant, detail, dict(field="synonyms", before="（无）", after=alias)


def added_synonym(entry, alias):
    """A boundary pass: the entry with one more synonym the dream anchor accepts."""
    result = with_synonym(entry, alias, "")
    if result is None:
        return None
    return result[0], f"新增同义词“{alias}”是同一意象的说法（解梦同义词锚点）"


def tarot_duplicate(entry, by_id):
    upright = by_id.get(entry["id"].replace(":reversed", ":upright"))
    if not upright or upright["text"] == entry["text"]:
        return None
    variant = copy.deepcopy(entry)
    variant["text"] = upright["text"]
    return (
        variant,
        "逆位释义写成了正位释义（与 counterpart 文字相同），正逆位没有区分，且与本条方向不符",
        dict(field="text", before=entry["text"], after=upright["text"]),
    )


def astro_dignity(entry):
    term = dignity_term(entry)
    if not term or term != table_dignity(entry):
        return None
    return replace_text(
        entry,
        f"为{term}",
        f"为{STRONGER[term]}",
        f"按本项目尊贵表此配置为{term}，text 写成了{STRONGER[term]}",
    )


def modern_dignity(entry):
    planet = entry["key"].split(":")[0]
    sentence = f"在传统尊贵体系中，{BODY_ZH[planet]}在此星座为入庙。"
    return append_text(
        entry,
        sentence,
        f"{planet} 属现代行星，不在本项目的传统尊贵表中（参考事实），text 却给出“入庙”",
    )


def astro_house(entry):
    house = int(entry["key"].split(":")[1])
    topic, wrong = HOUSE_TEXT[house - 1], HOUSE_TEXT[(house + 5) % 12]
    return replace_text(
        entry,
        f"第{house}宫，可围绕{topic}",
        f"第{house}宫，可围绕{wrong}",
        f"第{house}宫的主题是“{topic}”（参考事实），text 写成了“{wrong}”",
    )


def bazi_hidden(entry):
    stems = listed_stems(entry)
    if not stems:
        return None
    wrong = next(s for s in "甲乙丙丁戊己庚辛壬癸" if s not in stems)
    correct = "、".join(stems)
    changed = "、".join([*stems[:-1], wrong])
    return replace_text(
        entry,
        correct,
        changed,
        f"{entry['key']}的藏干应为{correct}（参考事实），text 写成{changed}",
    )


def bazi_branch(entry):
    right = LunarUtil.WU_XING_ZHI[entry["key"]]
    wrong = ELEMENTS[(ELEMENTS.index(right) + 1) % 5]
    return replace_text(
        entry,
        f"属{right}",
        f"属{wrong}",
        f"地支{entry['key']}属{right}（参考事实），text 写成属{wrong}",
    )


def bazi_group(entry):
    if entry["key"] == "三合":
        return replace_text(
            entry, "申子辰合水局", "申子辰合木局", "申子辰三合为水局（参考事实），text 写成木局"
        )
    return replace_text(
        entry,
        "亥子丑对应冬季，会水",
        "亥子丑对应冬季，会木",
        "亥子丑三会为水（参考事实），text 写成会木",
    )


def bazi_generic(entry):
    variant = copy.deepcopy(entry)
    variant["text"] = GENERIC[entry["kind"]].format(key=entry["key"])
    detail = f"只有通用说明，没有写出{entry['key']}本身的核心信息，换成同类其他对象也同样成立"
    return variant, detail, dict(field="text", before=entry["text"], after=variant["text"])


def name_digit(entry):
    found = re.search(r"尾数(\d)在三才里对应(.)", entry["text"])
    if not found:
        return None
    right = found.group(2)
    wrong = ELEMENTS[(ELEMENTS.index(right) + 2) % 5]
    return replace_text(
        entry,
        found.group(0),
        f"尾数{found.group(1)}在三才里对应{wrong}",
        f"尾数{found.group(1)}对应{right}（参考事实），text 写成{wrong}",
    )


def name_level(entry):
    number = int(entry["key"])
    right = "吉" if number in LUCKY else "半吉" if number in MIXED else "凶"
    wrong = "凶" if right != "凶" else "吉"
    return replace_text(
        entry,
        f"“{right}”",
        f"“{wrong}”",
        f"本项目归类中{number}为{right}（参考事实），text 写成{wrong}",
    )


def sancai_claim(entry):
    found = re.search(r"([木火土金水])克([木火土金水])", entry["text"])
    return found.group(0) if found else None


def name_relation(entry):
    claim = sancai_claim(entry)
    reverse = claim[2] + "克" + claim[0]
    return replace_text(entry, claim, reverse, f"五行相克为{claim}（参考事实），text 写成{reverse}")


def daily_color(entry):
    right = DAY_COLORS[entry["key"]][1].split("传统配色为")[1]
    other = ELEMENTS[(ELEMENTS.index(entry["key"]) + 1) % 5]
    wrong = DAY_COLORS[other][1].split("传统配色为")[1]
    return replace_text(
        entry,
        f"传统配色为{right}",
        f"传统配色为{wrong}",
        f"{entry['key']}的传统配色为{right}（参考事实），text 写成{wrong}",
    )


def daily_direction(entry):
    variant = copy.deepcopy(entry)
    variant["theme_map"]["self"] = 0.2
    return (
        variant,
        "每日运势条目按本项目约定须保持中性（theme_map 全为0），此处 self 标为 +0.2",
        dict(field="theme_map.self", before=0.0, after=0.2),
    )


def daily_luck(entry):
    return replace_text(
        entry, "不带来实际运气", "可以为当天带来好运", "把配色约定写成了能带来实际运气"
    )


def recipes(system: str, by_id: dict[str, dict], rng: random.Random):
    """(label, type, {partition: count}, candidates, make); make(entry) returns
    (variant, detail, change) for a fail and (variant, note) for a boundary pass."""
    entries = sorted(by_id.values(), key=lambda e: e["id"])

    def of(*kinds):
        return [e for e in entries if e["kind"] in kinds]

    def counts(holdout, dev):
        return dict(holdout=holdout, dev=dev)

    def keep(note):
        return lambda e: (e, note)

    def prediction(entry):
        return append_text(
            entry,
            rng.choice(PREDICTIONS[system]),
            "加入了对现实事件的预测（“预示……会……”），没有确定性词语但仍是预测",
        )

    predictable = [e for e in entries if e["kind"] not in ("convention", "position")]
    unsupported = lambda e: theme_change(e, rng, flip=False)  # noqa: E731
    contradicts = lambda e: theme_change(e, rng, flip=True)  # noqa: E731
    if system == "tarot":
        same_direction = [
            e
            for e in of("card")
            if e["key"].endswith(":reversed")
            and (up := by_id.get(e["id"].replace(":reversed", ":upright")))
            and any(e["theme_map"].get(t, 0) * up["theme_map"].get(t, 0) > 0 for t in THEME_ZH)
        ]
        return [
            ("pass", "same_direction_reversed", counts(4, 3), same_direction,
             keep("逆位与正位方向相同（程度减弱），塔罗规则允许，只要与本条文字一致")),
            ("fail", "unsupported_direction", counts(4, 2), [e for e in of("card", "position") if e["id"] not in RESERVED], unsupported),
            ("fail", "direction_contradicts_text", counts(4, 3), of("card"), contradicts),
            ("fail", "orientation_not_distinguished", counts(3, 2),
             [e for e in of("card") if e["key"].endswith(":reversed")],
             lambda e: tarot_duplicate(e, by_id)),
            ("fail", "position_mismatch", counts(1, 0), [by_id["kb:tarot:position:three_card:1"]],
             lambda e: replace_text(e, "“过去”", "“未来”", "牌阵定义中三张牌阵第1位是“过去”，text 写成了“未来”")),
            ("fail", "position_mismatch", counts(0, 1), [by_id["kb:tarot:position:decision:2"]],
             lambda e: replace_text(e, "此牌位对应“选 A”，用于梳理选择 A", "此牌位对应“选 B”，用于梳理选择 B",
                                    "牌阵定义中决策牌阵第2位是“选 A”，text 写成了“选 B”")),
            ("fail", "prediction", counts(3, 2), predictable, prediction),
        ]  # fmt: skip
    if system == "astro":
        supported = [
            e
            for e in of("planet_house")
            if any(
                v and t not in conventional(e) and re.search(STATED[t], e["text"])
                for t, v in e["theme_map"].items()
            )
        ]
        return [
            ("pass", "off_convention_supported", counts(3, 2), supported,
             keep("方向不在落宫约定内，但文字写明了对应主题（锚点B）")),
            ("pass", "modern_planet", counts(2, 1),
             [e for e in of("planet") if e["key"] in MODERN],
             keep("现代行星，没有尊贵说法属于正常（参考事实）")),
            ("fail", "dignity_wrong", counts(3, 2), [e for e in of("planet_sign") if dignity_term(e)], astro_dignity),
            ("fail", "modern_planet_dignity", counts(2, 1),
             [e for e in of("planet_sign") if e["key"].split(":")[0] in MODERN], modern_dignity),
            ("fail", "house_topic_wrong", counts(3, 2), of("planet_house"), astro_house),
            ("fail", "unsupported_direction", counts(3, 2), of("planet_house"), unsupported),
            ("fail", "direction_contradicts_text", counts(2, 1), of("planet_sign"), contradicts),
            ("fail", "prediction", counts(2, 2), predictable, prediction),
        ]  # fmt: skip
    if system == "bazi":
        reordered = [
            e
            for e in of("hidden")
            if (s := listed_stems(e)) and s != LunarUtil.ZHI_HIDE_GAN[e["key"]]
        ]
        return [
            ("pass", "stem_order_differs", counts(1, 0), reordered,
             keep("藏干列举顺序与参考表不同，但成员一致；规则只审成员")),
            ("pass", "relation_with_supported_direction", counts(2, 1),
             [e for e in of("relation") if any(e["theme_map"].values())],
             keep("术语条目带方向，但文字写明了对应主题（锚点B）")),
            ("pass", "convention_direction_unstated", counts(1, 1), of("ten_god", "god_pillar"),
             keep("十神的自我、事业方向属约定，不必在文字中写明（锚点B）")),
            ("pass", "zero_with_topic_mention", counts(1, 2), [
                e for e in of("relation", "element_relation", "nayin", "convention")
                if not any(e["theme_map"].values())
                and any(re.search(HINTED[t], e["text"]) for t in THEME_ZH)
            ], keep("文字提到相关主题但只作中性说明，方向为 0 与之相容（锚点B）")),
            ("fail", "hidden_stems_wrong", counts(2, 1), of("hidden"), bazi_hidden),
            ("fail", "branch_element_wrong", counts(2, 1), of("branch"), bazi_branch),
            ("fail", "group_members_wrong", counts(1, 0), [by_id["kb:bazi:relation:三合"]], bazi_group),
            ("fail", "group_members_wrong", counts(0, 1), [by_id["kb:bazi:relation:三会"]], bazi_group),
            ("fail", "not_object_specific", counts(1, 1), of("hidden"), bazi_generic),
            ("fail", "not_object_specific", counts(1, 0), of("branch"), bazi_generic),
            ("fail", "not_object_specific", counts(1, 1), of("relation"), bazi_generic),
            ("fail", "unsupported_direction", counts(2, 1), of("stem"), unsupported),
            ("fail", "direction_contradicts_text", counts(2, 2), of("ten_god", "god_pillar"), contradicts),
            ("fail", "prediction", counts(3, 2), predictable, prediction),
        ]  # fmt: skip
    if system == "name":
        return [
            ("pass", "disputed_number", counts(2, 2),
             [e for e in of("shuli") if int(e["key"]) in DISPUTED_NUMBERS],
             keep("各家归类不同的数，与本项目归类一致即不算错（锚点D）")),
            ("pass", "folk_once", counts(1, 1),
             [e for e in of("sancai") if e["text"].count("民间") == 1],
             keep("民间约定只写了一次，规则不要求每句重复（锚点E）")),
            ("fail", "tail_digit_element_wrong", counts(3, 2), of("shuli"), name_digit),
            ("fail", "shuli_level_wrong", counts(3, 2), of("shuli"), name_level),
            ("fail", "sancai_relation_wrong", counts(2, 1),
             [e for e in of("sancai") if sancai_claim(e)], name_relation),
            ("fail", "evaluation_as_fact", counts(3, 2), of("sancai", "shuli"),
             lambda e: append_text(e, rng.choice(OBJECTIVE[e["kind"]]),
                                   "把民间约定的评价写成了对使用者现实的客观推断")),
            ("fail", "unsupported_direction", counts(2, 1), of("sancai"), unsupported),
            ("fail", "prediction", counts(2, 2), predictable, prediction),
        ]  # fmt: skip
    if system == "dream":
        symbols = {e["key"]: e for e in of("symbol")}
        bad = {k: (a, why) for k, a, why in BAD_SYNONYMS}
        good = dict(GOOD_SYNONYMS)
        return [
            ("pass", "legit_synonym_added", counts(3, 2), [symbols[k] for k in good if k in symbols],
             lambda e: added_synonym(e, good[e["key"]])),
            ("pass", "sensitive_calm", counts(1, 1),
             [symbols[k] for k in ("葬礼", "生病", "去世的亲人", "死亡") if k in symbols],
             keep("敏感意象，措辞平和且不作预兆（解梦规则）")),
            ("fail", "synonym_not_same_image", counts(6, 4), [symbols[k] for k in bad if k in symbols],
             lambda e: with_synonym(e, bad[e["key"]][0], f"同义词“{bad[e['key']][0]}”{bad[e['key']][1]}")),
            ("fail", "unsupported_direction", counts(3, 2), of("symbol"), unsupported),
            ("fail", "direction_contradicts_text", counts(2, 1), of("symbol"), contradicts),
            ("fail", "prediction", counts(4, 3), of("symbol"), prediction),
        ]  # fmt: skip
    day = {k: by_id[f"kb:daily:day_element:{k}"] for k in DAY_COLORS}
    return [
        ("pass", "neutral_note_added", counts(0, 3), of("convention"),
         lambda e: (append_text(e, NEUTRAL_NOTE, "")[0], "补了一句中性说明，仍是约定、仍无方向")),
        ("fail", "color_wrong", counts(3, 0), [day[k] for k in "木火水"], daily_color),
        ("fail", "color_wrong", counts(0, 1), [day["金"]], daily_color),
        ("fail", "luck_claim", counts(2, 0), [day[k] for k in "土金"], daily_luck),
        ("fail", "luck_claim", counts(0, 1), [day["木"]], daily_luck),
        ("fail", "nonzero_direction", counts(4, 0), of("convention"), daily_direction),
        ("fail", "nonzero_direction", counts(0, 1), [day["水"]], daily_direction),
    ]  # fmt: skip


def pick(pool, count, make, used, rng, label):
    pool = [e for e in pool if e["id"] not in used and e["id"] not in DISPUTED]
    rng.shuffle(pool)
    made = []
    for entry in pool:
        if len(made) == count:
            break
        if label == "pass" and checks(entry) is None:
            continue
        result = make(entry)
        if result is None or (label == "fail" and content_hash(result[0]) == content_hash(entry)):
            continue
        used.add(entry["id"])
        made.append((entry, result))
    return made


def draft(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    items = []
    for system in SYSTEMS:
        by_id = {e["id"]: e for e in review.load_entries(review.ROOT / "knowledge/sources", system)}
        plan = recipes(system, by_id, rng)
        used: set[str] = set()
        for partition in ("holdout", "dev"):
            size = (DAILY_SIZES if system == "daily" else SIZES)[partition]
            if system == "daily":
                used = set()  # both partitions draw on all nine entries
            rows = []
            for label, kind, wanted, candidates, make in plan:
                count = wanted[partition]
                made = pick(candidates, count, make, used, rng, label) if count else []
                if label == "fail" and len(made) < count:
                    raise ValueError(f"{system} {partition} {kind} 只构造出 {len(made)}/{count} 条")
                for base, result in made:
                    if label == "fail":
                        variant, detail, change = result
                        rows.append(
                            dict(
                                label="fail",
                                case="defect",
                                base=base["id"],
                                defect=dict(type=kind, detail=detail),
                                change=change,
                                rationale=f"由现行条目改出一处缺陷（{ANCHOR_OF[kind]}），其余内容不变；"
                                "按规则应判 revise 或 reject。",
                                entry=variant,
                            )
                        )
                    else:
                        variant, note = result
                        rows.append(
                            dict(
                                label="pass",
                                case="boundary",
                                base=base["id"],
                                rationale=f"边界案例：{note}。按规则逐项核对："
                                + "；".join(checks(variant) or checks(base)),
                                entry=variant,
                            )
                        )
            fails = sum(r["label"] == "fail" for r in rows)
            if fails != size:
                raise ValueError(f"{system} {partition} 缺陷 {fails}，应为 {size}")
            typical_needed = size - sum(r["label"] == "pass" for r in rows)
            # daily has nine entries: each is both a typical pass and the base of a defect.
            pool = [
                e
                for e in sorted(by_id.values(), key=lambda e: e["id"])
                if (system == "daily" or e["id"] not in used)
                and e["id"] not in RESERVED
                and checks(e) is not None
            ]
            for entry in stratified(pool, typical_needed, rng):
                used.add(entry["id"])
                rows.append(
                    dict(
                        label="pass",
                        case="typical",
                        base=entry["id"],
                        rationale="按规则逐项核对：" + "；".join(checks(entry)),
                        entry=entry,
                    )
                )
            rng.shuffle(rows)
            prefix = "h" if partition == "holdout" else "d"
            for number, row in enumerate(rows, 1):
                items.append(
                    dict(
                        id=f"cal-{system}-{prefix}{number:02d}",
                        system=system,
                        partition=partition,
                        **row,
                    )
                )
    return dict(
        schema_version=1,
        status="draft_needs_owner_confirmation",
        drafted_by="Anthropic Claude，2026-10-22 应负责人要求起草；负责人确认后冻结",
        purpose="阶段1第二轮：dev 用于试跑与完善规则，holdout 只在预先登记的正式验收中使用一次",
        seed=seed,
        items=items,
    )


def stratified(pool: list[dict], count: int, rng: random.Random) -> list[dict]:
    """Round-robin over kinds so every kind of entry appears before any repeats."""
    by_kind: dict[str, list[dict]] = {}
    for entry in pool:
        by_kind.setdefault(entry["kind"], []).append(entry)
    for members in by_kind.values():
        rng.shuffle(members)
    chosen = []
    while len(chosen) < count and any(by_kind.values()):
        for kind in sorted(by_kind):
            if by_kind[kind] and len(chosen) < count:
                chosen.append(by_kind[kind].pop())
    if len(chosen) < count:
        raise ValueError("合格条目不足")
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    data = draft(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000), encoding="utf-8"
    )
    counts: dict = {}
    for item in data["items"]:
        key = f"{item['system']}/{item['partition']}"
        counts.setdefault(key, {}).setdefault(f"{item['label']}:{item['case']}", 0)
        counts[key][f"{item['label']}:{item['case']}"] += 1
    print(json.dumps(counts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
