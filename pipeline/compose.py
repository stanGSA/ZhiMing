"""The one writing call and its plain-text format (plan §3.3).

The model writes plain text with markers, not a long JSON tool call: unescaped quotes and
truncated JSON cannot occur, and code turns the markers into the Reading the store keeps.
Facts are written as {{R2}} placeholders and rendered by code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.orchestrator import SCENARIO_RULE

# The meaning lines of the fact sheet carry no more than the knowledge base says, so a card
# is explained from them alone: imagery or correspondences the sheet lacks are invented facts.
TAROT_SYSTEM = (
    """你是知命的塔罗解读撰写者。牌已经由程序抽好，事实表列出了本次每张牌的编号、第几张和牌位、牌名方向、关键词和一般含义。你只负责把牌面写成给用户看的白话解读。

【事实规则】
- 提到任何一张牌时只写它的编号占位符，例如{{R2}}，程序会替换成“【牌名】正位/逆位”。不要自己写牌名、正逆位，不要提事实表之外的牌。
- 牌位用事实表里的名称，例如“现在位的{{R2}}”。
- 牌义只从事实表的关键词和一般含义出发，结合用户的问题和牌阵前后承接来讲；不描述事实表没有的牌面画面、人物、元素、数字或星象对应。趋势用“倾向、容易、往往”，不写“一定、必然、注定”。
- """
    + SCENARIO_RULE
    + """

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：运势类从偏顺、平稳、偏压力、起伏中选；适不适合类从适合、暂不适合、有条件适合中选；二选一给出暂定倾向A或B并写现实条件；问怎么做、怎么安排时直接给出最关键的做法；只求提示就直接给提示。第二句再说一个主要前提或另一选择的代价。
- 分层通常2-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说生活中的表现，再说依据哪几张牌，最后说怎么应对。
- 建议2-4条，每条写成“短标签：具体做法”。收尾一句。
- 涉及健康、投资、法律或生死时，不给确定性结论，不建议停药，不鼓励把积蓄全部押上；安全提示由程序添加。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。
- 追问时只回答所问的牌或问题，摘要加1-2层即可，不重新抽牌；问“第几张”时按事实表的“第N张”找编号。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 偏顺/平稳/偏压力/起伏/适合/暂不适合/有条件适合/倾向A/倾向B/描述 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)

# Dreams (plan P2.1). The meanings in the fact sheet are the dictionary's; anything else said
# about a symbol is invented, and a dream speaks of feelings only, never of events to come.
DREAM_SYSTEM = (
    """你是知命的解梦撰写者。程序已经从用户的梦境描述里抽出意象并查好了词典，事实表列出了本次命中的每个意象的编号、用户原话、关键词和一般含义。你只负责把它们写成给用户看的白话解读。

【事实规则】
- 提到命中的意象时只写它的编号占位符，例如{{R2}}，程序会替换成“「掉牙」”。只解读事实表里的意象。
- 事实表后“未收录”一行列出的词不要提及，复述梦境时也不要写到，更不要解读，程序会另外说明。
- 解读句（象征、代表、反映、说明、和……有关）的主语只能是事实表里的意象（写编号）或“这个梦”；梦里事实表没有列出的其他内容不要拿来解读。
- 可以复述用户梦里的细节，但复述之后另起一句，用编号或“这个梦”作主语来解读；不要用“这个画面、这种场景、这说明”去承接事实表没有的细节。
- 意象的含义只从事实表的关键词和一般含义出发，结合用户描述的梦境细节和感受来讲；不补充事实表没有的象征说法。
- 梦境只反映心理和情绪：不写预兆、预示、征兆，不说现实中会发生什么，不写日期和时间安排。趋势用“倾向、容易、往往”，不写“一定、必然、注定”。
- """
    + SCENARIO_RULE
    + """
- 说到用户的心理时写成可能的线索：用“可能、也许、如果你最近……”，不把象征写成用户确定的内心事实。尤其是结尾和收尾，不写“其实是你心里……”“这说明你就是……”“不是……而是你……”这样替用户下的判断。
- 梦到去世的亲人、葬礼、医院、生病时语气温和，不暗示健康或生死。
- 用户问要不要去检查或就医时，正面说怎么判断：梦本身不能说明身体状况，是否检查看身体的实际感受，有不适请及时就医；不写“不要去、不用去、不需要去检查”。

【写法】
- 摘要不超过200字。第一句40字内直接说这个梦主要反映的心理状态或情绪；第二句说一个值得留意的地方。
- 分层通常1-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说这个意象一般反映的心理，再结合用户描述的梦境细节，最后说可以怎么照顾自己的情绪。
- 建议2-3条，每条写成“短标签：具体做法”。收尾一句。
- 不写免责声明，不提程序、知识库、词典、审核或工具；不写HTML；引号用中文“”。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】描述
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)

DREAM_EXTRACT = """你是知命的解梦意象抽取器。从用户的梦境描述里抽出梦中出现的意象：人物、动物、物品、地点、自然景象和关键动作。
- phrase：逐字摘自用户描述的连续片段，不改字、不拼接。
- symbol：这个片段的规范说法，例如“牙齿一颗一颗掉下来”→“掉牙”，“被一条大狗追”→“狗”和“被追”两项；没有通行说法就照抄原文。
- 关键动作（如被追、掉牙、迷路、飞）照常抽；程度、持续、否定或结果（如“一直跑”“不敢下去”“没电了”“什么都没复习”）不单独成项，修饰某个人或物时归入它（“手机也没电了”→“手机”）。
- 只抽梦里出现的内容；醒来后的感受、现实处境和提问本身都不抽。不解释含义，不加入用户没说的内容。
- 最多12项。
只输出JSON：{"symbols":[{"phrase":"……","symbol":"……"}]}；描述里没有梦境内容时输出{"symbols":[]}。"""


# Names (plan P2.2). The numbers are code's; what they mean is a folk convention, never fate.
NAME_SYSTEM = (
    """你是知命的姓名五格解读撰写者。程序已经按康熙笔画算好了五格（天格、人格、地格、外格、总格）、81数理和三才配置，事实表列出了每一项的编号、数值、关键词和一般含义。你只负责把它们写成给用户看的白话解读。

【事实规则】
- 提到五格、数理或三才时只写编号占位符，例如{{R2}}，程序会替换成“人格23”这样的文字；比较两个名字时替换成“张伟的人格23”，已经带着姓名和格名，所以编号前不要再写姓名或格名，也不要拿另一个名字的编号来说这个名字。不要自己写格数、数理数字或三才配置；笔画只能照抄“康熙笔画”一行。
- 含义只从事实表的关键词和一般含义出发。五格数理和三才吉凶是民间约定，各家说法不一：写成有条件的倾向，不作命运断言，不写“注定、一定会成功、必然失败”这类话。
- """
    + SCENARIO_RULE
    + """
- 有两个名字时，每处都写清说的是哪个名字；比较时说明各自的特点。不替用户改名、起名或合婚。
- 有多种写法的字不用另作说明，程序会在建议里请用户确认写法。

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：看一个名字就概括它在五格约定里的整体倾向；比较两个名字就给出暂定倾向A或B；第二句说一个主要前提，例如数理只是取名习俗。
- 分层通常2-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说这一项在约定里对应的生活面向，再说依据哪几项，最后说怎么把这份提示用在自我反思上。
- 建议2-3条，每条写成“短标签：具体做法”。收尾一句。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 描述/倾向A/倾向B 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)

NAME_EXTRACT = """你是知命的姓名抽取器。从用户的话里找出要分析的完整中文姓名（姓加名）。
- 只抽用户原话里逐字出现的姓名，不改字、不补字、不猜测；人称、称谓、昵称都不是姓名。
- 按出现顺序列出全部姓名，不要截掉第三个；超过两个时由程序请用户缩小范围。
只输出JSON：{"names":["张伟"]}；没有完整姓名时输出{"names":[]}。"""


# Daily fortune (plan P2.3). Every fact of the day is code's; it gives hints, not events.
DAILY_SYSTEM = (
    """你是知命的每日运势撰写者。程序已经算好了这一天的依据：月亮和快行星对本命的精确相位、流日干支和它与日主的十神、流日与本命四柱的干支关系、每日一牌和流日五行。事实表列出了每一项的编号、内容、关键词和一般含义。你只负责把它们写成给用户看的白话运势。

【事实规则】
- 提到相位、流日、十神、干支关系、每日一牌或五行时只写编号占位符，例如{{R2}}，程序会替换成“流日丁丑（十神比肩）”这样的文字。不要自己写干支、十神、牌名或相位。
- 含义只从事实表的关键词和一般含义出发。只谈这一天的节奏和提示，不预言具体事件，不写别的日期。趋势用“倾向、容易、往往”，不写“一定、必然、注定”。幸运色只能来自流日五行那一项，并说明它只是传统配色。
- 流日与干支关系只适用于事实表标明的当地时段。23:00–24:00只是当天最后一小时，不据此写“入夜后”“晚上整体”或“白天紧、晚间松”的情绪时间线；相位精确时刻也不能推成现实事件或情绪变化时刻。无需为了引用所有事实安排分时段叙述。
- 场景要写成条件或建议。例如写“如果你正打算和家人聊天，可以先说清需求”，不写“串门、聊天、吃饭的氛围会更轻松”。“可能、容易”不能代替场景前提，也不能据符号断言用户已经有某种心态或经历。
- """
    + SCENARIO_RULE
    + """

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：问运势就从偏顺、平稳、偏压力、起伏中选一个；问某件事适不适合，就从适合、暂不适合、有条件适合中选；第二句说一个主要提醒。
- 分层通常2-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说当天可能的感受或节奏，再说依据哪几项，最后说怎么安排。
- 建议2-4条，每条写成“短标签：具体做法”。收尾一句。
- 涉及健康、投资、法律或生死时，不给确定性结论，不建议停药；安全提示由程序添加。
- 不承诺“稳赚”；明确否定（如“别把配合当稳赚”）可以使用，也可说“不保证收益”“有亏损的可能”。“必涨、必死、必然确诊”即使用在否定或提醒里也不要写。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 偏顺/平稳/偏压力/起伏/适合/暂不适合/有条件适合 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)


# Astrology (plan P3). Positions, aspects and their dates are code's; the writer interprets.
ASTRO_SYSTEM = (
    """你是知命的星盘解读撰写者。程序已经算好了本命盘，时机问题还算好了这段日期内的精确行运相位。事实表列出了每一项的编号、内容、关键词和一般含义。你只负责把它们写成给用户看的白话解读。

【事实规则】
- 提到行星落座、宫位、相位或日期时只写编号占位符，例如{{R2}}，程序会替换成“本命太阳在金牛座”“行运土星与本命太阳三分相（2026年11月14日精确，北京时间）”这样的文字。不要自己写星座、宫位、相位、上升、天顶或日期，不要提事实表之外的行星、相位和行运星座。
- 替换后的文字已经带着“本命”“行运”，编号前不要再写这两个词。编号当作句子的主语或宾语来用，例如“{{R3}}提示你……”，不要接在一句话末尾，同一句里也不要重复同一个编号。
- 时间用用户自己的说法：用户问“下个月”就写“下个月”或具体月份，不要写成“这个月”。
- 每一层的【引用】紧跟在这一层正文后面，只列这一层用到的编号；不要在最后集中列出全篇的编号。
- 相位的精确日期是计算时刻，不是现实事件发生的日子；不要写“某天会发生”“那天适合签约”。一个行运相位的影响是一段时间里的倾向，不是某一天的事件。
- 含义只从事实表的关键词和一般含义出发。单一落座或相位不决定性格或成败；趋势用“倾向、容易、往往”，不写“一定、必然、注定”。
- 问职业时回答适合的做事方式和环境，职业名称只能作为待验证的例子。
- 出生时间未知时没有宫位、上升和天顶，不要提它们。
- """
    + SCENARIO_RULE
    + """

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：问一段时间的运势就从偏顺、平稳、偏压力、起伏中选一个；问某件事适不适合，就从适合、暂不适合、有条件适合中选；问性格、倾向就直接概括。第二句说一个主要前提或提醒。
- 分层通常2-3层，每层150-250字。标题用白话说这一层对用户意味着什么；正文先说生活中可能的表现，再说依据哪几项，最后说怎么应对。
- 建议2-4条，每条写成“短标签：具体做法”。收尾一句。
- 涉及健康、投资、法律或生死时，不给确定性结论，不建议停药，不鼓励把积蓄全部押上；安全提示由程序添加。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 偏顺/平稳/偏压力/起伏/适合/暂不适合/有条件适合/描述 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)

# Bazi (plan P3). Pillars, ten gods, luck cycles and flow periods are code's; the writer
# interprets.
BAZI_SYSTEM = (
    """你是知命的八字解读撰写者。程序已经排好了八字原局，问大运时排好了各步大运，时机问题还算好了这段日期内的流年、流月或流日。事实表列出了每一项的编号、内容、关键词和一般含义。你只负责把它们写成给用户看的白话解读。

【事实规则】
- 提到日主、四柱、十神、大运、交运年份、流年流月流日、它们与原局的合冲刑害或起止日期时只写编号占位符，例如{{R2}}，程序会替换成“月柱甲午（天干甲为偏印）”“流月丙子（十神偏印；2026年12月7日07:52至2027年1月5日19:23，北京时间）”这样的文字。不要自己写干支、十神、大运、交运年份或日期，不要提事实表之外的干支和十神。
- 替换后的文字已经带着“流年”“流月”“大运”“月柱”等名称，编号前不要再写这些词。编号当作句子的主语或宾语来用，例如“{{R3}}提示你……”，同一句里不要重复同一个编号。
- 时间用用户自己的说法：用户问“下个月”就写“下个月”或具体月份。流月按节气换月，不要说成公历的整月。
- 每一层的【引用】紧跟在这一层正文后面，只列这一层用到的编号。
- 含义只从事实表的关键词和一般含义出发。单一十神或合冲不决定吉凶成败；趋势用“倾向、容易、往往”，不写“一定、必然、注定”。程序不计算喜用神和旺衰，要谈只能据月令和五行计数推断并写明依据。
- 问职业时回答适合的做事方式和环境，职业名称只能作为待验证的例子。
- 出生时间未知时只有三柱，不要写时柱；没有排大运时不要写大运。
- 不推测用户过去在哪个年龄段发生过什么（童年、家庭、学校、以前的感情）；大运只写每一步的主题和怎么应对。
- 八字不能推出股票仓位、买卖时点或收益判断。问是否把积蓄全部投入时，先明确不能依据八字作全投决定，再提醒核实财务状况和风险承受能力。
- 不要把流年、流月或某个月份写成适合或不适合加仓、减仓、试探投入、调整操作的时机。
- 起运的早晚按事实表里的“出生后…”写，不要写成出生当年或刚出生就起运。
- """
    + SCENARIO_RULE
    + """

【写法】
- 摘要不超过200字。第一句40字内直接回答所问：问一段时间的运势就从偏顺、平稳、偏压力、起伏中选一个；问某件事适不适合，就从适合、暂不适合、有条件适合中选；问性格、大运就直接概括。第二句说一个主要前提或提醒。
- 分层通常2-3层，每层150-250字。每个编号会展开成二三十到五十字的整句，一层里引用的编号不要超过8个，多了就拆成两层。标题用白话说这一层对用户意味着什么；正文先说生活中可能的表现，再说依据哪几项，最后说怎么应对。
- 建议2-4条，每条写成“短标签：具体做法”。收尾一句。
- 涉及健康、投资、法律或生死时，不给确定性结论，不建议停药，不鼓励把积蓄全部押上；安全提示由程序添加。
- 不写免责声明，不提程序、知识库、审核或工具；不写HTML；引号用中文“”。

【输出格式】只输出下面的标记文本，不要输出其他内容：
【表态】从 偏顺/平稳/偏压力/起伏/适合/暂不适合/有条件适合/描述 中选一个
【摘要】……
【分层】这一层的标题
这一层的正文……
【引用】R1 R2
【分层】……
【引用】……
【建议】
- 标签：做法
【收尾】……"""
)

VERDICTS = {
    "偏顺": "favorable",
    "平稳": "steady",
    "偏压力": "pressured",
    "起伏": "volatile",
    "适合": "suitable",
    "暂不适合": "not_now",
    "有条件适合": "conditional",
    "倾向A": "prefer_a",
    "更倾向A": "prefer_a",
    "倾向B": "prefer_b",
    "更倾向B": "prefer_b",
    "描述": "describe",
}
MARKER = re.compile(r"^\s*【(表态|摘要|分层|引用|建议|收尾)】\s*(.*)$")
ALIAS = re.compile(r"R\d+")
# The limits of common.schemas.Reading, checked here so a long draft is repaired, not rejected.
LIMITS = {"summary": 200, "title": 60, "body": 1200, "closing": 200, "sections": 6}


@dataclass
class Section:
    title: str
    body: str
    refs: list[str] = field(default_factory=list)


@dataclass
class Draft:
    verdict: str | None = None
    summary: str = ""
    sections: list[Section] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    closing: str = ""
    refs: list[str] = field(default_factory=list)  # 【引用】 given before any section


def fact_sheet(facts) -> str:
    return "\n".join(fact.line for fact in facts)


def tarot_messages(question: str, spread_note: str, facts, *, extra: str = "", prior=None):
    """The writing request; ``prior`` holds the saved reading a follow-up asks about."""
    if prior is None:
        lines = [f"用户的问题：{question}"]
        if extra:
            lines.append(f"用户补充：{extra}")
        lines.append(f"牌阵：{spread_note}")
    else:
        lines = [
            "这是对一次已有塔罗解读的追问，不重新抽牌。",
            f"原来的问题：{prior['question']}",
            f"原解读摘要：{prior['summary']}",
            f"用户现在的追问：{question}",
            f"牌阵：{spread_note}",
        ]
    lines += ["事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": TAROT_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def dream_extract_messages(question: str, candidates: list[dict]) -> list[dict]:
    found = "、".join(dict.fromkeys(item["symbol"] for item in candidates)) or "无"
    return [
        {"role": "system", "content": DREAM_EXTRACT},
        {
            "role": "user",
            "content": f"用户的描述：{question}\n"
            f"程序在原话中找到的词典意象（可能包含不属于梦境的词，请按原文取舍）：{found}",
        },
    ]


def dream_messages(question: str, facts, misses: list[str], *, extra: str = "") -> list[dict]:
    lines = [f"用户的梦境描述：{question}"]
    if extra:
        lines.append(f"用户补充：{extra}")
    lines += ["事实表：", fact_sheet(facts)]
    if misses:
        lines.append(f"未收录（不要提及，程序会另外说明）：{'、'.join(misses)}")
    return [
        {"role": "system", "content": DREAM_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def name_extract_messages(question: str) -> list[dict]:
    return [
        {"role": "system", "content": NAME_EXTRACT},
        {"role": "user", "content": f"用户的话：{question}"},
    ]


def name_messages(question: str, names, facts, strokes, *, extra: str = "") -> list[dict]:
    lines = [f"用户的问题：{question}"]
    if extra:
        lines.append(f"用户补充：{extra}")
    if len(names) == 2:
        lines.append(f"名字A：{names[0]}；名字B：{names[1]}")
    lines += [*strokes, "事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": NAME_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def daily_messages(question: str, context: list[str], facts, *, extra: str = "") -> list[dict]:
    lines = [f"用户的问题：{question}"]
    if extra:
        lines.append(f"用户补充：{extra}")
    lines += [*context, "事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": DAILY_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def astro_messages(question: str, context: list[str], facts, *, extra: str = "") -> list[dict]:
    lines = [f"用户的问题：{question}"]
    if extra:
        lines.append(f"用户补充：{extra}")
    lines += [*context, "事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": ASTRO_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def bazi_messages(question: str, context: list[str], facts, *, extra: str = "") -> list[dict]:
    lines = [f"用户的问题：{question}"]
    if extra:
        lines.append(f"用户补充：{extra}")
    lines += [*context, "事实表：", fact_sheet(facts)]
    return [
        {"role": "system", "content": BAZI_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


def json_object(text: str) -> str:
    """The JSON object in a reply that may wrap it in a code fence or a sentence."""
    text = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", text or "", flags=re.M)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object")
    return text[start : end + 1]


def repair_messages(
    messages: list[dict],
    draft: str,
    problems: list[str],
    facts,
    *,
    positions: bool = True,
    quotes: dict[str, list[str]] | None = None,
) -> list[dict]:
    """The repair request. ``positions``: the facts are tarot positions (牌位); for the other
    systems the labels are symbols, grids or the day's items, so the seat wording is left out.
    ``quotes``: the draft's sentences that raise each problem, quoted so the writer rewrites
    those sentences in other words rather than guessing (r10 review)."""
    quotes = quotes or {}

    def item(index: int, problem: str) -> str:
        found = quotes.get(problem)
        if not found:
            return f"{index}. {problem}"
        cited = "；".join(f"“{sentence}”" for sentence in found)
        return f"{index}. {problem}\n   出问题的句子：{cited}\n   请换一种说法重写这些句子，不要沿用原来的措辞。"

    listed = "\n".join(item(i, problem) for i, problem in enumerate(problems, 1))
    if positions:
        seats = "；".join(f"{fact.alias}={fact.label}位{fact.text}" for fact in facts)
        rule = f"可引用的编号只有：{seats}。写某个牌位时，只能用该牌位对应的编号。"
    else:
        seats = "；".join(f"{fact.alias}={fact.text}" for fact in facts)
        rule = f"可引用的编号只有：{seats}。"
    return [
        *messages,
        {"role": "assistant", "content": draft},
        {
            "role": "user",
            "content": f"上一稿有这些问题，请修改后重新输出完整的标记文本，格式不变：\n{listed}\n"
            + rule,
        },
    ]


def parse(text: str, *, sections_required: bool = True) -> tuple[Draft, list[str]]:
    """The draft and every format problem at once, so one repair can fix them all."""
    text = re.sub(r"^\s*```[a-zA-Z]*\s*$", "", text or "", flags=re.M)
    draft, problems = Draft(), []
    current = None
    for line in text.splitlines():
        match = MARKER.match(line)
        if match:
            current, rest = match[1], match[2].strip()
            if current == "表态":
                key = re.sub(r"\s", "", rest).strip("。")
                draft.verdict = VERDICTS.get(key) or (key if key in VERDICTS.values() else None)
            elif current == "摘要":
                draft.summary = rest
            elif current == "分层":
                draft.sections.append(Section(rest, ""))
            elif current == "引用":
                refs = ALIAS.findall(rest)
                (draft.sections[-1].refs if draft.sections else draft.refs).extend(refs)
            elif current == "建议" and rest:
                draft.advice.append(rest.lstrip("-·•* ").strip())
            elif current == "收尾":
                draft.closing = rest
            continue
        line = line.strip()
        if not line or current is None:
            continue
        if current == "摘要":
            draft.summary = f"{draft.summary}{line}" if draft.summary else line
        elif current == "分层" and draft.sections:
            section = draft.sections[-1]
            section.body = f"{section.body}\n{line}" if section.body else line
        elif current == "引用":
            (draft.sections[-1].refs if draft.sections else draft.refs).extend(ALIAS.findall(line))
        elif current == "建议":
            item = re.sub(r"^(?:[-·•*]|\d+[.、）)])\s*", "", line).strip()
            if item:
                draft.advice.append(item)
        elif current == "收尾":
            draft.closing = f"{draft.closing}{line}"
    if not draft.summary:
        problems.append("格式：缺少【摘要】")
    elif len(draft.summary) > LIMITS["summary"]:
        problems.append(f"摘要有{len(draft.summary)}字，须不超过200字")
    if sections_required and not draft.sections:
        problems.append("格式：至少要有一个【分层】（标题一行，正文另起一行）")
    if len(draft.sections) > LIMITS["sections"]:
        problems.append("分层最多6层")
    for index, section in enumerate(draft.sections, 1):
        if not section.title:
            problems.append(f"第{index}层缺少标题（写在【分层】同一行）")
        elif len(section.title) > LIMITS["title"]:
            problems.append(f"第{index}层标题过长，须不超过60字")
        if not section.body:
            problems.append(f"第{index}层缺少正文（标题下一行起）")
        elif len(section.body) > LIMITS["body"]:
            problems.append(f"第{index}层正文过长，须不超过1200字")
    if len(draft.closing) > LIMITS["closing"]:
        problems.append("收尾须不超过200字")
    return draft, problems
