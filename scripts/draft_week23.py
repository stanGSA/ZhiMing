"""Deterministic original draft templates, explicitly NOT human reviewed."""

from pathlib import Path

import yaml

from knowledge.catalogues import expected_keys
from plugins.astro.calculator import BODY_ZH, SIGN_ZH, SIGNS

ROOT = Path(__file__).resolve().parents[1]
PLANET_THEMES = {
    "Sun": "自我表达与目标",
    "Moon": "感受与安全感",
    "Mercury": "信息理解与沟通",
    "Venus": "价值取舍与关系协调",
    "Mars": "行动与竞争",
    "Jupiter": "学习与扩展",
    "Saturn": "责任、边界与长期投入",
    "Uranus": "改变与独立",
    "Neptune": "想象与理想",
    "Pluto": "权力边界与深层转变",
}
SIGN_TEXT = dict(
    zip(
        SIGNS,
        (
            "主动尝试，同时留出确认步骤",
            "重视稳定资源，留意惯性",
            "善用好奇与交流，防止注意力分散",
            "关注归属感，表达需求而非期待别人猜",
            "愿意展示成果，也倾听合作反馈",
            "细分任务提升质量，避免完美主义拖慢",
            "重视协调与公平，练习明确取舍",
            "关注信任与深度，保护清楚的边界",
            "从学习和探索获得动力，落实具体步骤",
            "循序规划和承担责任，给自己合理节奏",
            "重视独立见解和共同目标，保持现实连接",
            "感受与想象丰富，用清晰任务保护精力",
        ),
        strict=True,
    )
)
HOUSE_TEXT = (
    "自我呈现",
    "资源与价值",
    "学习和日常沟通",
    "家庭与内在基础",
    "创作与兴趣",
    "日常工作与习惯",
    "合作与关系",
    "共享资源与信任",
    "远行、学习与视野",
    "职业与公共责任",
    "社群与长期愿景",
    "休整与内在反思",
)
WORK_EXAMPLES = {
    "Sun": "目标拆解、项目责任和成果呈现",
    "Moon": "工作节奏、团队支持与资源稳定",
    "Mercury": "需求梳理、业务分析、技术写作与知识管理",
    "Venus": "用户体验、内容表达与协作协调",
    "Mars": "任务推进、交付与流程改善",
    "Jupiter": "培训、知识传播与跨文化学习",
    "Saturn": "质量标准、长期计划和职责边界",
    "Uranus": "研究新方法、工具应用与流程自动化",
    "Neptune": "创意表达与清晰任务边界",
    "Pluto": "资源权限、保密责任与组织变化",
}
GOD_TEXT = {
    "比肩": ("独立与同伴", "明确自己的职责，也给同伴协作空间", 0.1),
    "劫财": ("竞争与共享", "留意资源边界，协商清楚投入和分配", -0.1),
    "食神": ("表达与产出", "通过稳定输出展示技能，保持可持续节奏", 0.2),
    "伤官": ("创新与质疑", "提出改进同时说明依据，避免只否定规则", 0.1),
    "偏财": ("机会与调配", "探索机会时核实成本，不据符号作投资预测", 0.1),
    "正财": ("秩序与资源", "把目标转成预算、流程和能交付的成果", 0.2),
    "七杀": ("压力与挑战", "面对任务压力先明确边界、资源和支持", -0.2),
    "正官": ("职责与规范", "以清楚标准承担责任，审视是否过度自我约束", 0.1),
    "偏印": ("探索与独特学习", "学习新角度后用小实验检验，不急于下结论", 0.0),
    "正印": ("学习与支持", "借助学习和支持体系完善准备，避免只积累不行动", 0.2),
}

# Stage 1 B1: relationship/finance directions, drafted by Anthropic Claude on 2026-10-21 from
# traditional rules. Only placements with a traditional basis get a direction; every other
# placement keeps 0 ("no directional content"). Model reviewers must not be Anthropic.
B1_SOURCE = "感情、财务方向由 Anthropic Claude 于2026-10-21按传统规则起草"
# Ten gods (gender-neutral simplification): (relationship, finance) and the matching phrases.
GOD_DIRECTIONS = {
    "比肩": (
        -0.1,
        "重视平等与独立，也容易各自坚持，宜留出协商空间",
        -0.1,
        "同伴分担也分享，留意合伙分配",
    ),
    "劫财": (
        -0.15,
        "容易出现竞争或争执，宜坦诚说明边界",
        -0.2,
        "留意资源被分走或冲动花费，借贷与合伙要写清约定",
    ),
    "食神": (0.15, "温和，重视相处的愉快感", 0.15, "倾向通过技能与产出带来收入"),
    "伤官": (
        -0.15,
        "直率，容易挑剔对方，宜先肯定再提意见",
        0.1,
        "可凭创意与专长开源，收入节奏可能起伏",
    ),
    "偏财": (
        0.1,
        "人缘与交际较活跃，宜保持专注",
        0.15,
        "较容易遇到机会，同时核实风险，不据此作投资判断",
    ),
    "正财": (0.15, "倾向稳定投入、重视承诺", 0.2, "对应稳定收入与预算，适合按计划积累"),
    "七杀": (-0.15, "容易出现强势与压力，宜明确界限、互相尊重", 0.0, ""),
    "正官": (0.15, "重视责任、规范与承诺", 0.1, "倾向稳定的职位收入，按规矩管理财务"),
    "偏印": (
        -0.1,
        "较需要独处空间，容易显得疏离，宜主动表达",
        -0.1,
        "不太关注理财，宜建立基本预算",
    ),
    "正印": (0.1, "重视照顾与支持", 0.0, ""),
}
# Traditional dignities (domicile/exaltation, detriment/fall) of the planets that signify a
# theme below. The outer planets stay sign-neutral: their sign is shared by a whole generation.
DIGNITY = {
    "Moon": ({"Cancer": "入庙", "Taurus": "擢升"}, {"Capricorn": "落陷", "Scorpio": "失势"}),
    "Mercury": (
        {"Gemini": "入庙", "Virgo": "入庙并擢升"},
        {"Sagittarius": "落陷", "Pisces": "落陷并失势"},
    ),
    "Venus": (
        {"Taurus": "入庙", "Libra": "入庙", "Pisces": "擢升"},
        {"Aries": "落陷", "Scorpio": "落陷", "Virgo": "失势"},
    ),
    "Mars": (
        {"Aries": "入庙", "Scorpio": "入庙", "Capricorn": "擢升"},
        {"Taurus": "落陷", "Libra": "落陷", "Cancer": "失势"},
    ),
    "Jupiter": (
        {"Sagittarius": "入庙", "Pisces": "入庙", "Cancer": "擢升"},
        {"Gemini": "落陷", "Virgo": "落陷", "Capricorn": "失势"},
    ),
    "Saturn": (
        {"Capricorn": "入庙", "Aquarius": "入庙", "Libra": "擢升"},
        {"Cancer": "落陷", "Leo": "落陷", "Aries": "失势"},
    ),
}
# Sign-based directions only for each theme's traditional significators:
# planet -> theme -> (magnitude, dignified phrase, debilitated phrase).
SIGN_DIRECTIONS = {
    "Venus": {
        "relationship": (
            0.2,
            "较容易表达好感、经营和谐关系",
            "表达好感的方式容易急切或别扭，宜多确认彼此节奏",
        ),
        "finance": (0.15, "对价值与花费有较好的分寸感", "留意因喜好或情绪冲动消费"),
    },
    "Moon": {
        "relationship": (
            0.15,
            "情感需求较容易被理解和回应",
            "情感需求不易直接说出，宜主动沟通感受",
        )
    },
    "Mars": {
        "relationship": (
            0.15,
            "主动直接，敢于表达需求",
            "主动性容易受压或转为急躁，宜直接而温和地沟通",
        )
    },
    "Mercury": {
        "finance": (0.15, "处理账目、比较与交易较有条理", "细节与合同条款容易疏忽，宜复核数字")
    },
    "Jupiter": {
        "finance": (
            0.2,
            "倾向看到机会、乐于扩展，仍需核实成本",
            "容易高估机会或分散投入，扩张前先算清预算",
        )
    },
    "Saturn": {
        "finance": (
            0.15,
            "倾向稳健积累、守住预算",
            "容易因压力过度保守或感到资源吃紧，宜做长期规划",
        )
    },
}
# House topics: the 2nd and 8th are money, the 5th and 7th romance and partnership. Benefics
# lean positive, the luminaries and Mercury mildly positive, the malefics negative; the outer
# planets stay house-neutral (their house meanings are modern and divergent).
HOUSE_THEME = {"2": "finance", "5": "relationship", "7": "relationship", "8": "finance"}
PLANET_NATURE = dict(
    Venus=0.2, Jupiter=0.2, Sun=0.1, Moon=0.1, Mercury=0.1, Mars=-0.15, Saturn=-0.15
)
HOUSE_PHRASES = {
    "2": dict(
        Sun="把收入与价值感视为自我实现的一部分，适合设定清楚的财务目标",
        Moon="重视财务安全感，倾向积蓄以求安心",
        Mercury="可通过信息、沟通或交易类工作获得收入，适合比较后再决定支出",
        Venus="对价值与享受敏感，较容易得到积累的机会，同时留意花在喜好上的开销",
        Jupiter="倾向看到增长机会，收入来源较宽，扩张前仍需核算成本",
        Mars="收入靠主动争取，也容易冲动支出，大额花费前先冷静一天",
        Saturn="积累偏慢、容易感到资源紧，适合预算与长期规划",
    ),
    "5": dict(
        Sun="恋爱与兴趣是表达自我的重要场景，投入时容易带来活力",
        Moon="恋爱中重视情感交流与陪伴，享受轻松的相处",
        Mercury="恋爱中重视聊得来，交流与玩笑能拉近距离",
        Venus="恋爱与享受中较容易感到愉快，表达好感比较自然",
        Jupiter="恋爱中乐观大方，较容易遇到愉快的相处",
        Mars="恋爱中热情直接，也容易急躁起冲突，留意沟通节奏",
        Saturn="恋爱中较谨慎，容易压抑表达或进展缓慢，可给自己放松的空间",
    ),
    "7": dict(
        Sun="伴侣与合作关系是投入心力、认识自己的重要场景",
        Moon="在伴侣关系中寻求情感安全感，重视被理解与照顾",
        Mercury="伴侣与合作关系中重视沟通，适合把期待说清楚",
        Venus="伴侣与合作关系中较容易得到善意与和谐",
        Jupiter="伴侣与合作关系中较容易得到支持，关系常带来成长",
        Mars="伴侣与合作中容易出现直接冲突，宜约定沟通方式",
        Saturn="关系中责任感重、进展偏慢，需要耐心经营承诺",
    ),
    "8": dict(
        Sun="共享资源、合作财务与信任是关注重点，宜把约定写清楚",
        Moon="在共同财务与亲密信任中寻求安全感，适合与对方坦诚沟通预算",
        Mercury="善于研究共同财务、保险与合同细节，签约前逐条核对",
        Venus="合作与伴侣带来的共享资源较顺，较容易得到他人支持",
        Jupiter="较容易从合作、共享资源或他人支持中受益，借贷仍需量力",
        Mars="共同财务中容易起争执，宜事先约定分配与决策方式",
        Saturn="债务与共同责任感较重，处理借贷与担保宜保守稳妥",
    ),
}
THEME_ZH = dict(relationship="感情", finance="财务")
PILLAR_ZH = dict(year="年", month="月", day="日", time="时")


def sign_directions(planet, sign):
    """B1 directions of a planet in a sign, and the sentence that states them."""
    if planet not in SIGN_DIRECTIONS:
        return {}, ""
    strong, weak = DIGNITY[planet]
    label = strong.get(sign) or weak.get(sign)
    if label is None:
        return {}, ""
    polarity = 1 if sign in strong else -1
    themes = {t: v[0] * polarity for t, v in SIGN_DIRECTIONS[planet].items()}
    phrases = "；".join(
        f"{THEME_ZH[t]}方面{v[1] if polarity > 0 else v[2]}"
        for t, v in SIGN_DIRECTIONS[planet].items()
    )
    return themes, f"传统上{BODY_ZH[planet]}在{SIGN_ZH[SIGNS.index(sign)]}为{label}，{phrases}。"


def house_directions(planet, house):
    """B1 direction of a planet in a money or relationship house, and its sentence."""
    if house not in HOUSE_THEME or planet not in PLANET_NATURE:
        return {}, ""
    theme = HOUSE_THEME[house]
    phrase = HOUSE_PHRASES[house][planet]
    return {theme: PLANET_NATURE[planet]}, f"{THEME_ZH[theme]}方面：{phrase}。"


def draft(system, kind, key):
    valence = 0.0
    directions = {}
    if system == "astro":
        if kind == "planet":
            text = f"{BODY_ZH[key]}在传统占星中用于讨论{PLANET_THEMES[key]}。这是象征性反思主题，不表示现实事件必然发生。"
            text += f"职业探索时可用{WORK_EXAMPLES[key]}等任务作实际验证的例子；不是已知技能或职业适配结论。"
        elif kind == "sign":
            text = f"{SIGN_ZH[SIGNS.index(key)]}的象征表达可参考：{SIGN_TEXT[key]}。"
        elif kind == "house":
            text = f"第{key}宫用于讨论{HOUSE_TEXT[int(key) - 1]}；宫位依赖可靠出生时刻。"
        elif kind == "planet_sign":
            planet, sign = key.split(":")
            text = f"{BODY_ZH[planet]}落{SIGN_ZH[SIGNS.index(sign)]}，关注{PLANET_THEMES[planet]}。可尝试：{SIGN_TEXT[sign]}。单一落座不决定性格或成败。"
            text += (
                f"可把{WORK_EXAMPLES[planet]}作为小任务探索方向，并用真实成果与反馈决定职业选择。"
            )
            directions, sentence = sign_directions(planet, sign)
            text += sentence
        elif kind == "planet_house":
            planet, house = key.split(":")
            text = f"{BODY_ZH[planet]}在第{house}宫，可围绕{HOUSE_TEXT[int(house) - 1]}观察{PLANET_THEMES[planet]}的表达。"
            directions, sentence = house_directions(planet, house)
            text += sentence
        elif kind == "aspect":
            descriptions = {
                "conjunction": ("合相强调主题集中，需要协调两种需求", 0.0),
                "opposition": ("对分相提示不同需求拉扯，适合澄清优先级", -0.15),
                "square": ("四分相提示需要调整的摩擦，先安排验证和缓冲", -0.2),
                "trine": ("三分相象征较顺的协作，可把已有优势转成行动", 0.2),
                "sextile": ("六分相象征可主动创造的配合机会，需要实际尝试", 0.15),
            }
            text, valence = descriptions[key]
            text += "。本命相位讨论长期习惯，行运相位只对应工具给出的日期范围；不是现实事件预测。"
        else:
            text = (
                "指定区间没有检测到精确主要相位，不代表没有变化；不要把空事件表解释成确定的吉凶。"
            )
        source = "自写草稿；参考传统回归黄道占星术语；待人工审核"
    else:
        if kind in ("ten_god", "god_pillar"):
            god = key.split(":")[0]
            keywords, text, valence = GOD_TEXT[god]
            text = f"{god}是相对日主的传统关系标签，主题是{keywords}：{text}。"
            love, love_text, money, money_text = GOD_DIRECTIONS[god]
            directions = {t: v for t, v in (("relationship", love), ("finance", money)) if v}
            text += f"感情方面{love_text}" + (f"；财务方面{money_text}" if money else "") + "。"
            text += "传统上配偶星按性别区分，这里只作不分性别的倾向参考。"
            if kind == "god_pillar":
                pillar = PILLAR_ZH[key.split(":")[1]]
                text += f"在{pillar}柱可作为该柱位置的反思线索，不能代替全局分析。"
        elif kind == "stem":
            text = f"天干{key}是阴阳五行关系中的一个符号；需结合日主、所在柱位与节气，不单凭一个字判断命运。"
        elif kind == "branch":
            text = f"地支{key}包含主五行与藏干，计数与藏干信息是不同口径；不能把简单数量当成旺衰或喜用神。"
        elif kind == "element":
            text = f"五行{key}的出现次数只说明本工具的简单计数，需结合节气与藏干理解，不能据此断言需要补某五行。"
        elif kind == "relation":
            valence = (
                -0.1 if key in ("地支冲", "地支刑", "地支害", "自刑", "天干冲", "地支破") else 0.1
            )
            text = f"{key}为干支之间的传统关系。可用来反思协调、边界与调整，不等于关系破裂、灾祸或事情必成；是否化局不在MVP中判定。"
        elif kind == "nayin":
            text = f"纳音{key}是干支组合的传统分类，与天干地支主五行计数口径不同，不据纳音单独推断职业或成败。"
        elif kind == "hidden":
            text = f"{key}支藏干按固定表列出；藏干十神相对当前日主计算，不凭藏干数量判断旺衰。"
        elif kind == "convention":
            text = {
                "day_master": "日主是日柱的天干，五行随该天干主五行确定；十神均相对这个日主计算。日主标签不表示已知人格或职业能力。",
                "dayun": "大运采用lunar_python getYun流派1：阳年男、阴年女顺排，阴年男、阳年女逆排；顺取出生到下一个节、逆取上一个节到出生的间隔，按三天折一年、时辰差折算月日，约每十年换一运。首运从月柱按顺逆移动一位。起运日期、年龄和序列以工具结果为准，不代表现实事件发生日期；其他流派可能不同。",
                "zishi_next_day": "23:00起日柱换为次日，子时天干由次日日干推算；年柱月柱仍按实际节气时刻，不随日柱换日。",
                "zishi_same_day": "区分早晚子时：23–24点日柱属于当天，时柱用次日日干起子时；0–1点为当天早子时。",
                "true_solar_time": "真太阳时为北京时间固定UTC+8加(经度−120度)×4分钟，再加视太阳时减平太阳时的均时差；日时可能跨界，节气边界仍是物理时刻。关闭时先修正历史夏令时，再用北京时间。",
                "year_month_boundary": "以立春的实际时刻换年，以十二节的实际时刻换月，不以春节、农历初一或公历月初换柱。",
                "unknown_time": "出生时辰未知只能提供能确定的三柱，时柱与精确起运不可用；出生日期跨节气或真太阳时可能跨日时须先追问，仍未知则展示候选并标明不确定性。",
            }[key]
        else:
            text = f"五行关系“{key}”需以双方元素与阴阳为条件，用作传统关系描述，不能推出喜用神。"
        source = "自写草稿；参考《渊海子平》《三命通会》传统术语，未复制原文；待人工审核"
    if directions:
        source = source.replace("；待人工审核", f"；{B1_SOURCE}；待人工审核")
    return dict(
        id=f"kb:{system}:{kind}:{key}",
        system=system,
        kind=kind,
        key=key,
        synonyms=[],
        keywords=[key],
        theme_map=dict(
            self=valence,
            career=valence,
            relationship=directions.get("relationship", 0.0),
            finance=directions.get("finance", 0.0),
        ),
        text=text,
        source=source,
        license="本项目自写",
        reviewed=False,
        # A changed entry gets a new edition number, as scripts.model_review_kb apply does.
        version=4 if directions else 3,
    )


def main():
    for system in ("astro", "bazi"):
        entries = [draft(*key) for key in sorted(expected_keys(system))]
        target = ROOT / f"knowledge/sources/{system}/entries.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(
                dict(status="draft_needs_human_review", entries=entries),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        print(system, len(entries))


if __name__ == "__main__":
    main()
