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


def draft(system, kind, key):
    valence = 0.0
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
            text = f"{BODY_ZH[planet]}落{SIGN_ZH[SIGNS.index(sign)]}，可将{PLANET_THEMES[planet]}与{SIGN_TEXT[sign]}一起反思；不由单一落座决定性格或成败。"
            text += (
                f"可把{WORK_EXAMPLES[planet]}作为小任务探索方向，并用真实成果与反馈决定职业选择。"
            )
        elif kind == "planet_house":
            planet, house = key.split(":")
            text = f"{BODY_ZH[planet]}在第{house}宫，可围绕{HOUSE_TEXT[int(house) - 1]}观察{PLANET_THEMES[planet]}的表达。"
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
            if kind == "god_pillar":
                text += f"在{key.split(':')[1]}柱可作为该柱位置的反思线索，不能代替全局分析。"
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
    return dict(
        id=f"kb:{system}:{kind}:{key}",
        system=system,
        kind=kind,
        key=key,
        synonyms=[],
        keywords=[key],
        theme_map=dict(self=valence, career=valence),
        text=text,
        source=source,
        license="本项目自写",
        reviewed=False,
        version=2,
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
