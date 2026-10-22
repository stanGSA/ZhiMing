"""The knowledge review rubric: what both reviewers judge, with the anchors they share.

Version 1 (the 2026-10-21 campaign) named the dimensions only. Its reviewers then applied
different standards on the same content: one wanted object-specific facts for bazi, narrow
dream synonyms and folk-convention wording for name; the other did not, and misremembered
the tail-digit rule. Version 2 states those standards as anchors and quotes the reference
facts from this project's own tables, so a reviewer checks an entry against the convention
the application computes with, not against a remembered school. Changing any of this text
changes ``rubric_sha256``, so a pre-registered campaign can tell which rubric it ran under.
"""

from __future__ import annotations

from lunar_python.util import LunarUtil

from plugins.astro.calculator import BODY_ZH, SIGN_ZH, SIGNS
from plugins.bazi.calculator import GROUP_RELATIONS, PAIR_RELATIONS, SELF_PUNISHMENT
from plugins.name.wuge import CONTROLS, ELEMENTS, GENERATES
from scripts.draft_tarot import MAJOR_THEMES, SUIT_THEMES
from scripts.draft_week6 import DAY_COLORS, LUCKY, MIXED
from scripts.draft_week23 import DIGNITY, HOUSE_TEXT, HOUSE_THEME

THEME_ZH = dict(self="自我状态", career="事业", relationship="感情关系", finance="财务")
SUIT_ZH = dict(wands="权杖", cups="圣杯", swords="宝剑", pentacles="星币")


def _themes(themes) -> str:
    return "、".join(THEME_ZH[t] for t in themes)


RUBRIC_VERSION = 5

ANCHORS = """判定锚点（两位审核员使用同一套锚点；锚点与“参考事实”优先于个人习惯或记忆中的其他流派）：
A. 具体问题：只因能指出具体句子或字段的问题判 revise 或 reject，并在 issues 中写明位置；“还可以写得更好”“可以补充更多内容”不构成 revise。
B. 方向：theme_map 非零值的正负须与文字表达的倾向一致（偏顺为正、偏阻为负）；该主题须能从文字的含义或本体系的方向约定（见参考事实）中看出，不要求出现固定词语。既不能从文字看出、也不属于约定的主题标了方向，判 revise。0 表示没有方向，与中性文字相容，不能因为“本可以标方向”判 revise。
C. 对象专属：术语与规则类条目（天干地支、藏干、干支关系、十神、五行、宫位、相位、数理、三才、牌位、约定）必须写出该对象区别于同类对象的核心信息（例如某地支的五行与藏干、某种组合由哪些成员构成）；只有通用提醒或方法说明、换成同类其他对象也同样成立的文字，判 revise。牌义、意象等象征类条目只要核心含义与该对象的传统象征相符即可，不要求写出全部细节。免责与方法说明可以存在，但不能代替核心信息。
D. 参考事实：与下方参考事实一致的内容不得判为错误；与参考事实不符判 revise。单个成员、属性或对应五行写错属于可修正事实错误，判 revise；只有主体整体换成另一对象、主定义或全文与 key 不符才判 reject（医疗/投资/法律确定性结论仍按 reject）。参考事实没有覆盖、各流派说法不一的细节，只要条目没有写成唯一定论，不算错误。
E. 民间约定：吉凶、顺逆等评价写明是民间约定、传统说法或象征解释即可，不要求每句重复；把评价写成客观事实或对个人现实的推断（如“这种配置的人事业顺利”）判 revise。
F. 预测：除“必然、注定、一定会”等确定性词语外，“预示、将会、近期会”等对现实事件的预测同样判 revise；“不代表事件必然发生”这类否定式免责声明不算预测。
G. 逐字段核对：给结论前须核对每个非零主题的主题依据和正负倾向、每个 synonyms 的同义关系、以及文中每个涉及参考表的事实。不能用“整体合理”“没有明显矛盾”代替这些核对。主题与文字必须存在支持关系：“压力、需要、选择、困局、资源”等泛词不能自动支持任意事业或财务方向；只需核实风险、安排沟通等建议，不能把原本偏顺的核心描述改读成偏阻。无主题依据或正负相反即 revise。正文温和、加了免责、甚至正文提醒了某种额外情节要另看，也不能消除 synonyms 中混入该情节的错误。reason 必须与 verdict 一致，指出方向不符或错误别名时不得判 pass。
H. 语义范围：keywords 是主题索引，可以包含正文所解释或否定推断的主题，例如“不能据此判断喜忌”与关键词“喜忌”相容，不代表正文作出喜用神结论；涉及具体五行、干支等事实的关键词仍须正确。synonyms 仍须为同义表达。不能把“不表示X”“不能据此判断X”误读为正在主张X。方向衡量条目象征解读的偏顺/偏阻，不要求预测现实；明确描述工作协作摩擦、推进受限，可支持事业负向反思，结尾否定现实预言不会抹去这层象征含义。只作泛化提醒、没有相关主题含义时仍应标0。"""

RUBRIC = (
    """你是知识库释义的审核员。项目是一个占卜/自我反思应用，释义是项目自写的草稿，面向普通用户。
请逐条独立判断，只依据条目本身、下方判定锚点与参考事实，不要猜测其他审核员的意见。

字段说明：kind/key 标明条目对象；text 是给用户看的释义；theme_map 是四个主题
（self 自我状态、career 事业、relationship 感情关系、finance 财务）的倾向值，范围 -1 到 1，
正数偏顺、负数偏阻，0 表示该主题没有方向。只审方向与相对大小是否与文字一致，不审具体数值。
counterpart（若有）是同一张塔罗牌另一方向的释义，只作对照，不需要给它结论。

通用维度：
1. tradition：核心含义符合参考事实与主流传统，没有把对象写错（如牌名、十神、五行、行星、星座、宫位）。
2. theme_direction：theme_map 的正负方向与释义文字一致。
3. certainty：没有宿命化、确定性断言或对现实事件的预测。否定式免责声明（如“不代表事件必然发生”）不算。
4. medical_legal_finance：没有医疗诊断、投资或法律方面的确定性结论。
5. plain_language：术语附带的白话解释准确，没有误导。
6. copying：不疑似照抄古籍整理版、现代书籍或网站原文（只能标“疑似”）。
7. consistency：与 key、同义词、关键词不矛盾，不与同类条目重复。

"""
    + ANCHORS.replace("{", "{{").replace("}", "}}")
    + """
{system_rubric}

结论：
- pass：可以原样作为面向用户的草稿释义使用。
- revise：有可以修正的具体问题（方向与文字不一致、措辞宿命化、白话不准、同义词会误命中等）。
- reject：核心含义错误、文字与 key 不符、疑似抄录，或含医疗/投资/法律确定性结论。

只输出一个 JSON 对象，不要输出其他文字：
{{"items": [{{"item": "<条目编号>", "verdict": "pass|revise|reject",
  "issues": [{{"dimension": "<维度名>", "detail": "<问题>"}}], "reason": "<一句话理由>"}}]}}
每个条目编号恰好出现一次；verdict 为 pass 时 issues 为空列表。"""
)


def _dignity() -> str:
    rows = []
    for planet, tables in DIGNITY.items():
        terms = [
            f"{SIGN_ZH[SIGNS.index(sign)]}{term}"
            for table in tables
            for sign, term in table.items()
        ]
        rows.append(f"{BODY_ZH[planet]}：{'、'.join(terms)}")
    return "；".join(rows)


def _bazi() -> str:
    stems = "".join(LunarUtil.WU_XING_GAN)
    yang = "".join(stems[0::2])
    by_element = {}
    for branch, element in LunarUtil.WU_XING_ZHI.items():
        by_element.setdefault(element, []).append(branch)
    branches = "，".join(f"{''.join(v)}属{k}" for k, v in by_element.items())
    hidden = "；".join(f"{b}藏{'、'.join(s)}" for b, s in LunarUtil.ZHI_HIDE_GAN.items())
    hidden += "（各家列举顺序不同，只审成员，不审顺序）"
    pairs = "；".join(f"{kind} {'、'.join(p)}" for kind, p in PAIR_RELATIONS.items())
    groups = "；".join(
        f"{kind} " + "、".join(f"{g}（{LunarUtil.WU_XING_ZHI[g[1]]}）" for g in members)
        for kind, members in GROUP_RELATIONS.items()
    )
    stem_elements = {}
    for stem, element in LunarUtil.WU_XING_GAN.items():
        stem_elements.setdefault(element, []).append(stem)
    return (
        f"天干五行 {'，'.join(''.join(v) + k for k, v in stem_elements.items())}；"
        f"{'、'.join(yang)}为阳，其余为阴。地支五行 {branches}。地支藏干 {hidden}。"
        "十神以日主为“我”：同我者，阴阳相同为比肩、相异为劫财；我生者，同为食神、异为伤官；"
        "我克者，同为偏财、异为正财；克我者，同为七杀、异为正官；生我者，同为偏印、异为正印。"
        f"{pairs}；自刑 {'、'.join(SELF_PUNISHMENT)}；{groups}。"
    )


def _name() -> str:
    digits = "，".join(
        f"{a}、{(b % 10)}{element}"
        for element, (a, b) in zip(ELEMENTS, ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10)), strict=True)
    )
    level = lambda numbers: "、".join(map(str, sorted(numbers)))  # noqa: E731
    return (
        f"三才取天格、人格、地格各自尾数定五行：{digits}。"
        f"相生 {'、'.join(f'{a}生{b}' for a, b in GENERATES.items())}；"
        f"相克 {'、'.join(f'{a}克{b}' for a, b in CONTROLS.items())}。"
        f"81数理三档归类（本项目采用的五格剖象法民间约定，超过81减80）：吉 {level(LUCKY)}；"
        f"半吉 {level(MIXED)}；其余为凶。各家对少数数字归类不同，与本项目归类一致即不算错。"
    )


def _daily() -> str:
    colors = "；".join(f"{e} {text.split('传统配色为')[1]}" for e, (_, text) in DAY_COLORS.items())
    return f"五行配色（传统约定）{colors}。"


SYSTEM_RUBRIC = {
    "tarot": "塔罗：正位、逆位含义区分清楚（结合 counterpart 判断）。逆位不必与正位相反，"
    "可以是同一主题的减弱、受阻或内化，方向与正位相同也可以成立，只要与本条文字一致。"
    "方向约定（按约定标出的主题不必在文字中逐一写明）：大阿卡纳作用于"
    + _themes(MAJOR_THEMES)
    + "；"
    + "；".join(f"{SUIT_ZH[suit]}作用于{_themes(t)}" for suit, t in SUIT_THEMES.items())
    + "；正负随牌义倾向。约定以外的主题标了方向须能从文字看出。"
    "牌位条目（kind=position）的含义以 spread_positions 给出的牌阵定义为准。",
    "astro": "占星：行星、星座、宫位、相位的基本性质准确；行星落座、落宫的主题方向与文字一致。"
    "行星象征条目写出准确的核心主题即已区分对象，例如金星的价值取舍与关系协调、水星的信息理解与沟通、"
    "冥王星的权力边界与深层转变；不要求列全爱、美、交易、控制等全部联想。附职业探索例子不会抹去"
    "已经写出的核心信息；提到职业但没有偏顺或偏阻时，方向全0可以通过，不能以篇幅占比判偏题。"
    "参考事实：十二宫主题（本项目约定）"
    + "；".join(f"第{i}宫{text}" for i, text in enumerate(HOUSE_TEXT, 1))
    + "。传统尊贵（本项目采用的表；入庙、擢升为强，失势、落陷为弱）"
    + _dignity()
    + "。表中未列出的行星与星座组合不按尊贵判断；天王星、海王星、冥王星属现代占星，不在传统尊贵表中。"
    "方向约定（按约定标出的主题不必在文字中逐一写明）："
    + "、".join(f"第{h}宫可标{THEME_ZH[t]}" for h, t in HOUSE_THEME.items())
    + "；其他方向须能从文字看出。",
    "bazi": "八字：不把冲合刑害说成灾祸；十神对感情、财运的方向与文字一致；本项目不计算喜用神，"
    "条目不应据五行数量下旺衰或喜用神结论。方向约定（按约定标出的主题不必在文字中逐一写明）："
    "十神（含柱位十神）的自我状态、事业方向可随该十神主题的倾向标出；其他方向须能从文字看出。"
    "正反例：写出“某地支的藏干为甲、丙、戊”或“某组合由哪三个地支构成”是对象专属信息（pass）；"
    "只说“按传统表确定”而不写出成员的判 revise；术语条目的文字为说明适用范围提到事业、关系，"
    "而 theme_map 为 0，两者相容（pass）。阴/阳、柔韧/刚直是性质描述，本身不等于偏阻/偏顺；例如阴木文字只写柔韧伸展却标 self 负值，缺少负向依据（revise），不能因为阴柔就推断弱势。地支刑的文字明确以自我苛责/反复纠结、工作约束/协作摩擦阻碍推进作象征反思，可分别支持 self/career 负值；声明不预测现实事件不影响这些方向。参考事实："
    + _bazi(),
    "name": "姓名：81 数理与三才的吉凶写成民间约定，不作命运断言。"
    "先核实事实再作评价：数理释义同时介绍吉凶分类与尾数配属并不构成错误；“28尾数8对应金”符合参考表，"
    "仅陈述数的五行配属并不声称只凭28就能判断整个三才，也不声称尾数是吉凶分类的依据。不得自行加上"
    "正文没有作出的这类推论再否决。"
    "方向约定（按约定标出的主题不必"
    "在文字中逐一写明）：数理条目可按吉、半吉、凶对四个主题统一标为正、小正、负；三才条目的自我状态"
    "可随天格与人格的关系、感情关系可随人格与地格的关系、事业可随两者合计（相生、比和偏顺，相克偏阻）；"
    "文字另有限定时可以偏离约定或标 0；约定以外的方向须能从文字看出。"
    "正反例：“某数在民间约定中常被归为吉”（pass）；“某数是吉数，用这个数的人事业顺利”"
    "（revise，评价写成了客观推断）；结尾已写明“数理是取名习俗”，前文不必逐句重复（pass）。"
    "参考事实：" + _name(),
    "dream": "解梦：同义词是检索别名——用户描述梦境时说出这个词，所指必须是同一个意象"
    "（同一事物或动作的常见说法、近义词、程度不同但意象相同的说法，如“暴雨”之于“下雨”、"
    "“跪下”之于“下跪”）；不同事物（“护士”之于“医生”）、上位泛称（“瑞兽”之于“麒麟”）、"
    "只是场所或事件的词（“考场”之于“考试”）、常见的其他义项（“想不开”之于“自杀”）"
    "不能作同义词，缺少某个同义词不算问题。方向须能从意象的联想文字中看出。"
    "同类具体类型或程度可以归入同一意象（如台灯之于灯、暴雨之于下雨），但相邻对象、属性、"
    "症状及额外事件情节不因相关就成为同义词：灯光是光线而不是灯具，发烧是症状而不是患病状态，"
    "出轨限定了亲密关系不忠情节而一般背叛没有这层限定。前者允许，后者须移出synonyms或改成独立意象。"
    "这是一项必须逐词执行的条件：某物破损是不同情节，狐狸精是精怪或对人的贬称，均不能因正文释义"
    "整体合理而放行。0方向允许中性提及多个话题；非零则需要该主题的明确含义，普通困局并不自动指工作，"
    "团圆与照顾并不自动表示财务受阻。"
    "不写预兆；死亡、疾病、怀孕等敏感意象措辞平和。",
    "daily": "每日运势：配色、种子等写成约定，不暗示带来实际运气。每日运势条目按本项目约定一律"
    "保持中性（theme_map 全为 0），方向来自其他体系；出现非零方向判 revise。参考事实：" + _daily(),
}

REVISE_PROMPT = """你负责按审核意见修改一条知识库释义草稿。只修改 text、theme_map、synonyms、keywords；
不能改变条目对象（kind/key）。theme_map 只用 self、career、relationship、finance 四个主题，范围 -1 到 1，
0 表示没有方向。不写宿命化、确定性断言，不写医疗、投资、法律结论。修改结果会由两家审核模型按下方
判定锚点与参考事实重新审核；只修正审核意见指出的具体问题，不做无关改写。
只输出一个 JSON 对象：{"text": "...", "theme_map": {...}, "synonyms": [...], "keywords": [...],
"note": "<改了什么>"}"""


def revise_prompt(system: str) -> str:
    return f"{REVISE_PROMPT}\n\n{ANCHORS}\n{SYSTEM_RUBRIC.get(system, '')}"
