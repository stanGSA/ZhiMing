"""Week 6 original knowledge drafts (name, dream, daily); explicitly NOT human reviewed.

Texts are written for this project; sources are cited only as the conventions they follow.
Running this script regenerates knowledge/sources/{name,dream,daily}/entries.yaml.
"""

from pathlib import Path

from plugins.dream.symbols import CATEGORIES, SYMBOLS
from plugins.name.wuge import ELEMENTS, GRIDS, relation
from scripts.draft_sources import write_drafts

ROOT = Path(__file__).resolve().parents[1]
LICENSE = "本项目自写"
VERSION = 1
NAME_SOURCE = "自写草稿；按五格剖象法（熊崎氏）民间约定整理，未复制任何书籍文字；待人工审核"
DREAM_SOURCE = "自写草稿；常见意象的心理联想整理，未复制《周公解梦》或现代网站文字；待人工审核"
DAILY_SOURCE = "自写草稿；五行配色为传统约定，仅作说明；待人工审核"
THEMES = ("self", "career", "relationship", "finance")

# 81 数理的三档归类是民间约定，各家对少数数字（如 27、28、40、50、71、73、75）有分歧。
LUCKY = {1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25, 29, 31, 32, 33, 35, 37}
LUCKY |= {39, 41, 45, 47, 48, 52, 57, 61, 63, 65, 67, 68, 81}
MIXED = {30, 38, 40, 49, 50, 51, 53, 55, 58, 71, 73, 75, 77, 78}
LEVEL_TEXT = {
    "吉": "传统上被看作顺遂、易得助力的数，可提醒自己善用已有的优势与人际支持",
    "半吉": "传统上被看作吉凶参半的数，意味着顺与不顺都与个人选择有关，适合提醒自己稳住节奏",
    "凶": "传统上被看作波折较多的数，更适合作为提醒：给计划留余量、遇事多求证，而不是对命运下结论",
}
ELEMENT_TEXT = {
    "木": "生长、计划与向上发展",
    "火": "热情、表达与行动力",
    "土": "稳定、承载与务实",
    "金": "规则、决断与边界",
    "水": "流动、思考与适应",
}
GRID_TEXT = {
    "天格": "天格来自姓氏，五格约定中代表家族背景与先天环境，不随个人取名改变，通常不单独评判。",
    "人格": "人格由姓末字与名首字组成，五格约定中被看作名字的核心，对应自我认知、性格与做事方式。",
    "地格": "地格由名字各字组成，五格约定中对应早年基础、家庭与亲近关系。",
    "外格": "外格由天格加地格减人格得到，五格约定中对应外部人际与社会支持。",
    "总格": "总格是全名实际笔画之和，五格约定中对应整体发展方向与中后期的综合状态。",
}
RELATION_SELF = {
    "生": "外部环境容易给自我提供支持",
    "被生": "自我习惯向外付出、照顾外部期待",
    "同": "内外节奏一致，容易保持方向",
    "克": "外部要求对自我形成压力，需要练习设定边界",
    "被克": "自我倾向主动掌控环境，宜留意与长辈或规则的协调",
}
RELATION_BASE = {
    "生": "愿意为身边的人与生活基础投入",
    "被生": "家庭与生活基础能给自我补充能量",
    "同": "自我与生活基础步调一致",
    "克": "对身边的人和事要求较多，宜放慢节奏沟通",
    "被克": "日常琐事容易牵扯精力，需要主动安排休整",
}
SCORE = {"生": 1, "被生": 1, "同": 1, "克": -1, "被克": -1}


def entry(system, kind, key, text, theme_map, source, keywords=None, synonyms=None):
    return dict(
        id=f"kb:{system}:{kind}:{key}",
        system=system,
        kind=kind,
        key=key,
        synonyms=synonyms or [],
        keywords=keywords or [key],
        theme_map={t: round(theme_map.get(t, 0.0), 3) for t in THEMES},
        text=text,
        source=source,
        license=LICENSE,
        reviewed=False,
        version=VERSION,
    )


def shuli_level(number):
    return "吉" if number in LUCKY else "半吉" if number in MIXED else "凶"


def name_entries():
    entries = []
    for number in range(1, 82):
        level = shuli_level(number)
        valence = {"吉": 0.15, "半吉": 0.05, "凶": -0.15}[level]
        tail = number % 10
        text = (
            f"{number}数在五格数理的民间约定中常被归为“{level}”，尾数{tail}在三才里对应"
            f"{ELEMENTS[((number - 1) % 10) // 2]}。{LEVEL_TEXT[level]}。数理是取名习俗，"
            "不决定一个人的经历。"
        )
        entries.append(
            entry(
                "name",
                "shuli",
                str(number),
                text,
                dict.fromkeys(THEMES, valence),
                NAME_SOURCE,
                keywords=[f"{number}数", level],
            )
        )
    for heaven in ELEMENTS:
        for person in ELEMENTS:
            for earth in ELEMENTS:
                upper, lower = relation(heaven, person), relation(person, earth)
                score = SCORE[upper] + SCORE[lower]
                label = {2: "较顺", 0: "需要协调", -2: "张力较多"}[score]
                key = heaven + person + earth
                text = (
                    f"三才{key}（天格{heaven}、人格{person}、地格{earth}）："
                    f"天格{heaven}与人格{person}是“{upper}”的关系，{RELATION_SELF[upper]}；"
                    f"人格{person}与地格{earth}是“{lower}”的关系，{RELATION_BASE[lower]}。"
                    f"按五行生克规则整体可看作“{label}”，只作自我观察的线索。"
                )
                entries.append(
                    entry(
                        "name",
                        "sancai",
                        key,
                        text,
                        dict(
                            self=0.1 * SCORE[upper],
                            relationship=0.1 * SCORE[lower],
                            career=0.05 * score,
                        ),
                        NAME_SOURCE,
                        keywords=[key, label],
                    )
                )
    for grid in GRIDS:
        entries.append(entry("name", "grid", grid, GRID_TEXT[grid], {}, NAME_SOURCE))
    for element in ELEMENTS:
        entries.append(
            entry(
                "name",
                "element",
                element,
                f"三才中的{element}象征{ELEMENT_TEXT[element]}；它来自格数尾数，不是名字用字的字义五行。",
                {},
                NAME_SOURCE,
            )
        )
    conventions = {
        "stroke_rule": "五格笔画按康熙字典繁体字形计数，偏旁按原字计算（如氵按水4画、艹按艸6画），数字一至十按数值计；与现代简体笔画不同。",
        "compound_surname": "复姓的天格取两字笔画之和，不加假数；人格取姓的第二字与名的第一字。",
        "ambiguous_form": "部分字有不同的繁体或异体写法（如杰与傑、强与強），笔画随写法改变；应按证件或本人习惯的写法确认后再看数理。",
        "bazi_compare": "名字与八字的对照只并列三才五行与原局五行计数，不判断喜用神，也不据此建议改名或“补”某个五行。",
    }
    for key, text in conventions.items():
        entries.append(entry("name", "convention", key, text, {}, NAME_SOURCE))
    return entries


def dream_entries():
    entries = []
    for key, synonyms, category, phrase, themes, valence in SYMBOLS:
        label, tail = CATEGORIES[category]
        text = f"梦见{key}，{phrase}。{tail}"
        theme_map = {t: valence for t in themes}
        entries.append(
            entry(
                "dream",
                "symbol",
                key,
                text,
                theme_map,
                DREAM_SOURCE,
                keywords=[key, label],
                synonyms=list(synonyms),
            )
        )
    conventions = {
        "unmatched": "词典没有收录的意象记为未命中，不作含义解读；可以请用户补充当时的感受或细节。",
        "psyche_only": "梦境只提供心理与情绪层面的线索，不参与时机与运势判断，不预示现实中会发生的事。",
        "no_symbol": "没有可识别的意象时，不作解读，可以询问用户是否记得场景、人物或情绪。",
    }
    for key, text in conventions.items():
        entries.append(entry("dream", "convention", key, text, {}, DREAM_SOURCE))
    return entries


# The five-element colour convention; the knowledge review rubric quotes it too.
DAY_COLORS = {
    "木": ("青绿", "木对应生长，传统配色为青、绿"),
    "火": ("红", "火对应热情，传统配色为红、紫"),
    "土": ("黄", "土对应承载，传统配色为黄、棕"),
    "金": ("白", "金对应决断，传统配色为白、金"),
    "水": ("黑蓝", "水对应流动，传统配色为黑、蓝"),
}


def daily_entries():
    entries = []
    for element, (color, text) in DAY_COLORS.items():
        entries.append(
            entry(
                "daily",
                "day_element",
                element,
                f"流日天干五行为{element}：{text}。“幸运色”只是这一传统配色约定，不带来实际运气。",
                {},
                DAILY_SOURCE,
                keywords=[element, color],
            )
        )
    conventions = {
        "daily_seed": "每日一牌的种子由用户编号与日期的SHA256计算，同一用户同一天结果不变；不同日期重新计算。",
        "no_exact_events": "当天月亮与快行星对本命盘没有精确相位，说明今天没有突出的行运节点，不代表好或坏。",
        "unknown_time": "出生时间未知时以中午为代理计算本命盘，月亮位置与当天精确相位时刻存在不确定性。",
        "moment_only": "每日运势是当天的提示，属于短时信号，不改变本命或流年的长期判断。",
    }
    for key, text in conventions.items():
        entries.append(entry("daily", "convention", key, text, {}, DAILY_SOURCE))
    return entries


def main():
    for system, entries in (
        ("name", name_entries()),
        ("dream", dream_entries()),
        ("daily", daily_entries()),
    ):
        target = ROOT / f"knowledge/sources/{system}/entries.yaml"
        write_drafts(target, entries)
        print(system, len(entries))


if __name__ == "__main__":
    main()
