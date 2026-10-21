"""Draft the labelled calibration set for the stage 1 second campaign (owner confirms, then freezes).

Drafted by Anthropic Claude on 2026-10-22 at the owner's request. Anthropic drafted the B1
directions and reviews nothing; this set never enters the knowledge base. Generation is
deterministic from the current sources, so the owner can rerun it and diff the result:

- pass: a current entry both reviewers passed four times on 2026-10-21 whose content the
  checks below find consistent with the rubric anchors and the reference facts;
- fail: a different current entry with exactly one realistic defect, written in the entries'
  own words (no wrapper real entries never carry), with the defect and the change stated.

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
from plugins.name.wuge import ELEMENTS, element
from scripts import model_review_kb as review
from scripts.draft_tarot import MAJOR_THEMES, SUIT_THEMES
from scripts.draft_week6 import DAY_COLORS, LUCKY, MIXED
from scripts.draft_week23 import HOUSE_TEXT, HOUSE_THEME

SEED = 20261022
EVIDENCE = review.ROOT / "docs/verification/kb-model-review/20261021-live/campaign"
THEME_ZH = dict(self="自我状态", career="事业", relationship="感情关系", finance="财务")
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
# (dream key, alias, why it is not the same image) — the anchors' own categories.
BAD_SYNONYMS = (
    ("医生", "护士", "不同人物：护士不是医生"),
    ("新郎", "新娘", "不同人物：新娘不是新郎"),
    ("图书馆", "书店", "不同场所：书店不是图书馆"),
    ("麒麟", "瑞兽", "上位泛称：瑞兽包含麒麟以外的神兽"),
    ("自杀", "想不开", "常见其他义项：想不开也常指一时纠结"),
    ("考试", "考场", "只是场所：考场不等于考试这件事"),
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


def approved_now() -> set[str]:
    """Entries whose current content both reviewers passed four times on 2026-10-21."""
    found = set()
    for path in EVIDENCE.glob("*/summary.json"):
        evidence = review.read_json(path).get("current_content_evidence", {})
        found |= {ref for ref, row in evidence.items() if row["approved"]}
    return found


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


def consistent(entry: dict) -> str | None:
    """Why a current entry cannot serve as a pass item, or None. Conservative: a direction
    needs its convention or explicit wording, narrower than what the rubric accepts."""
    if certainty_finding(entry["text"]):
        return "certainty"
    for theme, value in entry["theme_map"].items():
        if (
            value
            and theme not in conventional(entry)
            and not re.search(STATED[theme], entry["text"])
        ):
            return "direction"
    if entry["system"] == "daily" and any(entry["theme_map"].values()):
        return "daily_direction"
    if entry["system"] == "bazi" and entry["kind"] in ("hidden", "branch"):
        stems = LunarUtil.ZHI_HIDE_GAN[entry["key"]]
        listed = re.search(
            rf"{entry['key']}(?:的藏干为|藏)([甲乙丙丁戊己庚辛壬癸、]+)", entry["text"]
        )
        if not listed or sorted(listed.group(1).split("、")) != sorted(stems):
            return "hidden_stems"
    if entry["system"] == "name" and entry["kind"] == "shuli":
        number = int(entry["key"])
        level = "吉" if number in LUCKY else "半吉" if number in MIXED else "凶"
        if f"“{level}”" not in entry["text"] or f"对应{element(number)}" not in entry["text"]:
            return "shuli"
    return None


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
    variant = copy.deepcopy(entry)
    variant["synonyms"] = [*entry["synonyms"], alias]
    return variant, detail, dict(field="synonyms", before="（无）", after=alias)


def defects(system: str, by_id: dict[str, dict], rng: random.Random):
    """(type, [(base id, make)]) per defect kind, ``make(entry) -> (variant, detail, change)``."""
    entries = sorted(by_id.values(), key=lambda e: e["id"])

    def of(kind):
        return [e for e in entries if e["kind"] == kind]

    plans = []
    predict = PREDICTIONS.get(system, ())
    if system == "tarot":
        plans += [
            (
                "unsupported_direction",
                [*of("card"), *of("position")],
                5,
                lambda e: theme_change(e, rng, flip=False),
            ),
            (
                "direction_contradicts_text",
                of("card"),
                3,
                lambda e: theme_change(e, rng, flip=True),
            ),
            (
                "orientation_not_distinguished",
                [e for e in of("card") if e["key"].endswith(":reversed")],
                3,
                lambda e: tarot_duplicate(e, by_id),
            ),
            (
                "position_mismatch",
                [by_id["kb:tarot:position:three_card:1"]],
                1,
                lambda e: replace_text(
                    e,
                    "“过去”",
                    "“未来”",
                    "牌阵定义中三张牌阵第1位是“过去”，text 写成了“未来”",
                ),
            ),
        ]
    if system == "astro":
        plans += [
            ("dignity_wrong", [e for e in of("planet_sign") if dignity_term(e)], 4, astro_dignity),
            ("house_topic_wrong", of("planet_house"), 3, astro_house),
            (
                "unsupported_direction",
                of("planet_house"),
                3,
                lambda e: theme_change(e, rng, flip=False),
            ),
            (
                "direction_contradicts_text",
                of("planet_sign"),
                2,
                lambda e: theme_change(e, rng, flip=True),
            ),
        ]
    if system == "bazi":
        plans += [
            ("hidden_stems_wrong", of("hidden"), 3, bazi_hidden),
            ("branch_element_wrong", of("branch"), 2, bazi_branch),
            (
                "group_members_wrong",
                [by_id[f"kb:bazi:relation:{k}"] for k in ("三合", "三会")],
                2,
                bazi_group,
            ),
            *[
                ("not_object_specific", of(kind), 1, bazi_generic)
                for kind in ("hidden", "branch", "relation")
            ],
            ("unsupported_direction", of("stem"), 2, lambda e: theme_change(e, rng, flip=False)),
        ]
    if system == "name":
        plans += [
            ("tail_digit_element_wrong", of("shuli"), 3, name_digit),
            ("shuli_level_wrong", of("shuli"), 3, name_level),
            (
                "sancai_relation_wrong",
                [e for e in of("sancai") if sancai_claim(e)],
                2,
                name_relation,
            ),
            (
                "evaluation_as_fact",
                [*of("sancai"), *of("shuli")],
                3,
                lambda e: append_text(
                    e,
                    rng.choice(OBJECTIVE[e["kind"]]),
                    "把民间约定的评价写成了对使用者现实的客观推断",
                ),
            ),
            ("unsupported_direction", of("sancai"), 2, lambda e: theme_change(e, rng, flip=False)),
        ]
    if system == "dream":
        symbols = {e["key"]: e for e in of("symbol")}
        plans += [
            (
                "synonym_not_same_image",
                [symbols[k] for k, *_ in BAD_SYNONYMS if k in symbols],
                6,
                lambda e: with_synonym(
                    e,
                    *next((a, f"同义词“{a}”{why}") for k, a, why in BAD_SYNONYMS if k == e["key"]),
                ),
            ),
            ("unsupported_direction", of("symbol"), 2, lambda e: theme_change(e, rng, flip=False)),
            (
                "direction_contradicts_text",
                of("symbol"),
                2,
                lambda e: theme_change(e, rng, flip=True),
            ),
        ]
    if system == "daily":
        plans += [
            ("color_wrong", [by_id[f"kb:daily:day_element:{k}"] for k in "木火水"], 3, daily_color),
            (
                "luck_claim",
                [by_id[f"kb:daily:day_element:{k}"] for k in "土金"],
                2,
                lambda e: replace_text(
                    e,
                    "不带来实际运气",
                    "可以为当天带来好运",
                    "把配色约定写成了能带来实际运气",
                ),
            ),
            ("nonzero_direction", of("convention"), 4, daily_direction),
        ]
    if predict:
        count = 5 if system == "dream" else 3 if system != "name" else 2
        candidates = [e for e in entries if e["kind"] not in ("convention", "position")]
        plans.append(
            (
                "prediction",
                candidates,
                count,
                lambda e: append_text(
                    e,
                    rng.choice(predict),
                    "加入了对现实事件的预测（“预示……会……”），没有确定性词语但仍是预测",
                ),
            )
        )
    return plans


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


def dignity_term(entry):
    found = re.search(r"为“?(入庙|擢升|失势|落陷)”?(?!并)", entry["text"])
    return found.group(1) if found else None


def astro_dignity(entry):
    term = dignity_term(entry)
    if not term:
        return None
    return replace_text(
        entry,
        f"为{term}",
        f"为{STRONGER[term]}",
        f"按本项目尊贵表此配置为{term}，text 写成了{STRONGER[term]}",
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
    stems = LunarUtil.ZHI_HIDE_GAN[entry["key"]]
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
    detail = (
        f"只有通用说明，没有写出{entry['key']}本身的核心信息（锚点C），换成同类其他对象也同样成立"
    )
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


def draft(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    approved = approved_now()
    items = []
    for system in ("tarot", "astro", "bazi", "name", "dream", "daily"):
        by_id = {e["id"]: e for e in review.load_entries(review.ROOT / "knowledge/sources", system)}
        used: set[str] = set()
        fails = []
        for kind, candidates, count, make in defects(system, by_id, rng):
            pool = [e for e in candidates if e["id"] not in used]
            rng.shuffle(pool)
            made = 0
            for entry in pool:
                if made == count:
                    break
                result = make(entry)
                if result is None:
                    continue
                variant, detail, change = result
                if content_hash(variant) == content_hash(entry):
                    continue
                used.add(entry["id"])
                made += 1
                fails.append((entry, variant, kind, detail, change))
            if made < count:
                raise ValueError(f"{system} {kind} 只构造出 {made}/{count} 条")
        # daily has nine entries: every one is both a pass item and the base of one defect.
        pool = [
            e
            for e in sorted(by_id.values(), key=lambda e: e["id"])
            if e["id"] in approved
            and consistent(e) is None
            and (system == "daily" or e["id"] not in used)
        ]
        passes = stratified(pool, len(fails), rng)
        rows = [
            dict(
                system=system,
                label="pass",
                base=e["id"],
                rationale="现行条目；2026-10-21两家各两轮均判通过；自动核对无确定性措辞，"
                "非零方向符合体系方向约定或有对应表述"
                + ("，与参考事实一致" if system in ("bazi", "name", "daily") else "")
                + "。请按判定锚点复核。",
                entry=e,
            )
            for e in passes
        ] + [
            dict(
                system=system,
                label="fail",
                base=base["id"],
                defect=dict(type=kind, detail=detail),
                change=change,
                rationale="由现行条目改出一处缺陷，其余内容不变；按判定锚点应判 revise 或 reject。",
                entry=variant,
            )
            for base, variant, kind, detail, change in fails
        ]
        rng.shuffle(rows)
        for number, row in enumerate(rows, 1):
            items.append(dict(id=f"cal-{system}-{number:02d}", **row))
    return dict(
        schema_version=1,
        status="draft_needs_owner_confirmation",
        drafted_by="Anthropic Claude，2026-10-22 应负责人要求起草；负责人逐条确认后冻结",
        purpose="阶段1第二轮知识库审核的标注校准集：kappa在此集合上计算（运行前登记）",
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
    counts = {}
    for item in data["items"]:
        counts.setdefault(item["system"], {}).setdefault(item["label"], 0)
        counts[item["system"]][item["label"]] += 1
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
