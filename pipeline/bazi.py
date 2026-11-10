"""Bazi in the pipeline: the natal chart, the luck cycles and flow periods over a range (plan P3).

Code decides what a calculation needs (pipeline/requirements.py, the bazi rows): the birth data,
the gender a luck-cycle question needs, the range of a timing question and its granularity.
What is missing is asked with a templated question that ends the turn; the next message resumes
the run. The calculators keep their own confirmations (an overseas birth's solar-time choice, a
Xinjiang birth clock, a lunar leap month, an unknown hour on the day of a solar term): their
NeedsInput becomes the same kind of question, and the answer is read by the same input_evidence
functions the tools use. The planned calls are compute_bazi and, for a timing question,
compute_bazi_period, both through the Guard.

The writer cites the day master, pillars, ten gods, luck cycles and flow periods by number only;
what it writes by hand is checked against the calculation (P3.4): stem-branch pairs, the day
master, a ten god named for a pillar, a luck cycle named as the first, current or n-th one, a
handover year, and a relation between a pillar and the natal chart.

Left with the agent loop: follow-ups to a saved reading, corrections of birth data, techniques the
calculator does not have (合婚, 紫微, 神煞…) and questions that also name another system.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from common.facts import value_claim
from common.input_evidence import DATE as BIRTH_DATE
from common.input_evidence import clock_in, gender_evidence
from common.time_utils import NeedsInput
from common.validation import HIGH_RISK, RISKS
from harness.failures import failure
from harness.refs import short
from pipeline import birth, compose, requirements
from pipeline.astro import BIRTH_MENTION, COMPARED, RELATIVE, chinese, relative_span
from pipeline.factsheet import CAVEAT, Fact, shorten
from pipeline.intent import CONTINUE, Intent
from pipeline.render import safety_for
from pipeline.state import RESUMABLE, snapshot
from pipeline.system import System
from plugins.bazi.calculator import relations, ten_god

BAZI = re.compile(
    r"八字|四柱|命盘|命局|命理|排盘|日主|日元|十神|大运|流年|流月|起运|交运|首运|"
    r"喜用神?|五行(?:缺|旺|弱|强|分布|属性)"
)
OTHER = re.compile(
    r"塔罗|牌阵|抽[一二两三]?张|[一二两三单]张牌|星盘|占星|星座|行运|本命盘|上升星座|"
    r"姓名|名字|五格|解梦|梦见|梦到|做梦|每日运势|今日运势|今天运势"
)
# What compute_bazi and compute_bazi_period do not calculate.
UNSUPPORTED = re.compile(
    r"合婚|合八字|八字合|配对|两个人|夫妻宫|紫微|斗数|六爻|奇门|梅花|称骨|神煞|胎元|命宫|身宫|"
    r"纳音五行合|小运|流时|时辰吉凶|择日|改名"
)
REFERS_TO_READING = re.compile(
    r"(?:上一条|上一次|上次|刚才|之前|前面|那次|原来)(?:那个|这个|那次|那条|的)?"
    r"(?:八字|命盘|解读|记录|分析|结果)|原记录|[这那]段解读|(?:你|刚才)(?:说|提到)的"
)
BIRTH_CORRECTION = re.compile(
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单|生辰).{0,16}"
    r"(?:更正|改成|改为|记错|不准确|不对)|"
    r"(?:更正|改成|改为|记错|不准确|不对).{0,16}"
    r"(?:出生(?:日期|时间|时刻|地点|资料|信息)|出生信息|出生表单|生辰)"
)
# The gender the user states for themselves (“我是女生”“性别男”); 女朋友 or 男同事 is not one.
GENDER_STATED = re.compile(
    r"(?:我是|我为|本人|本人是|性别(?:是|为|：|:)?\s*)(?:一[个名位])?\s*"
    r"(?P<gender>男|女)(?:性|生|士|孩|的)?(?![朋同友儿婿人方家])"
)
LEAP = re.compile(r"闰[正冬腊一二三四五六七八九十]+月")
REGULAR = re.compile(r"普通月|非闰|不是闰|不闰|regular")
PHYSICAL = re.compile(r"physical|物理时刻起运")
UNCERTAIN = re.compile(r"候选|两种|仍不知道")
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ELEMENT = dict(zip(STEMS, "木木火火土土金金水水", strict=True))
# 己 in 自己 is no stem, as plugins/bazi/validation.py reads it.
STEM = r"(?:[甲乙丙丁戊庚辛壬癸]|(?<!自)己)"
JIAZI = rf"{STEM}[{BRANCHES}]"
GANZHI = re.compile(JIAZI)
TEN_GODS = ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")
TEN_GOD = re.compile("|".join(TEN_GODS))
PILLAR_ZH = {"year": "年柱", "month": "月柱", "day": "日柱", "time": "时柱"}
PILLAR_KEY = {"年": "year", "月": "month", "日": "day", "时": "time"}
FLOW_ZH = {"year": "流年", "month": "流月", "day": "流日"}
FLOW_KEY = {"流年": "year", "流月": "month", "流日": "day"}
# Negations that turn a denial back into a statement: “不能说日主不是乙木” states 乙木.
OUTER = re.compile(
    r"不能说|不可能|不会|不应|不该|未必|不一定|谈不上|说不上|很难说|难说|不代表|不等于|"
    r"并不意味|不见得|怎么会|岂"
)
# A degree word between the negation and the value (“不完全是”): neither a plain statement
# nor a plain denial, so it is checked both ways.
HEDGED = re.compile(r"(?:不|没|并非|并不)(?:完全|全然|一定|绝对|根本|全)是?\s*$")
CLAUSE_BREAK = "，,。；;！!？?\n"
# What follows a value in a denied inference: “并不是丁火日主都外向”“不是七杀就一定压力大”.
INFERENCE = re.compile(
    r"[木火土金水]?(?:日主|日元|大运|格)?(?:的)?(?:人)?(?:都|就|一定|必然|必定|未必|便)"
)
# Words between a pillar and the ten god named for it: “月柱癸巳根本不是七杀”.
FUNCTION_TAIL = re.compile(
    r"(?:的|天干|十神|就|也|都|却|其实|确实|并|根本|完全|全然|绝对|是|为|属于|属|当令|当值|"
    r"透出|带|：|:|即|不|非|而|\s)$"
)
# The governing negations common.facts.NEGATED_VALUE reads, found anywhere in the clause.
NEGATION = re.compile(r"不是|并不是|并非|而非|不再是|不在|并不在|没在|未在")
RELATION_WORD = (
    r"天干五合|天干合|天干相冲|天干冲|地支六合|六合|相合|合|地支相冲|地支冲|相冲|冲|"
    r"地支相刑|相刑|自刑|刑|地支相害|相害|害|地支相破|相破|破"
)
RELATION_KINDS = {
    "合": {"天干合", "地支六合"},
    "冲": {"天干冲", "地支冲"},
    "刑": {"地支刑", "自刑"},
    "害": {"地支害"},
    "破": {"地支破"},
}
NATAL_SIDE = r"(?:本命|原局|命局|出生)?的?(?P<natal>[年月日时])(?:柱|干|支)(?P<ngz>{JIAZI})?"
RELATION_AFTER = re.compile(
    rf"(?P<subject>(?:流年|流月|流日|大运)?{JIAZI}|流年|流月|流日)(?:的)?(?:天干|地支)?"
    rf"(?:与|和|跟|同)"
    + NATAL_SIDE.format(JIAZI=JIAZI)
    + rf"(?:之间)?(?P<between>[^，,。；;！!？?\n]{{0,8}}?)(?P<kind>{RELATION_WORD})"
)
RELATION_BEFORE = re.compile(
    rf"(?P<subject>(?:流年|流月|流日|大运)?{JIAZI}|流年|流月|流日)(?P<between>[^，,。；;！!？?\n与和跟同]{{0,6}}?)"
    rf"(?P<kind>合|冲|刑|害|破)(?:住|动|到|了)?" + NATAL_SIDE.format(JIAZI=JIAZI)
)
# “……，与日柱也相合”: a clause that names only the natal side keeps the sentence's subject.
RELATION_CARRY = re.compile(
    r"[，,]\s*(?:又|也|还|并且|而且)?(?:与|和|跟|同)"
    + NATAL_SIDE.format(JIAZI=JIAZI)
    + rf"(?:之间)?(?P<between>[^，,。；;！!？?\n]{{0,8}}?)(?P<kind>{RELATION_WORD})"
)
NATAL_SCOPE = re.compile(r"命局|原局|八字|四柱|命里|命中|命盘")
ABSENT = re.compile(r"(?:没有|没|无|缺少|缺)\s*$")
RELATION_DENIED = re.compile(r"不|没|未|并非|无")
DOUBLE_DENIAL = re.compile(r"不是不|并非不|不会不|没有不|并不是不")
# A negation may stand between the label and the value; claim() reads it.
DENIAL = r"(?:(?:根本|完全|并|也|就)?(?:不是|并非|而非|不)(?:完全|全然|一定|绝对)?){0,2}"
NATAL_PILLAR = re.compile(
    rf"(?<![流第步])(?:本命|原局|出生)?的?(?P<name>[年月日时])柱\s*{DENIAL}(?:是|为|：|:)?\s*(?P<gz>{JIAZI})"
)
DAY_MASTER = re.compile(
    rf"(?:日主|日元|日干)\s*{DENIAL}(?:是|为|属于|属|：|:)?\s*(?P<stem>{STEM})|"
    rf"(?P<before>{STEM})[木火土金水]?(?:日主|日元)"
)
STEM_ELEMENT = re.compile(rf"(?P<stem>{STEM})(?P<element>[木火土金水])(?![日月年时柱])")
SUBJECT = re.compile(
    rf"(?P<label>首步大运|第一步大运|首运|第[一二三四五六七八九十\d]+步大运|当前大运|目前大运|现在的大运|"
    rf"大运|流年|流月|流日|[年月日时](?:柱|干))?的?(?P<gz>{JIAZI})?(?:天干)?(?:[{STEMS}])?$"
)
FIRST_DAYUN = re.compile(
    rf"(?:首步大运|第一步大运|首运)\s*{DENIAL}(?:是|为|：|:|走)?\s*(?P<gz>{JIAZI})"
)
NTH_DAYUN = re.compile(
    rf"第(?P<n>[一二三四五六七八九十\d]+)步大运\s*{DENIAL}(?:是|为|：|:|走)?\s*(?P<gz>{JIAZI})"
)
PRESENT = r"(?:当前|目前|现在|眼下|如今|当下)"
CURRENT_DAYUN = re.compile(
    rf"(?:{PRESENT}|正在走)(?:所处|所在|所走|走|行)?的?(?:这步|这一步)?大运\s*{DENIAL}"
    rf"(?:是|为|：|:|走)?\s*(?P<gz>{JIAZI})|"
    # “目前走的是辛巳大运”“当前处于辛巳大运”“如今正行辛巳运” (bazi pilot r3 probe).
    rf"(?:{PRESENT}(?:正)?(?:走|行|处于|处在|进入|在)|正在走|正走|走到了?)(?:的是|的|着|了)?"
    rf"\s*{DENIAL}(?:是)?\s*(?P<walking>{JIAZI})(?:这步|这一步)?(?:大运|运)(?![势气程])"
)
# A cycle taken as “this” stage (bazi pilot r3, typed birth #2: “首步大运辛巳（1997年交运）这个
# 大运阶段需要你留意”, in a reading of 2026): in a timing reading it is the range's own cycle.
STAGE_HERE = re.compile(
    rf"(?P<label>首步大运|第一步大运|首运|第[一二三四五六七八九十\d]+步大运|大运)?的?"
    rf"(?P<gz>{JIAZI})(?P<suffix>大运|运)?(?:（[^）]{{0,24}}）|\([^)]{{0,24}}\))?[，,]?\s*"
    r"(?P<here>(?:这个|这一|这|此)(?:步|个)?(?:大运阶段|大运|阶段|运)|这一?步)"
)
# What sets such a stage in another time, right after it (“这个阶段早已过去”“这一步之后”) or
# right before it (“早在”“下一步”); anywhere else in the clause it does not (“别重复过去的模式”).
OTHER_TIME_AFTER = re.compile(
    r"\s*(?:(?:已经|早已|早就|已|都)?(?:过去|走完|结束|过完)(?:了)?"
    r"(?=\s*(?:[，,。；;！!？?）)\n]|$))|之后|以后|之前|以前|过后)"
)
OTHER_TIME_BEFORE = re.compile(
    r"(?:早在|当年|那时|当时|回看|回顾|下一步|下步|往后|将来|未来|接下来|交运后|等到)的?$"
)
# A year directly governing this stage is a historical/future reference only when it
# agrees with the calculated cycle. An unrelated year elsewhere is not an exemption.
STAGE_TIME_BEFORE = re.compile(
    r"(?P<first>\d{4})年(?:(?:至|到|[-—–~～])(?P<last>\d{4})年)?"
    r"(?:\d{1,2}月(?:\d{1,2}日)?)?(?:时|期间|的)?"
    r"(?:进入|开始|走进|走到|处于|处在|走|行)?\s*$"
)
ANY_DAYUN = re.compile(rf"(?P<gz>{JIAZI})大运|大运(?:是|为|：|:)?\s*(?P<after>{JIAZI})")
HANDOVER = re.compile(r"(?P<year>\d{4})年(?:前后|左右)?(?:交运|换运|换大运|交大运|进入下一步大运)")
START_DATE = re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日(?:前后)?起运")
START_AGE = re.compile(r"(?P<age>\d{1,2})岁(?:起运|交运|上运)")
# A number left as text after the placeholders were rendered (bazi pilot r3, typed birth #3:
# “……引用：R7 R8 R4 R5” closed three section bodies). {{R99}} unknown is said elsewhere.
LITERAL_ALIAS = re.compile(r"(?<![A-Za-z0-9{｛])R\d+(?![\d}｝])")
LITERAL_ALIAS_PROBLEM = (
    "正文里直接写了R加数字的编号，读者看不到编号对应的事实："
    "要引用就写成{{编号}}由程序换成文字，或把编号写在【引用】行"
)
# 流月流月丙子: a placeholder already renders the label.
# “日主为日主乙木乙木” (bazi pilot r5, luck cycles #1): the label again after 为/是.
REPEATED_LABEL = re.compile(r"(流年|流月|流日|日主|大运|年柱|月柱|日柱|时柱)(?:的|为|是)?\1")
REPEATED_VALUE = re.compile(rf"(?P<value>{STEM}[木火土金水]|{JIAZI})(?P=value)")
# 第4步大运第4步大运己未, 第一步大运第1步大运丙辰 (bazi pilot r4, luck cycles #2), and the
# fact's own note copied after it: （2023年交运，2033年换下一步）（2023年交运，2033年换下一步）.
REPEATED_STAGE = re.compile(
    # r5 luck cycles #3: “第一步第1步大运丙辰”, without 大运 after the first.
    r"(?:首步|第[一二三四五六七八九十\d]+步)(?:大运)?的?(?:首步|第[一二三四五六七八九十\d]+步)大运"
)
REPEATED_NOTE = re.compile(r"（(?P<note>[^（）]{4,40})）\s*（(?P=note)）")
# The five-element count is the natal chart's (wuxing_count); no period has one (bazi pilot r5,
# overseas #3: “按五行简单计数，这段时间木2、火4、土2、金0、水0”).
ELEMENT_COUNT = re.compile(
    r"[木火土金水](?:有|为|是|：|:)?\s*[0-9一二三四五六七八](?!\d*[月日年号])"
)
ELEMENT_COUNT_LIST = re.compile(
    rf"{ELEMENT_COUNT.pattern}(?:[、，, \t和及与]*{ELEMENT_COUNT.pattern}){{2,}}"
)
NATAL_SCOPE_WORD = re.compile(r"原局|命局|本命|八字|命盘|四柱|出生|天生|先天|命里|命中|生辰")
NATAL_SCOPE_DENIED = re.compile(r"(?:不是|并非|而非|不属于|并不是)(?:看|按|用)?$")
# “年柱戊辰（天干戊为正财）、时柱己卯（天干己为偏财）这两处偏财线索” (bazi pilot r7, luck cycles
# #2): a summary of the ten gods just listed must agree with them.
LISTED_GOD = re.compile(rf"天干[{STEMS}]为(?P<god>{'|'.join(TEN_GODS)})")
AGGREGATE_GOD = re.compile(
    rf"(?P<count>两|二|三|四|几)(?:处|个|项|柱|条)(?:都是|都为|都带有?|都属于?|都|的)?(?P<god>{'|'.join(TEN_GODS)})"
    rf"|都(?:是|为|带有?|属于?)(?P<both>{'|'.join(TEN_GODS)})"
)
AGGREGATE_DENIED = re.compile(r"(?:不|并不|并非|没有|未必|不一定)(?:都|全)?(?:是|为)?$")
# Bazi pilot r8, investment #2: “春节之后，流年丁未（…2027年2月4日09:46…）”. A flow year begins
# at 立春, not at 春节 (2027: 2月4日 and 2月6日); 春节 written as the change is refused however
# close the two days are. Only where it opens or bounds a named flow year: “春节前后多陪家人”
# names no flow year.
FESTIVAL = r"(?:春节|农历新年|(?<!不)过年|大年初一|正月初一)"
FESTIVAL_EDGE = r"(?:之后|以后|过后|后|一过|起|开始|之前|以前|前)"
YEAR_AT_FESTIVAL = re.compile(
    rf"(?P<at>(?:过了|过完){FESTIVAL}{FESTIVAL_EDGE}?|{FESTIVAL}{FESTIVAL_EDGE})[，,]?\s*(?:就|便|才|仍|还|都)?"
    rf"(?:进入|转入|换成|换到|换为|迎来|来到|轮到|走到|是|为|属于?|在)?(?=流年{JIAZI})"
    rf"|流年{JIAZI}(?:（[^（）]*）)?"
    r"(?:并不是|不是|并非|而非|(?:不|没|并非|并不)(?:完全|全然|一定|绝对|根本|全)是?){0,2}"
    rf"(?:要|才|就|会)?(?P<prep>从|自|于|在|到){FESTIVAL}(?:之后|以后|过后|后)?才?"
    r"(?:开始|起|算起|交接)"
)
FESTIVAL_PROBLEM = (
    "流年按立春换年，不是春节：写流年从何时开始时，用立春或事实表里的日期，不要写成春节前后"
)
COUNT_PROBLEM = (
    "五行计数是原局（出生八字）的，不是这段时间的：写成“原局五行计数……”，"
    "不要说成这个月、这段时间或流年流月的五行分布"
)
# “‘全投’本身也超出八字能判断的范围” (bazi pilot r5, investment #1): a disclaimer after the
# action, read right after it.
OUT_OF_SCOPE = re.compile(
    r"[”’」\"']?(?:本身)?(?:也|都)?"
    r"(?:(?:超出|超过|不在|不属于)了?(?:八字|命理|排盘|传统命理)(?:所?能|可以)?(?:判断|决定|回答|推断)?的?范围"
    r"|不是(?:八字|命理|排盘|传统命理)(?:所?能|可以)(?:判断|决定|推断)的)"
)
# “出生当年就进入了第一步大运” for a start 4年10个月20天 after birth (bazi pilot r4, luck
# cycles #3): when the chart starts its cycles, said as at or right after birth.
AT_BIRTH = re.compile(
    r"(?P<when>出生当年|出生那年|一出生|刚出生|出生时|出生后不久|出生不久)(?:就|便)?"
    r"(?:开始)?(?:起运|交运|上运|进入了?(?:第一步|首步|第1步)?大运|走大运|行大运)"
)
# “又与年柱有流年丙午与本命时柱辛亥天干合” (bazi pilot r4, investment #3): a pillar named in
# front of a relation fact that is about another pillar.
LEAD_PILLAR = re.compile(
    rf"(?P<lead>[年月日时])柱(?:之间)?(?:有|出现|形成|构成|是|的)?\s*"
    rf"(?:流年|流月|流日){JIAZI}(?:天干|地支)?(?:与|和|跟)(?:本命|原局)(?P<natal>[年月日时])柱"
)
# “大运层面有年柱丙寅” (bazi pilot r4, investment #2): a natal pillar named as a luck cycle.
NATAL_AS_DAYUN = re.compile(
    rf"大运(?:层面|方面)?(?:上|里|中)?(?:有|是|带|出现)(?:本命|原局)?的?(?P<name>[年月日时])柱"
    rf"(?P<gz>{JIAZI})"
)
# Positions, trades and amounts timed by a period (bazi pilot r4, investment #1–#3: “八月……此时
# 更适合检查仓位而非扩大仓位”). The writing prompt forbids it; checked for an investment
# question only.
INVESTMENT = re.compile(RISKS[0][1] + "|股市|股|仓")
TRADE = re.compile(
    r"[加减建清满重轻全底调]仓|仓位|抄底|追涨|杀跌|止盈|止损|买入|卖出|买卖|交易|操作|投入|出手|进场|入场|离场|试探|额度|"
    # bazi pilot r7, investment #2: “这几个月更适合小额验证、设好止损线”.
    r"小额(?:验证|尝试|参与)"
)
ALL_IN = re.compile(
    r"全部投入|全投|全押|押上全部|全仓|满仓|梭哈|一次性押上|集中投入|一次性投入|一次性建仓"
)
PERIOD_WORD = re.compile(
    r"流年|流月|流日|大运|(?<![年月日时])(?:正|腊|十[一二]|[一二三四五六七八九十]|1[0-2]|[1-9])月(?!柱)|"
    r"月份|上半年|下半年|全年|整年|今年|明年|年初|年中|年底|年末|月初|月中|月底|"
    r"这段时间|这段|此时|这时|这一时期|时期|时段|阶段|窗口|期间|这几个月|"
    + RELATIVE.pattern
    + r"|(?<!\d)\d{4}年|"
    + BIRTH_DATE
)
TURNED_BACK = re.compile(
    r"不能说|不是说|并不是说|很难说|谈不上|说不上|不代表|不等于|并不意味|怎么会|岂"
)
# Owner decision 2026-11-10: a period may come with holding back (“八月不宜加仓”“最需要克制
# 加仓冲动的阶段”). A clause holds back when it restrains the trade and recommends nothing; a
# weakened or turned-back restraint (“不一定不适合”“不能说不宜”“并非不宜”) does not.
RESTRAINT = re.compile(
    r"不宜|不适合|不要|别|避免|克制|暂缓|不急于|不建议|尽量不|而非|而不是|勿|不做|少做|少碰|"
    r"减少|不轻易|不贸然|不追|忌|延后|推迟|搁置|暂停|不能|"
    # bazi pilot r6, investment #1–#3: “不构成买卖时点”“不算适合把积蓄全投”“不像是适合一把投入”.
    # These negations must deny suitability, not a need for caution (“并不需要谨慎加仓”).
    # bazi pilot r3 investment #3: “适合复盘预算、控制仓位的时段”.
    r"控制|降低|压低|收紧|守住|"
    r"不构成|(?:不算|算不上|不像是?|不太|并不)"
    r"(?=(?:是)?(?:让人)?(?:很|太|那么)?(?:适合|宜|放心))"
)
# A recommendation right after a negation is denied (“不算适合”“谈不上是让人放心”).
DENIED_BEFORE = re.compile(
    r"(?:不|没|非|未|不算|算不上|谈不上|说不上|不像是?|并不|不太|不是|并非)(?:是)?(?:让人)?(?:很|太|那么)?$"
)
INNER_NEGATION = re.compile(r"不|没|非|无|别|未")
DOUBLE_RESTRAINT = re.compile(r"(?:不算|算不上|谈不上|说不上|不像是?|不太)不")
# “涉及大额投入的事多找人复核”“合伙或跟风操作尤其要边界清楚” (bazi pilot r6, investment #2, #3).
CAUTION_AFTER = re.compile(
    r"(?:的事|的决定|的计划|之前|前|时|上|中)?(?:都|也|先|多|尤其|更|一定|务必|最好)?"
    r"(?:要|需要|需|得)?(?:找人|和家人)?"
    # A review verb needs an object or a boundary, not an investment's name (“核实型基金”).
    r"(?:(?:复核|核实|核对|评估|确认|商量|写清楚?|留意)"
    r"(?=[\s。！？!?，,；;：:]|$|(?:你的|自己的|自身的?)?"
    r"(?:财务|资金|金额|预算|风险|条件|边界|计划|承受能力|实际情况))|"
    # A caution adjective must finish the reminder, not begin an investment's name.
    r"(?:三思|想清楚|边界清楚|谨慎|小心|慎重|冷静)(?:一些|一点|些|点|一下)?"
    r"(?=[\s。！？!?，,；;：:]|$))"
)
ENCOURAGED = re.compile(
    r"(?<!不)(?:更|最|较|比较|很|也|只|正)?适合|(?<![不适])宜(?!不)|可以|应该|应当|值得|不妨|最好|建议|"
    r"(?:不宜|不要|别|避免|不必|忌)再?(?:犹豫|迟疑|观望|错过|等待)"
)
WEAKENED = re.compile(r"不一定|未必|不完全|并不完全|不见得")
CLAUSE_OR_TURN = re.compile(
    r"[，,；;：:]|但是?|不过|然而|可是|却|所以|因此|因而|而且|并且|同时|且|并(?!非|不|未|没)"
)
# Match all-in phrases as actions, never erase them merely because another action is denied.
TRADE_ACTION = re.compile(ALL_IN.pattern + "|" + TRADE.pattern)
TRADE_COORDINATION = re.compile(r"[\s、和或及与“”‘’\"']*(?:这种|以及|或者)?[\s“”‘’\"']*")
NO_TRADE_SUPPORT = re.compile(r"(?:没有|无|不足以)[^，,。；;]{0,24}(?:支持|依据|说明)")
FINANCIAL_REVIEW = re.compile(r"(?P<verb>核实|核对|评估|确认)[^，,。；;]{0,24}$")
TRADE_PROBLEM = (
    "八字不能推出仓位、买卖时点或投入节奏：不要按流年、流月或某段时间推荐"
    "加仓、减仓、试探投入、调整操作；可提醒核实财务状况和风险承受能力，或只作克制冲动的提醒"
)
ASK_GENDER = "排大运需要知道性别（大运顺排还是逆排由性别和年干决定）：请告诉我是男还是女。"
ASK_FORM_GENDER = "排大运需要性别：请在出生信息表中选择性别，填好后发送“继续”。"
ASK_PHYSICAL = (
    "按真太阳时修正后的出生时刻跨过了节气，修正钟表口径的大运会和年柱、月柱冲突。"
    "如果同意按物理出生时刻起运，请回复“物理时刻起运”。"
)
# A lunar date's clock must be written right after the date (plugins.bazi.tools.stated_lunar).
ASK_LUNAR_CLOCK = (
    "排时柱需要出生时间：请把农历生日和时间连在一起再写一遍，例如“农历2023年二月十五早上10点出生”；"
    "不知道时间就说“不知道出生时间”。"
)
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"
# A run asks at most three times (astro: two): birth data typed into the message may need its
# place, its clock and an overseas solar-time choice before the chart can be computed.
MAX_ASKS = 3
MAX_PERIODS = 48
BODY_LIMIT = 1200  # common.schemas.Reading: a section body
SECTION_LIMIT = compose.LIMITS["sections"]
SECTION_ORDER = ("日主", "四柱", "大运", "流年", "流月", "流日", "流期与原局", "约定")


def number(text: str) -> int:
    if text.isdigit():
        return int(text)
    digits = dict(zip("一二三四五六七八九", range(1, 10), strict=True))
    if text.startswith("十"):
        return 10 + digits.get(text[1:], 0)
    if "十" in text:
        head, tail = text.split("十", 1)
        return digits.get(head, 0) * 10 + digits.get(tail, 0)
    return digits.get(text, 0)


def claim(text: str, start: int, end: int) -> str | None:
    """“asserted”, “denied”, “hedged” or None (a denied inference), for a value at start:end.

    common.facts.value_claim reads the words right before the value; a denial inside an outer
    negation (不能说……不是, 不可能不是) states the value again, and a degree word between the
    negation and the value (不完全是) is neither.
    """
    head = text[max(0, start - 12) : start]
    if HEDGED.search(head):
        return "hedged"
    kind = value_claim(text, start, end)
    if kind != "denied":
        return kind
    if re.search(r"并不是|不是|并非|而非", head) and INFERENCE.match(text, end):
        return None  # “并不是丁火日主都外向” denies an inference about day masters
    clause = max(text.rfind(c, 0, start) for c in CLAUSE_BREAK) + 1
    before = text[clause:start]
    negations = list(NEGATION.finditer(before))
    lead = before[: negations[-1].start()] if negations else before
    return "asserted" if OUTER.search(lead) else "denied"


def reasserted(text: str, end: int, value: str) -> bool:
    """Whether a value denied before ``end`` is stated again later in the same sentence
    (“日主不是乙木，但其实是乙木”): the denial does not stand."""
    stop = min((i for i in (text.find(c, end) for c in "。！？!?\n") if i != -1), default=len(text))
    for match in re.finditer(re.escape(value), text[end:stop]):
        start = end + match.start()
        if claim(text, start, start + len(value)) == "asserted":
            return True
    return False


def wrong(kind: str | None, actual: bool) -> bool:
    """Whether a value claim of this kind is wrong for a value that is (not) the actual one."""
    if kind is None:
        return False
    if kind == "hedged":
        return True
    return (kind == "asserted") != actual


def encouraged(text: str) -> bool:
    """A recommendation that no negation right before it denies (“不算适合” is none)."""
    return any(
        not DENIED_BEFORE.search(text[: m.start()])
        for m in ENCOURAGED.finditer(text)
        if not m[0].startswith(("不宜", "不要", "别", "避免", "不必", "忌"))
    ) or bool(re.search(r"(?:不宜|不要|别|避免|不必|忌)再?(?:犹豫|迟疑|观望|错过|等待)", text))


# Owner decision 2026-11-10 (r7 review): refuse only an explicit recommendation of a timed trade;
# anything else that names a trade passes. The signals of a recommendation, per action:
# a recommending word before it (适合/可以/建议…) with no restraint in between; a manner or modal
# word right before it (分批/适度/谨慎/要/可…) that no restraint or denial governs; a period word
# right before it (“8月加仓”); the action opening its clause (“……并加仓”); a timing noun after it
# asserted (“8月是买入时点”); a denial turned back, a hesitation or a chance not to miss.
MANNER_BEFORE = re.compile(
    r"(?P<word>要|应该|应当|应|可以|可|能|宜|适度|分批|逢低|择机|大胆|放心|积极|果断|谨慎|小心|冷静|"
    r"慎重|考虑|开始|着手|继续|适量|少量|小额|小幅|大额|一次性)(?:地)?(?:先)?$"
)
NEED_BEFORE = re.compile(r"需要|必要|必须|用得着")
CAUTION_MANNER = ("谨慎", "小心", "冷静", "慎重")
# “8月不太需要谨慎买入”“谈不上需要谨慎加仓”: the need for caution denied.
NEED_DENIED = re.compile(
    r"(?:不|并不|不太|谈不上|算不上|不算|不像是?|不能说|说不上)[^，,。；;]{0,3}(?:需要|必要|必须|用得着)$"
)
NOMINAL_AFTER = re.compile(
    r"[”’」\"']*(?:的)?(?:念头|冲动|风险|条件|规则|线|计划|上限|理由|决定|方式|节奏|这类|这种|之类|类|"
    r"依据|信号|方案|纪律|习惯|频率|比例|成本|逻辑|心态|欲望|年份|月份|一年|阶段|安排|判断)"
)
TIMING_NOUN_AFTER = re.compile(r"[”’」\"']*(?:的)?(?:好)?(?:时点|时机|窗口|机会|时候)")
TIMING_DENIED = re.compile(
    r"不构成|不是|并非|不能|无法|不作为|不当作|不当成|不代表|不等于|别把|不要把"
)
QUESTION_BEFORE = re.compile(r"(?:是否|要不要|该不该|能否|可否|何时|什么时候|能不能)$")
# A contemplated action in the condition is not an instruction in its consequent.
CONSIDERED_CONDITION = re.compile(
    r"(?:如果|若|假如|要是|即便|即使|万一)(?:你|您)?(?:正在|正|在|已经)?"
    r"(?:考虑|打算|计划|准备|想|需要|要)(?:(?!就|则|那么|便|应该|建议|适合|可以).){0,12}$"
)
CONSEQUENT_BEFORE = re.compile(r"(?:就|则|那么|便)(?:先)?$")
RHETORICAL = re.compile(r"(?:岂能|怎么会|怎能|岂可)[^，,。；;]{0,4}错过")
HESITATION_DENIED = re.compile(r"(?:不宜|不要|别|避免|不必|忌)再?(?:犹豫|迟疑|观望|错过|等待)")
OPENING = re.compile(r"[\s“”‘’\"'—\-·•*、]*(?:先|就|再|然后|接着|随后)?$")
# An action opening its clause is an instruction when nothing but its object follows (“……并加仓”,
# “并买入股票”), not a subject (“投入越多越容易……”“操作上宜留余地”).
OBJECT_AFTER = re.compile(
    r"[\s。！？!?]*$|(?:一些|一点|部分|少量|资金|积蓄|股票|基金|股市|标的|个股|指数)"
)
COMPARED_BEFORE = re.compile(r"比[^，,。；;]{0,8}$")
# “‘全投’不一定超出八字能判断的范围” weakens the disclaimer: bazi might judge it after all.
SCOPE_WEAKENED = re.compile(
    r"[”’」\"']?(?:本身)?(?:也|都)?(?:不一定|未必|并非|并不|不是|不见得)(?:超出|超过|不在|不属于)"
)


# “明年把积蓄全部投入股市暂不适合”“明年把积蓄全押股市这件事，从盘面提示看暂不适合” (bazi pilot r1
# and r2 final answers, refused when replayed on c6b1b26): the trade is the subject of a verdict
# that denies it is suitable, so it holds back (owner, 2026-11-10). Read up to a turn or the end
# of the sentence; another period, trade or recommendation before the verdict takes it over.
VERDICT_DENIED = re.compile(
    r"(?:不太|不大|不算|不够|不怎么|不|难称|算不上|谈不上|称不上)"
    r"(?:适合|合适|适宜|明智|可取|稳妥|妥当|划算|值得|现实|理智|理性)"
    # The verdict ends its clause: “不适合全投”“不适合犹豫” govern what follows instead.
    r"(?=(?:你|您|自己)?[了的吧啊呢]?(?:[，,。；;！!？?\n）)”’]|$))"
)
VERDICT_TURN = re.compile(r"但|不过|然而|可是|却|而是|反而|只是|除非")
# Between the trade and its verdict: the trade's object or topic (“股市这件事”), a viewpoint
# (“从盘面提示看”) and adverbs only. “8月是加仓的好时机，错过就不划算” has its own subject.
VERDICT_SUBJECT = re.compile(
    r"[^，,]{0,10}?(?:这件事|这个(?:决定|想法|做法|选择)|这种做法|这一步)?"
    r"(?:[，,]\s*(?:从|就|按)[^，,]{0,10}?(?:看|来看|而言|来说))?"
    r"(?:暂时?|并|都|还|也|就|恐怕|显然|目前|现在|对你|完全|根本|实在|真的|确实|其实)*"
)
VERDICT_TAKEN_OVER = re.compile(r"时机|时点|窗口|机会|时候|错过|犹豫|迟疑|观望|等待|晚|迟")
VERDICT_DENIAL_DENIED = re.compile(
    r"(?:不是|并非|并不是|未必|不一定|不见得|不能说|很难说|说不上|谈不上|并不|不|"
    r"(?:不|并不|并非)(?:完全|全然|全))$"
)


def denied_verdict(tail: str) -> bool:
    """Whether the rest of the sentence after a trade denies, in so many words, that the trade
    is suitable (“……暂不适合”“……并不明智”); “不是不适合” and “不完全适合” do not."""
    turn = VERDICT_TURN.search(tail)
    scope = re.split(r"[。！？!?\n]", tail[: turn.start()] if turn else tail)[0]
    match = VERDICT_DENIED.search(scope)
    if not match:
        return False
    between = scope[: match.start()]
    if not VERDICT_SUBJECT.fullmatch(between) or VERDICT_TAKEN_OVER.search(between):
        return False
    if PERIOD_WORD.search(between) or TRADE_ACTION.search(between) or ENCOURAGED.search(between):
        return False
    return not VERDICT_DENIAL_DENIED.search(between)


def restrains_trade(text: str) -> bool:
    """A bound on this action, not on another object before the action."""
    for match in RESTRAINT.finditer(text):
        if match[0] in ("控制", "降低", "压低", "收紧", "守住"):
            # “控制仓位” bounds 仓位; “控制情绪再加仓” does not bound 加仓.
            if not re.fullmatch(r"(?:你|您|自己|自身)?的?", text[match.end() :]):
                continue
        return True
    return False


def recommended_trade(
    clause: str, action: re.Match, before: str, after: str, tail: str | None = None
) -> bool:
    """Whether this clause recommends the trade it names (see the owner decision above).

    ``before`` is the text since the previous action (a bare list shares its governor);
    ``after`` runs to the next action; ``tail`` is the rest of the sentence after the action.
    """
    prefix = clause[: action.start()]
    rest = clause[action.end() :]
    if tail is not None and denied_verdict(tail):
        # “不能说明年全投股市不适合” turns the verdict back; “明年全投股市暂不适合” holds back.
        return bool(TURNED_BACK.search(prefix) or WEAKENED.search(prefix))
    # A denial turned back states the trade again (“不能说8月不宜加仓”“8月并非不宜加仓”).
    turned = TURNED_BACK.search(prefix)
    if turned and turned[0] not in ("岂", "怎么会"):
        tail = prefix[turned.end() :]
        if INNER_NEGATION.search(tail) or OUT_OF_SCOPE.match(rest):
            return True
    if (
        DOUBLE_DENIAL.search(prefix)
        or DOUBLE_RESTRAINT.search(prefix)
        or SCOPE_WEAKENED.match(rest)
    ):
        return True
    if WEAKENED.search(prefix) and INNER_NEGATION.search(prefix[WEAKENED.search(prefix).end() :]):
        return True
    if RHETORICAL.search(prefix) or HESITATION_DENIED.search(prefix):
        return True
    # What only names, reviews or bounds the trade.
    if financial_review(before, action[0], rest) or out_of_scope(before, rest):
        return False
    if NO_TRADE_SUPPORT.search(before) or QUESTION_BEFORE.search(before):
        return False
    if CONSIDERED_CONDITION.search(prefix):
        return False
    if CAUTION_AFTER.match(after) and not encouraged(before):
        return False
    if TIMING_NOUN_AFTER.match(after):
        return not (
            TIMING_DENIED.search(prefix) or (restrains_trade(prefix) and not encouraged(prefix))
        )
    if COMPARED_BEFORE.search(before) and not encouraged(before):
        return False  # 会比一次性全投从容得多
    manner = MANNER_BEFORE.search(before)
    if manner:
        ahead = before[: manner.start()]
        governor = [
            m
            for m in (*RESTRAINT.finditer(before), *TURNED_BACK.finditer(before))
            if m.start() < manner.start()
            and (
                m[0] not in ("控制", "降低", "压低", "收紧", "守住")
                or restrains_trade(before[m.start() : manner.start()])
            )
        ]
        if manner["word"] in ("要", "宜", "能", "可") and re.search(r"不$|别$|勿$", ahead):
            return False  # 不要加仓, 不宜加仓
        if manner["word"] in CAUTION_MANNER:
            # “8月要谨慎加仓” holds back as “加仓需要谨慎” does; denying the need does not.
            return bool(NEED_DENIED.search(ahead))
        if not governor:
            return True
        last = max(governor, key=lambda m: m.end())
        between = before[last.end() : manner.start()]
        # “不建议等待时机而要全仓”: the restraint ends at 而 and does not govern the trade.
        if re.search(r"而|但|却|反而", between):
            return True
        # “谈不上是让人放心全押” denies the manner; “谈不上需要谨慎加仓” denies the need.
        return bool(NEED_BEFORE.search(between))
    last_encouraged = None
    for match in ENCOURAGED.finditer(prefix):
        if match[0] == "建议" and prefix[: match.start()].endswith("的"):
            continue  # 别把某个朋友的建议当成全投理由
        if not DENIED_BEFORE.search(prefix[: match.start()]):
            last_encouraged = match
    if last_encouraged is not None:
        between = prefix[last_encouraged.end() :]
        if restrains_trade(between) or TIMING_DENIED.search(between):
            return False  # 适合克制加仓冲动
        governed = RESTRAINT.search(prefix) or TIMING_DENIED.search(prefix)
        if NOMINAL_AFTER.match(after) and (len(between) > 2 or governed):
            return False  # 适合把规则、凭证和止损条件想清楚
        return True
    if NOMINAL_AFTER.match(after):
        return False
    if OPENING.fullmatch(prefix) and OBJECT_AFTER.match(after):
        return True  # ……并加仓
    if CONSEQUENT_BEFORE.search(before) and OBJECT_AFTER.match(after):
        return True  # 如果资金充足就加仓
    if restrains_trade(prefix):
        return False  # 避免在冲、合集中的月份凭情绪操作
    period = None
    for match in PERIOD_WORD.finditer(prefix):
        period = match
    if period is not None:
        gap = prefix[period.end() :]
        if len(gap) <= 3 and not re.search(r"的|前|后|不|没|别|勿|非|无", gap):
            return True  # 8月加仓, 8月买入谨慎型产品
    return False


def out_of_scope(before: str, after: str) -> bool:
    """“‘全投’本身也超出八字能判断的范围”: the action itself said to be beyond bazi."""
    if TURNED_BACK.search(before) or DOUBLE_DENIAL.search(before) or WEAKENED.search(before):
        return False
    return bool(OUT_OF_SCOPE.match(after))


def financial_review(before: str, action: str, after: str) -> bool:
    """Reviewing available funds is not a recommendation to invest those funds."""
    review = FINANCIAL_REVIEW.search(before)
    if not review or re.search(r"后|再|接着|就", before[review.end("verb") :]):
        return False
    if ENCOURAGED.search(before[review.start() :]):
        return False
    if action == "投入":
        return before.endswith("可") and bool(re.match(r"资金|金额|预算|额度", after))
    return action == "额度"


def local(instant: str, tz: str) -> datetime:
    return datetime.fromisoformat(instant).astimezone(ZoneInfo(tz))


def local_day(instant: str, tz: str, *, end: bool = False) -> date:
    """The local date of an instant; an exclusive end at midnight belongs to the day before."""
    moment = local(instant, tz)
    if end and (moment.hour, moment.minute, moment.second, moment.microsecond) == (0, 0, 0, 0):
        return (moment - timedelta(seconds=1)).date()
    return moment.date()


def span_text(period: dict, tz: str) -> str:
    start, end = local(period["start_utc"], tz), local(period["end_utc"], tz)
    return f"{start.year}年{start.month}月{start.day}日{start:%H:%M}至{end.year}年{end.month}月{end.day}日{end:%H:%M}"


def short_span(period: dict, tz: str, range_start: str | None) -> str:
    """“12月7日至12月31日”: local dates, the end inclusive, years only when another year."""
    first = local_day(period["start_utc"], tz)
    last = local_day(period["end_utc"], tz, end=True)
    year = int(range_start[:4]) if range_start else first.year

    def day(value: date) -> str:
        return (
            f"{value.month}月{value.day}日"
            if value.year == year
            else f"{value.year}年{value.month}月{value.day}日"
        )

    return day(first) if first == last else f"{day(first)}至{day(last)}"


def relevant_keywords(keywords, text: str) -> list[str]:
    """Keywords that name a specific pair or group (甲己合, 申子辰) only when the fact is that
    pair: the knowledge base lists every pair of a relation, and the first ones are not this
    fact's (bazi pilot r2: 丙辛合 described as 甲己合)."""
    marks = set(STEMS + BRANCHES)
    out = []
    for keyword in chinese(keywords):
        named = [c for c in keyword if c in marks]
        if len(named) >= 2 and not set(named) <= set(text):
            continue
        out.append(keyword)
    return out


def keyword_sections(rows: list[tuple[str, str, str]]) -> tuple[list[dict], int]:
    """Keep category boundaries when they fit; otherwise share sections before omitting facts.

    Each row is (category, whole sentence, reference). The schema caps both body length and
    section count, so a tiny day-master section must not crowd out the final flow relations.
    Return the number omitted as well, including any single sentence too long to fit.
    """

    def pack(compact: bool) -> list[dict]:
        sections = []
        body, labels, refs = "", [], []

        def flush():
            sections.append({"title": "、".join(labels), "body": body, "ref_ids": refs})

        for label, sentence, ref in rows:
            if len(sentence) > BODY_LIMIT:
                continue
            separator = "\n" if labels and label != labels[-1] else ""
            if body and (
                len(body) + len(separator) + len(sentence) > BODY_LIMIT
                or (not compact and label != labels[-1])
            ):
                flush()
                body, labels, refs = "", [], []
                separator = ""
            body += separator + sentence
            if label not in labels:
                labels.append(label)
            refs.append(ref)
        if body:
            flush()
        return sections

    sections = pack(compact=False)
    if len(sections) > SECTION_LIMIT:
        sections = pack(compact=True)
    sections = sections[:SECTION_LIMIT]
    omitted = len(rows) - sum(len(section["ref_ids"]) for section in sections)
    return sections, omitted


def merged_spans(periods: list[dict]) -> dict[tuple[str, str, str], dict]:
    """(pillar, ganzhi, a period's start) → the span of the run of periods sharing that pillar.

    Flow days are cut at each day; the flow year and month they share run across them, and the
    fact sheet gives each such run once with its whole span.
    """
    out = {}
    for key in ("year", "month", "day"):
        run = []
        for item in [*periods, None]:
            gz = item["pillars"].get(key) if item else None
            if run and gz != run[0]["pillars"][key]:
                span = {"start_utc": run[0]["start_utc"], "end_utc": run[-1]["end_utc"]}
                for member in run:
                    out[(key, member["pillars"][key], member["start_utc"])] = span
                run = []
            if gz:
                run.append(item)
    return out


def run_start(periods: list[dict], key: str, start: str) -> str:
    """The start of the first period in the run of ``key`` that the period at ``start`` is in."""
    index = next(i for i, p in enumerate(periods) if p["start_utc"] == start)
    gz = periods[index]["pillars"][key]
    while index and periods[index - 1]["pillars"].get(key) == gz:
        index -= 1
    return periods[index]["start_utc"]


# Calendar time a section title may name (r2: “先甜后磨的上半年尾巴” over a July-to-December range
# passed every check). Parts of a year are read broadly: a title is a summary, not a boundary.
MONTH_WORD = r"(?:十[一二]|[一二三四五六七八九十]|1[0-2]|[1-9])"
BARE_PART = r"(?:上中旬|中下旬|上旬|中旬|下旬|月初|月中|月底|月末)"
MONTH_PART = rf"(?:{BARE_PART}|初|中|底|末)"
PART_AFTER = r"(?:以后|之后|后|起|开始)"
MONTH_SPAN = re.compile(
    rf"(?P<a>{MONTH_WORD})月(?P<pa>{MONTH_PART})?(?P<sa>{PART_AFTER})?"
    rf"(?:(?:到|至|—|-|~|～)(?P<b>{MONTH_WORD})月(?P<pb>{MONTH_PART})?(?P<sb>{PART_AFTER})?)?"
)
PART_SPAN = re.compile(rf"(?P<part>{BARE_PART})(?P<after>{PART_AFTER})?")
# “7到9月”, “七八月” (bazi pilot r3–r6 titles): the first month without 月 is written out.
MONTH_PAIR = re.compile(
    rf"(?<![\d一二三四五六七八九十月第])(?P<a>{MONTH_WORD})(?P<sep>到|至|—|-|~|～)(?={MONTH_WORD}月)"
)
ADJACENT_MONTHS = re.compile(
    r"(?<![一二三四五六七八九十\d])(?P<a>[一二三四五六七八九])(?P<b>[二三四五六七八九十])月"
)


def written_months(title: str) -> str:
    """“7到9月” → “7月到9月”; “七八月” → “七月到八月” for consecutive months only."""
    title = MONTH_PAIR.sub(lambda m: f"{m['a']}月{m['sep']}", title)

    def pair(m):
        a, b = "一二三四五六七八九".index(m["a"]), "二三四五六七八九十".index(m["b"])
        return f"{m['a']}月到{m['b']}月" if b == a else m[0]

    title = re.sub(r"十一二月|十一、十二月", "十一月到十二月", title)
    return ADJACENT_MONTHS.sub(pair, title)


RELATIVE_PART = re.compile(rf"(?P<part>{MONTH_PART})(?P<after>{PART_AFTER})?")
YEAR_PARTS = {
    "上半年": ((1, 1), (6, 30)),
    "下半年": ((7, 1), (12, 31)),
    "年初": ((1, 1), (3, 31)),
    "年中": ((5, 1), (8, 31)),
    "年底": ((11, 1), (12, 31)),
    "年末": ((11, 1), (12, 31)),
}
SEASON = re.compile(r"(?P<season>[春夏秋])(?:季|天)")
SEASON_PARTS = {
    "春": ((2, 1), (5, 31)),
    "夏": ((5, 1), (8, 31)),
    "秋": ((8, 1), (11, 30)),
}
MONTH_NUMBER = {"十一": 11, "十二": 12, **{c: i for i, c in enumerate("一二三四五六七八九十", 1)}}
SPAN_SLACK = 2


def month_number(text: str) -> int:
    return int(text) if text.isdigit() else MONTH_NUMBER[text]


def part_of(year: int, month: int, part: str | None, after: str | None = None) -> tuple[date, date]:
    import calendar as months

    last = months.monthrange(year, month)[1]
    low, high = {
        "上中旬": (1, 20),
        "中下旬": (11, last),
        "上旬": (1, 10),
        "月初": (1, 10),
        "初": (1, 10),
        "中旬": (11, 20),
        "月中": (11, 20),
        "中": (11, 20),
    }.get(part, (21, last) if part in ("下旬", "月底", "月末", "底", "末") else (1, last))
    if after:
        high = last
    return date(year, month, low), date(year, month, min(high, last))


def title_spans(title: str, start: date, end: date, today: date | None) -> list[tuple[date, date]]:
    """The calendar spans a section title names, in the range's years; [] when it names none.

    “八月到九月”, “7月中到8月初”, “十月到年底”, “上半年”, “春季到夏季”; a part of a month alone
    (上旬, 月中之后…) only when the range is a single month; 下个月/这周… from today.
    """
    title = written_months(title)
    years = list(range(start.year, end.year + 1))
    if today is not None and "明年" in title:
        years = [today.year + 1]
    elif today is not None and "今年" in title:
        years = [today.year]
    stated = re.search(r"(\d{4})年", title)
    if stated:
        years = [int(stated[1])]
    out = []
    for match in MONTH_SPAN.finditer(title):
        first = month_number(match["a"])
        last = month_number(match["b"]) if match["b"] else first
        for year in years:
            low, high = part_of(year, first, match["pa"], match["sa"])
            if match["b"]:
                last_year = year if last >= first else year + 1
                _, high = part_of(last_year, last, match["pb"], match["sb"])
            out.append((low, high))
    rest = MONTH_SPAN.sub("", title)
    for word, ((m1, d1), (m2, d2)) in YEAR_PARTS.items():
        if word in rest:
            out += [(date(year, m1, d1), date(year, m2, d2)) for year in years]
    # A bare 春/秋 also occurs in idioms (春风得意、秋后算账), not just calendar titles.
    for match in SEASON.finditer(rest):
        (m1, d1), (m2, d2) = SEASON_PARTS[match["season"]]
        out += [(date(year, m1, d1), date(year, m2, d2)) for year in years]
    if out and re.search(r"(?:到|至)(?:年底|年末)", title):
        out = [(out[0][0], date(out[0][0].year, 12, 31))]
    # Resolve a relative month before borrowing the calculation's month for a bare 上旬.
    if not out and today is not None:
        for match in RELATIVE.finditer(title):
            low, high = relative_span(match[0], today)
            part = RELATIVE_PART.match(title, match.end())
            if part and match[0] in ("下下个月", "下个月", "这个月", "本月"):
                low, high = part_of(low.year, low.month, part["part"], part["after"])
            out.append((low, high))
    if not out and start.year == end.year and start.month == end.month:
        parts = [
            part_of(start.year, start.month, match["part"], match["after"])
            for match in PART_SPAN.finditer(rest)
        ]
        if parts:
            out.append((min(p[0] for p in parts), max(p[1] for p in parts)))
    return out


def overlaps(spans, low: date, high: date, slack: int = SPAN_SLACK) -> bool:
    gap = timedelta(days=slack)
    return any(a - gap <= high and low <= b + gap for a, b in spans)


def title_findings(
    title: str, start: date, end: date, cited: list[tuple[date, date]], today: date | None
) -> list[str]:
    """Problems with the time a section title names: it must lie in the computed range, and a
    section citing flow periods must cite at least one in that time (lenient: a title sums up
    the section, so a period running on past it is not refused)."""
    spans = title_spans(title, start, end, today)
    if not spans:
        return []
    named = "、".join(
        f"{a.month}月{a.day}日至{b.month}月{b.day}日" if a.year == b.year else f"{a}至{b}"
        for a, b in spans
    )
    if not overlaps(spans, start, end, 0):
        return [
            f"“{title}”这一层的标题说的是{named}，这次看的是{start.isoformat()}至"
            f"{end.isoformat()}；按这段时间里的月份写标题"
        ]
    if cited and not any(overlaps(spans, low, high) for low, high in cited):
        listed = "、".join(f"{a.month}月{a.day}日至{b.month}月{b.day}日" for a, b in cited[:3])
        return [
            f"“{title}”这一层的标题说的是{named}，正文引用的流期却在{listed}；"
            "按流期的实际起止写标题，或把这些句子移到对应时段的那一层"
        ]
    return []


def title_scope_findings(
    title: str,
    start: date,
    end: date,
    cited: list[tuple[date, date, str]],
    today: date | None,
) -> list[str]:
    """Stricter than title_findings for the flow months and days a section cites (bazi pilot
    r6): one lying mostly outside the title's time, or, under a title naming part of a month
    (中旬到月底), one starting or ending more than two days outside it. Flow years are left out:
    they usually cover the whole range."""
    spans = title_spans(title, start, end, today)
    if not spans or not cited:
        return []
    first, last = min(a for a, _ in spans), max(b for _, b in spans)
    named = "、".join(
        f"{a.month}月{a.day}日至{b.month}月{b.day}日" if a.year == b.year else f"{a}至{b}"
        for a, b in spans
    )
    part = bool(PART_SPAN.search(title))
    for low, high, label in cited:
        low, high = max(low, start), min(high, end)
        if low > high:
            continue
        inside = sum(max(0, (min(high, b) - max(low, a)).days + 1) for a, b in spans)
        mostly_outside = inside * 2 < (high - low).days + 1
        slack = timedelta(days=2)
        if mostly_outside or (part and (low < first - slack or high > last + slack)):
            return [
                f"“{title}”这一层的标题说的是{named}，正文里的{label}在{low.month}月{low.day}日至"
                f"{high.month}月{high.day}日，与标题的时间对不上；按流期的实际起止写标题，"
                "或把这一段移到对应时段的那一层"
            ]
    return []


# Bazi pilot r8: “好在下旬之后转向流月庚子（…2026年12月6日18:52…）” (overseas #3) and “7月中旬之后，
# 流月乙未（…2026年7月7日09:56…）” (typed birth #1) passed every check; only titles were held to
# the flow months. A body clause that names the part of a month a flow month begins in, by a
# word for after or a turn (之后, 起, 转向…), is held to the title rule (owner, 2026-11-10): the
# flow month's start more than two days outside that part is refused. Read leniently, as titles:
# “9月上旬之后” over 9月7日 passes.
STARTS_IN_PART = re.compile(
    rf"(?:(?P<month>{MONTH_WORD})月(?P<mpart>{BARE_PART}|初|中|底|末)|(?P<part>{BARE_PART}))"
    rf"(?P<after>{PART_AFTER})?[，,]?\s*(?:就|便|则|又|再|会|才)?"
    r"(?P<verb>转向|转入|转到|转为|进入|换成|换到|换为|轮到|迎来|来到|交到)?"
    rf"(?P<flow>流月(?P<gz>{JIAZI}))"
)


def start_findings(
    body: str, start: date, end: date, starts: dict[str, list[date]]
) -> list[tuple[str, str]]:
    """(problem, sentence) for a flow month said to begin in a part of a month it does not
    begin in. ``starts``: each flow month's local start days in the range (clipped to it)."""
    single = start.year == end.year and start.month == end.month
    years = range(start.year, end.year + 1)
    found = []
    for sentence in re.split(r"(?<=[。！？!?；;])|\n", body):
        for match in STARTS_IN_PART.finditer(sentence):
            if not (match["after"] or match["verb"]) or match["gz"] not in starts:
                continue
            marker = sentence[match.start() : match.start("flow")].rstrip("，, ")
            if claim(sentence, match.start(), match.start("flow")) == "denied":
                continue
            part = match["mpart"] or match["part"]
            if match["month"]:
                months = [(year, month_number(match["month"])) for year in years]
            elif single:
                months = [(start.year, start.month)]
            else:
                continue  # 下旬 alone over several months names no month
            slack = timedelta(days=SPAN_SLACK)
            spans = [part_of(year, month, part) for year, month in months]
            days = starts[match["gz"]]
            if any(a - slack <= day <= b + slack for a, b in spans for day in days):
                continue
            day = days[0]
            found.append(
                (
                    f"“{marker}”说流月{match['gz']}从这时开始，流月{match['gz']}实际从"
                    f"{day.month}月{day.day}日开始；按流月的实际起始日写（如“{day.month}月"
                    f"{day.day}日起”）",
                    sentence.strip(),
                )
            )
    return found


def zone_label(tz: str) -> str:
    return "北京时间" if tz == "Asia/Shanghai" else f"{tz}当地时间"


def granularity(start: str, end: str) -> str:
    """Flow days for a few days, flow months up to a year, flow years beyond."""
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    return "day" if days <= 10 else "month" if days <= 366 else "year"


def stated_gender(text: str) -> tuple[str, str] | None:
    """(gender, the words stating it) when the user states their own gender exactly once."""
    found = {(m["gender"], m.group()) for m in GENDER_STATED.finditer(text)}
    genders = {g for g, _ in found}
    if len(genders) != 1:
        return None
    gender, words = next(iter(found))
    value = "male" if gender == "男" else "female"
    return (value, words) if value in gender_evidence(words) else None


def lunar_usable(question: str, session) -> bool:
    """A lunar birth typed into the message, with nothing saved it would replace."""
    return (
        not getattr(session, "birth_binding", None)
        and not session.profile.get("birth_local_dt")
        and birth.typed_lunar(question) is not None
    )


class Bazi(System):
    name = "bazi"
    kept = "八字计算结果"
    lunar = True  # pipeline.birth binds a lunar birth for bazi
    birth_form = (
        "看八字需要出生日期、时间和地点：请在页面上的出生信息表里补全"
        "（时间不知道可以选未知），填好后发送“继续”。也可以直接告诉我，例如"
        "“我1990年3月5日早上8点出生在杭州”。"
    )

    # ---- ① intent ------------------------------------------------------------------------

    def detect(self, runtime, message):
        from pipeline.astro import typed_birth_usable as solar_usable

        def typed_birth_usable(question, session):
            return solar_usable(question, session) or lunar_usable(question, session)

        session = runtime.session
        selected = session.state.get("selected_systems")
        if selected not in (None, ["bazi"]) or session.pinned_reading_id:
            return None
        question = self.question(message)
        run = runtime.store.unfinished_pipeline_run(session.user_id)
        if run and run["state"].get("system") == "bazi" and run["stage"] == "awaiting_input":
            from pipeline.astro import Astro

            if not Astro.answering(session, run):
                runtime.store.finish_pipeline_run(run["run_id"])
                run = None
        if run and run["state"].get("system") == "bazi":
            if run["stage"] == "awaiting_input":
                needs = run["state"].get("needs")
                handed = (
                    (selected is None and OTHER.search(question))
                    or (
                        BIRTH_MENTION.search(question)
                        and not (needs == "birth" and typed_birth_usable(question, session))
                        and needs not in ("missing_birth_time", "unknown_time_at_term")
                    )
                    or run["state"].get("asks", 0) >= MAX_ASKS
                    or (
                        needs == "birth"
                        and not requirements.birth_ready(session)
                        and not typed_birth_usable(question, session)
                    )
                )
                if needs in ("missing_birth_time", "unknown_time_at_term"):
                    from pipeline.astro import clock_answer_changes_birth

                    kept = str(run["state"].get("snapshot", {}).get("typed_lunar") or "")
                    restated = birth.typed_lunar(question)
                    if restated is not None:
                        # The lunar date written again with its clock: the same date only.
                        handed = handed or restated.date != kept.split(" ")[0]
                    else:
                        handed = handed or clock_answer_changes_birth(question, session)
                if handed:
                    runtime.store.finish_pipeline_run(run["run_id"])
                    return None
                return Intent("bazi", "input", run=run)
            if run["stage"] in RESUMABLE and (
                CONTINUE.search(message) or question == run["state"]["question"].strip()
            ):
                return Intent("bazi", "resume", run=run)
        if selected is None and (OTHER.search(question) or not BAZI.search(question)):
            return None
        if (
            UNSUPPORTED.search(question)
            or REFERS_TO_READING.search(question)
            or BIRTH_CORRECTION.search(question)
        ):
            return None
        if BIRTH_MENTION.search(question) and not typed_birth_usable(question, session):
            return None
        if not requirements.birth_ready(session) and (
            re.search(BIRTH_DATE, question) or re.search(r"出生|生于", question)
        ):
            if not typed_birth_usable(question, session):
                return None
        return Intent("bazi", "new")

    def question(self, message):
        return requirements.strip_birth_note(message).strip() or message

    # ---- ② requirements and ③ compute ----------------------------------------------------

    def text(self, run, session) -> str:
        index = session.state.get("question_message_index", 0)
        answers = session.user_messages[index:] if index >= 0 else session.user_messages[-1:]
        parts = [run.question, *(requirements.strip_birth_note(a) for a in answers)]
        return " ".join(dict.fromkeys(p.strip() for p in parts if p and p.strip()))

    async def ask(self, runner, run, question: str, needs: str):
        session = runner.session
        run.asks += 1
        run.needs = needs
        run.asked = question
        _, terminal = await runner.planned([("ask_user", {"question": question})])
        run.snapshot = snapshot(session.state)
        run.save(runner.store, session, "awaiting_input")
        return terminal or failure(session, "tool_error", "ask_failed", question)

    async def compute(self, runner, run):
        session = runner.session
        state = session.state
        if not (run.reading_id and state.get("active_reading_id") == run.reading_id):
            results, _ = await runner.planned(
                [("start_reading", {"question": run.question, "systems": ["bazi"]})]
            )
            if not results[0]["ok"]:
                error = results[0]
                return failure(session, "tool_error", error.get("code"), error["error"])
            run.reading_id = session.state["active_reading_id"]
            state = session.state
        text = self.text(run, session)
        ranged = birth.without_birth(text)
        if not state.get("bazi_question_type"):
            state["bazi_question_type"] = requirements.bazi_question_type(
                run.question, ranged, session.calendar_anchor
            )
        kind = state["bazi_question_type"]
        if not requirements.birth_ready(session) and not birth.bound(session):
            stopped = await birth.bind(self, runner, run)
            if stopped is not None:
                return stopped
            state = session.state
            if not requirements.birth_ready(session) and not birth.bound(session):
                return await self.ask(runner, run, self.birth_form, "birth")
        answer = session.user_messages[-1] if session.user_messages else ""
        gender = state.get("bazi_gender") or session.profile.get("gender")
        bound = getattr(session, "birth_binding", None)
        if bound:
            gender = bound["profile"].get("gender")
        if not gender and not bound:
            stated = stated_gender(text)
            if stated is None and run.needs == "gender":
                found = gender_evidence(answer)
                stated = (next(iter(found)), answer.strip()) if len(found) == 1 else None
            if stated is not None:
                gender = stated[0]
                results, _ = await runner.planned(
                    [
                        (
                            "update_profile",
                            {"field": "gender", "value": gender, "evidence": stated[1]},
                        )
                    ]
                )
                if not results[0]["ok"]:
                    error = results[0]
                    return failure(session, "tool_error", error.get("code"), error["error"])
                state["bazi_gender"] = gender
        if kind == "dayun" and not gender:
            return await self.ask(runner, run, ASK_FORM_GENDER if bound else ASK_GENDER, "gender")
        if not state.get("bazi_result"):
            arguments = self.arguments(run, session, text, answer)
            if gender and gender in ("male", "female"):
                arguments["gender"] = gender
            results, _ = await runner.planned([("compute_bazi", arguments)])
            stopped = await self.checked(runner, run, results[0])
            if stopped is not None:
                return stopped
            state = session.state
        if kind != "timing" or state.get("bazi_period_result"):
            return None
        found = requirements.asked_range(ranged, session.calendar_anchor)
        if found is None:
            return await self.ask(runner, run, requirements.UNCLEAR_RANGE, "range")
        start, end = found
        if (date.fromisoformat(end) - date.fromisoformat(start)).days >= 3660:
            return await self.ask(runner, run, requirements.TOO_LONG_BAZI, "range")
        try:
            period = requirements.period_choice(session, state["bazi_result"], start, end)
        except NeedsInput as exc:
            return await self.ask(runner, run, exc.question, "timezone")
        # compute_bazi_period reads the consultation timezone from here when none is passed
        # (plugins.context.period_timezone), exactly as compute_transits does for astro.
        state["timeframe_tz"] = period.tz
        state["timeframe_default"] = period.defaulted
        arguments = {
            "bazi_id": state["bazi_id"],
            "start": start,
            "end": end,
            "granularity": granularity(start, end),
        }
        results, _ = await runner.planned([("compute_bazi_period", arguments)])
        return await self.checked(runner, run, results[0])

    def arguments(self, run, session, text: str, answer: str) -> dict:
        """compute_bazi's arguments for what the user answered; the rest comes from the profile."""
        arguments = {}
        profile = session.profile
        if profile.get("time_known") is False or birth.UNKNOWN_TIME.search(text):
            arguments["time_known"] = False
        saved = str(profile.get("birth_local_dt") or "")
        if run.needs in ("missing_birth_time", "unknown_time_at_term"):
            clock = clock_in(answer)
            if clock and saved:
                arguments["birth_local"] = f"{saved[:10]} {clock}"
                arguments["time_known"] = True
            elif run.needs == "unknown_time_at_term" and UNCERTAIN.search(answer):
                arguments["accept_uncertain"] = True
        elif run.needs == "ambiguous_local_time":
            fold = re.search(r"fold\s*=\s*([01])", answer)
            if fold:
                arguments["fold"] = int(fold[1])
            elif "回拨前" in answer:
                arguments["fold"] = 0
            elif "回拨后" in answer:
                arguments["fold"] = 1
        if PHYSICAL.search(text):
            arguments["dayun_time_basis"] = "physical"
        lunar = session.state.get("typed_lunar") or (
            profile.get("lunar_date") if profile.get("calendar_input") == "lunar" else None
        )
        if lunar:
            arguments.update(calendar="lunar", lunar_date=lunar, calendar_confirmed=True)
            restated = birth.typed_lunar(answer) if run.needs == "missing_birth_time" else None
            if restated is not None and restated.clock:
                # The lunar date written again with its clock (ASK_LUNAR_CLOCK).
                arguments["lunar_date"] = restated.value
                session.state["typed_lunar"] = restated.value
            if LEAP.search(text):
                arguments["leap_month"] = True
            elif REGULAR.search(text):
                arguments["leap_month"] = False
        return arguments

    async def checked(self, runner, run, result: dict):
        if not result["ok"]:
            return failure(runner.session, "tool_error", result.get("code"), result["error"])
        data = result["data"]
        if data.get("status") == "needs_input":
            code = data.get("code") or "input"
            question = ASK_PHYSICAL if code == "confirm_dayun_time_basis" else data["question"]
            if code == "missing_birth_time" and runner.session.state.get("typed_lunar"):
                question = ASK_LUNAR_CLOCK
            return await self.ask(runner, run, question, code)
        return None

    # ---- ④ fact sheet --------------------------------------------------------------------

    def question_type(self, run, session, followup):
        kind = session.state.get("bazi_question_type")
        return "timing" if kind == "timing" else "trait"

    @staticmethod
    def texts(state) -> dict[str, tuple[str, str]]:
        """fact → (where it sits on the fact sheet, the text code renders for it)."""
        natal = state.get("bazi_result") or {}
        out = {}
        if not natal:
            return out
        master = natal.get("day_master")
        if master:
            out[f"day_master:{master}"] = ("日主", f"日主{master}")
        rule = (natal.get("input") or {}).get("zishi_rule")
        if rule:
            out[f"zishi:{rule}"] = (
                "约定",
                "子时按23点换日" if rule == "next_day" else "子时按0点换日",
            )
        pillars = natal.get("pillars", {})
        gods = natal.get("ten_gods_stems", {})
        for key, gz in pillars.items():
            if not gz:
                continue
            if key == "day":
                out[f"day:{gz}:gan"] = ("四柱", f"日柱{gz}（日主所在）")
                out[f"day:{gz}:zhi"] = ("四柱", f"日柱{gz}地支{gz[1]}")
                continue
            god = gods.get(key)
            if god:
                out[f"{key}:{gz}:{god}"] = (
                    "四柱",
                    f"{PILLAR_ZH[key]}{gz}（天干{gz[0]}为{god}）",
                )
        dayun = natal.get("dayun")
        if dayun:
            first = dayun["sequence"][0]
            y, m, d = map(int, dayun["start_solar"].split("-"))
            out[f"dayun:{dayun['start_solar']}:{first['ganzhi']}"] = (
                "大运",
                f"{y}年{m}月{d}日起运"
                + (f"（出生后{dayun['start_after']}）" if dayun.get("start_after") else "")
                + f"，首步大运{first['ganzhi']}"
                f"（{first['start_year']}年交运，{first['start_year'] + 10}年换下一步）",
            )
            for index, stage in enumerate(dayun["sequence"]):
                gz = stage["ganzhi"]
                year = stage["start_year"]
                out[f"dayun_stage:{index + 1}:{gz}:{year}至{year + 10}交运年份标记"] = (
                    "大运",
                    f"第{index + 1}步大运{gz}（{year}年交运，{year + 10}年换下一步）",
                )
                god = ten_god(master[0], gz[0]) if master else None
                if god:
                    out[f"dayun_stem:{index + 1}:{gz}:{god}"] = (
                        "大运",
                        f"第{index + 1}步大运{gz}天干{gz[0]}为{god}",
                    )
        if natal.get("alternatives"):
            out["unknown_time_candidates"] = (
                "约定",
                "出生时间未知，出生当天交节，年柱或月柱有两种可能",
            )
        period = state.get("bazi_period_result") or {}
        tz = period.get("tz") or "Asia/Shanghai"
        spans = merged_spans(period.get("periods", []))
        for item in period.get("periods", []):
            for key, gz in item["pillars"].items():
                when = f"{span_text(spans[(key, gz, item['start_utc'])], tz)}，{zone_label(tz)}"
                god = item["ten_gods"][key]
                out[f"period:{item['start_utc']}:{key}:{gz}:{god}"] = (
                    FLOW_ZH[key],
                    f"{FLOW_ZH[key]}{gz}（十神{god}；{when}）",
                )
                # Relations repeat their flow pillar's span: dates only, so a section citing
                # many stays within the 1200-character limit (bazi pilot r2, investment #1).
                dates = short_span(spans[(key, gz, item["start_utc"])], tz, period.get("start"))
                for relation in item["relations"][key]:
                    kind = relation["type"]
                    where = relation.get("natal_pillar", relation.get("branches"))
                    fact = f"period:{item['start_utc']}:{key}:{gz}:{kind}:{where}"
                    if "natal_pillar" in relation:
                        text = (
                            f"{FLOW_ZH[key]}{gz}与本命{PILLAR_ZH[where]}"
                            f"{relation['natal_ganzhi']}{kind}（{dates}）"
                        )
                    else:
                        text = (
                            f"{FLOW_ZH[key]}{gz}地支{gz[1]}与原局地支构成{where}{kind}（{dates}）"
                        )
                    out[fact] = ("流期与原局", text)
        return out

    def facts(self, session):
        state = session.state
        natal = state.get("bazi_result") or {}
        period = state.get("bazi_period_result") or {}
        allowed = state.get("allowed_refs", ())
        texts = self.texts(state)
        items = list(natal.get("interpretations", []))
        periods = period.get("periods", [])
        pillars, relations_ = [], []
        for item in period.get("interpretations", []):
            # A flow year or month shared by several flow days is listed once, from the first
            # period of its run (merged_spans gives the run's whole span).
            parts = item["fact"].split(":")
            if item["fact"].startswith("period:") and len(parts) >= 6:
                start = (
                    ":".join(parts[1:-3]) if item["kind"] == "ten_god" else ":".join(parts[1:-4])
                )
                key = parts[-3] if item["kind"] == "ten_god" else parts[-4]
                if key in ("year", "month", "day") and any(
                    p["start_utc"] == start for p in periods
                ):
                    if run_start(periods, key, start) != start:
                        continue
            (pillars if item["kind"] == "ten_god" else relations_).append(item)
        # Every flow pillar first; their relations to the natal chart fill what room is left.
        items += pillars[:MAX_PERIODS]
        items += relations_[: max(0, MAX_PERIODS - len(pillars))]
        facts = []
        for item in items:
            if item["ref_id"] not in allowed or item["fact"] not in texts:
                continue
            label, text = texts[item["fact"]]
            alias = short(item["ref_id"], session)
            meaning = item.get("meaning") or {}
            keywords = "、".join(relevant_keywords(meaning.get("keywords"), text)[:6])
            general = shorten(CAVEAT.sub("", meaning.get("text") or ""), 140)
            line = (
                f"{alias}｜{label}｜{text}｜关键词：{keywords or '无'}｜一般含义：{general or '无'}"
            )
            facts.append(Fact(alias, item["ref_id"], label, text, line))
        return facts

    # ---- ⑤ compose -----------------------------------------------------------------------

    def context(self, session) -> list[str]:
        state = session.state
        natal = state.get("bazi_result") or {}
        period = state.get("bazi_period_result") or {}
        kind = state.get("bazi_question_type")
        lines = []
        if kind == "timing" and period:
            lines.append(
                f"问题类型：时机。日期范围：{period['start']}至{period['end']}（{period['tz']}，首尾两天都含）"
            )
            phrase = RELATIVE.search(state.get("question") or "")
            if phrase:
                lines.append(
                    f"用户说的时间是“{phrase[0]}”，即{period['start']}至{period['end']}；"
                    f"正文提到这段时间时写“{phrase[0]}”或具体月份，不要换成别的说法。"
                )
            lines.append(
                "流年按立春换年，流月按节气换月，不是公历的1月1日或每月1日；"
                "事实表写明了每个流期的起止时刻。"
            )
        elif kind == "dayun":
            lines.append("问题类型：大运概览（起运、各步大运和交运年份）")
        else:
            lines.append("问题类型：原局（性格、倾向、做事方式）")
        count = natal.get("wuxing_count")
        if count:
            listed = "、".join(f"{k}{v}" for k, v in count.items())
            lines.append(
                f"原局五行简单计数（出生八字的天干地支各算一个，不是旺衰权重，也不是这段时间的分布）："
                f"{listed}"
            )
        if not natal.get("time_known", True):
            lines.append("出生时间未知：只有年、月、日三柱，没有时柱，不要写时柱或精确起运。")
        dayun = natal.get("dayun")
        if dayun:
            current = "、".join(s["ganzhi"] for s in dayun.get("current_candidates", []))
            if current:
                lines.append(
                    f"按今年算，所在大运是{current}（交运年份只是年份标记，交运年可能前后两运并存）。"
                )
            if kind == "timing" and period:
                # bazi pilot r3, typed birth #2: the only luck-cycle fact on a timing sheet is
                # the first one, and it was written as the range's own stage.
                first, last = int(period["start"][:4]), int(period["end"][:4])
                covering = [
                    s
                    for s in dayun["sequence"]
                    if s["start_year"] <= last and first <= s["start_year"] + 10
                ]
                if covering and dayun["sequence"][0] not in covering:
                    listed = "或".join(
                        f"{s['ganzhi']}（{s['start_year']}年交运）" for s in covering
                    )
                    lines.append(
                        f"这段时间所在的大运是{listed}；事实表里的首步大运"
                        f"{dayun['sequence'][0]['ganzhi']}只说明何时起运，不是这段时间的大运，"
                        "不要把它写成“这个大运阶段”。"
                    )
        elif natal:
            lines.append("没有性别资料，没有排大运；不要写大运。")
        if (natal.get("input") or {}).get("true_solar_time"):
            lines.append("日柱和时柱按出生地真太阳时排。")
        lines.append("喜用神程序不计算；要谈喜用倾向，只能据月令和五行计数推断，并写明依据。")
        return lines

    def messages(self, run, facts, session, *, prior=None, extra=""):
        return compose.bazi_messages(run.question, self.context(session), facts, extra=extra)

    # ---- ⑥ verify ------------------------------------------------------------------------

    def problems(self, texts, session):
        """The chart's closed vocabulary (plan P3.4) and the shared wording rules."""
        state = session.state
        natal = state.get("bazi_result") or {}
        if not natal:
            return self.wording_problems(texts, session)
        found = []
        for text in texts:
            found += [
                f"“{m[0]}”把“{m[1]}”写了两遍：编号会替换成带“{m[1]}”的文字，编号前不要再写"
                for m in REPEATED_LABEL.finditer(text)
            ]
            found += [
                f"“{m[0]}”把大运的步数写了两遍：编号会替换成带“第几步大运”的文字，编号前不要再写"
                for m in REPEATED_STAGE.finditer(text)
            ]
            found += [
                f"“（{m['note']}）”写了两遍：编号展开后已经带着这段说明，不要再抄一遍"
                for m in REPEATED_NOTE.finditer(text)
            ]
            found += [
                f"“{m[0]}”把“{m['value']}”写了两遍：编号展开后已经带着“{m['value']}”，不要再写"
                for m in REPEATED_VALUE.finditer(text)
            ]
            if LITERAL_ALIAS.search(text):
                found.append(LITERAL_ALIAS_PROBLEM)
            found += self.count_problems(text)
            found += self.festival_problems(text)
            found += self.aggregate_problems(text)
            found += self.role_problems(text, state)
            found += self.ganzhi_problems(text, state)
            found += self.pillar_problems(text, natal)
            found += self.day_master_problems(text, natal)
            found += self.ten_god_problems(text, state)
            found += self.dayun_problems(
                text,
                natal,
                state.get("bazi_period_result")
                if state.get("bazi_question_type") == "timing"
                else None,
            )
            found += self.relation_problems(text, state)
        found += self.wording_problems(texts, session)
        return list(dict.fromkeys(found))

    @staticmethod
    def known_ganzhi(state) -> set[str]:
        natal = state.get("bazi_result") or {}
        known = {gz for gz in natal.get("pillars", {}).values() if gz}
        for candidate in natal.get("alternatives", []):
            known.update(gz for gz in candidate.values() if gz)
        known.update(s["ganzhi"] for s in (natal.get("dayun") or {}).get("sequence", []))
        for item in (state.get("bazi_period_result") or {}).get("periods", []):
            known.update(item["pillars"].values())
        return known

    def ganzhi_problems(self, text: str, state) -> list[str]:
        known = self.known_ganzhi(state)
        return [
            f"{m[0]}不在这次的计算里（四柱、大运和所看的流年流月都没有它）"
            for m in GANZHI.finditer(text)
            if m[0] not in known and claim(text, m.start(), m.end()) not in (None, "denied")
        ]

    @staticmethod
    def pillar_problems(text: str, natal: dict) -> list[str]:
        """A natal pillar named with a stem-branch pair must be that pillar's (“年柱癸巳”)."""
        pillars = natal.get("pillars", {})
        found = []
        for match in NATAL_PILLAR.finditer(text):
            key = PILLAR_KEY[match["name"]]
            actual = pillars.get(key)
            if not actual:
                continue  # an unknown hour: the validator refuses any 时柱
            kind = claim(text, match.start("gz"), match.end("gz"))
            if kind == "denied" and reasserted(text, match.end("gz"), match["gz"]):
                kind = "asserted"
            if wrong(kind, match["gz"] == actual):
                found.append(f"{PILLAR_ZH[key]}是{actual}，正文写成了“{match[0]}”")
        return found

    @staticmethod
    def day_master_problems(text: str, natal: dict) -> list[str]:
        master = natal.get("day_master")
        if not master:
            return []
        found = []
        for match in DAY_MASTER.finditer(text):
            group = "stem" if match["stem"] else "before"
            stem = match[group]
            start, end = match.start(group), match.end(group)
            kind = claim(text, start, end)
            if kind == "denied" and reasserted(text, match.end(), stem):
                kind = "asserted"
            if wrong(kind, stem == master[0]):
                found.append(f"日主是{master}，正文写成了“{match[0]}”")
        for match in STEM_ELEMENT.finditer(text):
            if ELEMENT[match["stem"]] != match["element"]:
                found.append(
                    f"{match['stem']}的五行是{ELEMENT[match['stem']]}，正文写成了“{match[0]}”"
                )
        return found

    @staticmethod
    def expected_gods(label: str | None, gz: str | None, state) -> set[str] | None:
        """The ten gods a pillar named in the text may have; None when it names none."""
        natal = state.get("bazi_result") or {}
        master = natal.get("day_master")
        if not master:
            return None
        pillars = natal.get("pillars", {})
        gods = natal.get("ten_gods_stems", {})
        periods = (state.get("bazi_period_result") or {}).get("periods", [])
        sequence = (natal.get("dayun") or {}).get("sequence", [])
        if label and label[0] in PILLAR_KEY and label[1:] in ("柱", "干"):
            key = PILLAR_KEY[label[0]]
            if key == "day" or not pillars.get(key):
                return None
            if gz and gz != pillars[key]:
                return None  # a wrong pillar is the validator's and ganzhi_problems' to refuse
            return {gods[key]} if gods.get(key) else None
        if label in FLOW_KEY:
            key = FLOW_KEY[label]
            values = {
                p["ten_gods"][key]
                for p in periods
                if key in p["pillars"] and (gz is None or p["pillars"][key] == gz)
            }
            return values or None
        if label and "大运" in label or label == "首运":
            if gz:
                return {ten_god(master[0], gz[0])}
            if label in ("首步大运", "第一步大运", "首运") and sequence:
                return {ten_god(master[0], sequence[0]["ganzhi"][0])}
            nth = re.match(r"第(.+)步大运", label or "")
            if nth and sequence and 1 <= number(nth[1]) <= len(sequence):
                return {ten_god(master[0], sequence[number(nth[1]) - 1]["ganzhi"][0])}
            return None
        if gz:
            if gz[0] == master[0]:
                return None
            return {ten_god(master[0], gz[0])}
        return None

    def ten_god_problems(self, text: str, state) -> list[str]:
        natal = state.get("bazi_result") or {}
        periods = (state.get("bazi_period_result") or {}).get("periods", [])
        on_sheet = set((natal.get("ten_gods_stems") or {}).values())
        master = natal.get("day_master")
        for stage in (natal.get("dayun") or {}).get("sequence", []):
            if master:
                on_sheet.add(ten_god(master[0], stage["ganzhi"][0]))
        for item in periods:
            on_sheet.update(item["ten_gods"].values())
        hidden = {g for gods in (natal.get("hidden_ten_gods") or {}).values() for g in gods}
        found = []
        for match in TEN_GOD.finditer(text):
            god = match[0]
            kind = claim(text, match.start(), match.end())
            if kind is None:
                continue
            if kind == "asserted" and ABSENT.search(
                text[max(0, match.start() - 4) : match.start()]
            ):
                # “命局里没有比肩” says the chart lacks it; “不能说没有比肩” says it has it.
                clause = max(text.rfind(c, 0, match.start()) for c in CLAUSE_BREAK) + 1
                lead = text[clause : match.start()]
                lead = lead[: ABSENT.search(lead).start()] if ABSENT.search(lead) else lead
                kind = "asserted" if OUTER.search(lead) or DOUBLE_DENIAL.search(lead) else "denied"
            if kind == "denied" and reasserted(text, match.end(), god):
                kind = "asserted"
            clause = max(text.rfind(c, 0, match.start()) for c in CLAUSE_BREAK) + 1
            before = text[clause : match.start()]
            if re.search(r"藏干|藏|地支", before):
                if wrong(kind, god in hidden):
                    found.append(f"这次的地支藏干里没有{god}")
                continue
            head = before[-16:]
            while True:
                stripped = FUNCTION_TAIL.sub("", head)
                if stripped == head:
                    break
                head = stripped
            subject = SUBJECT.search(head)
            expected = (
                self.expected_gods(subject["label"], subject["gz"], state)
                if subject and (subject["label"] or subject["gz"])
                else None
            )
            if expected is not None:
                if wrong(kind, god in expected):
                    found.append(
                        f"“{before[-12:]}{god}”：这里的十神是{'、'.join(sorted(expected))}"
                    )
            elif kind == "denied":
                natal_gods = set((natal.get("ten_gods_stems") or {}).values()) | hidden
                if NATAL_SCOPE.search(before) and god in natal_gods:
                    found.append(f"原局里有{god}，正文却说没有")
            elif wrong(kind, god in on_sheet):
                found.append(f"命局、大运和这段时间的流年流月里都没有{god}")
        return found

    @staticmethod
    def dayun_problems(text: str, natal: dict, period: dict | None = None) -> list[str]:
        """Luck cycles named as the first, n-th or current one; ``period``, a timing reading's
        range, is the time a cycle taken as “this” stage must cover."""
        dayun = natal.get("dayun")
        if not dayun:
            if re.search(r"(?:首步|第.{1,2}步|当前|目前)大运|起运", text) and not re.search(
                r"没有排|没排|未排|不排|无法排|不能排", text
            ):
                return ["这次没有排大运（没有性别资料或出生时间未知），正文不能写大运"]
            return []
        sequence = [s["ganzhi"] for s in dayun["sequence"]]
        current = [s["ganzhi"] for s in dayun.get("current_candidates", [])]
        years = {s["start_year"] for s in dayun["sequence"]}
        ages = {s["start_age"] for s in dayun["sequence"]}
        found = []

        def kind_at(start, end, value):
            kind = claim(text, start, end)
            if kind == "denied" and reasserted(text, end, value):
                return "asserted"
            return kind

        def kind_of(match, group):
            return kind_at(match.start(group), match.end(group), match[group])

        for match in FIRST_DAYUN.finditer(text):
            if wrong(kind_of(match, "gz"), match["gz"] == sequence[0]):
                found.append(f"首步大运是{sequence[0]}，正文写成了{match['gz']}")
        for match in NTH_DAYUN.finditer(text):
            n = number(match["n"])
            actual = sequence[n - 1] if 1 <= n <= len(sequence) else None
            if wrong(kind_of(match, "gz"), match["gz"] == actual):
                found.append(f"第{n}步大运是{actual or '（没有排到）'}，正文写成了{match['gz']}")
        for match in CURRENT_DAYUN.finditer(text):
            group = "gz" if match["gz"] else "walking"
            if current and wrong(kind_of(match, group), match[group] in current):
                found.append(f"按今年算所在的大运是{'或'.join(current)}，正文写成了{match[group]}")
        if period and period.get("start") and period.get("end"):
            found += Bazi.stage_here_problems(text, dayun, period, kind_at)
        for match in ANY_DAYUN.finditer(text):
            group = "gz" if match["gz"] else "after"
            if match[group] not in sequence and claim(
                text, match.start(group), match.end(group)
            ) not in (None, "denied"):
                found.append(f"{match[group]}不是这次排出的大运")
        for match in HANDOVER.finditer(text):
            if int(match["year"]) not in years:
                listed = "、".join(str(y) for y in sorted(years))
                found.append(f"交运年份是{listed}，正文写成了{match['year']}年")
        for match in START_DATE.finditer(text):
            value = f"{int(match['y']):04d}-{int(match['m']):02d}-{int(match['d']):02d}"
            if value != dayun["start_solar"]:
                found.append(f"起运日是{dayun['start_solar']}，正文写成了{value}")
        for match in START_AGE.finditer(text):
            expected = ages if "交运" in match[0] else {dayun["sequence"][0]["start_age"]}
            if int(match["age"]) not in expected:
                found.append(f"“{match[0]}”与排出的交运岁数不符")
        return found

    @staticmethod
    def stage_here_problems(text: str, dayun: dict, period: dict, kind_at) -> list[str]:
        """A luck cycle taken as “this” stage in a timing reading must cover the range asked
        about; one whose ten years lie outside it is a different stage of life."""
        first, last = int(period["start"][:4]), int(period["end"][:4])
        stages = {s["ganzhi"]: s for s in dayun["sequence"]}
        # The handover year is a year label only: either cycle may hold it.
        covering = [
            s["ganzhi"]
            for s in dayun["sequence"]
            if s["start_year"] <= last and first <= s["start_year"] + 10
        ]
        found = []
        for match in STAGE_HERE.finditer(text):
            stage = stages.get(match["gz"])
            if stage is None:
                continue
            if not (match["label"] or match["suffix"] or "大运" in match["here"]):
                continue  # 流年丙午这个阶段: not a luck cycle
            clause = max(text.rfind(c, 0, match.start("gz")) for c in CLAUSE_BREAK) + 1
            stop = min(
                (i for i in (text.find(c, match.end()) for c in CLAUSE_BREAK) if i != -1),
                default=len(text),
            )
            if OTHER_TIME_BEFORE.search(text[clause : match.start()]) or OTHER_TIME_AFTER.match(
                text, match.end(), stop
            ):
                continue
            year = stage["start_year"]
            explicit = STAGE_TIME_BEFORE.search(text[clause : match.start()])
            if explicit:
                start = int(explicit["first"])
                end = int(explicit["last"] or explicit["first"])
                if year <= start <= end <= year + 10:
                    continue
            # A negation stands before the label: “现在不是首步大运辛巳这个阶段”.
            # Read the whole mention so “不是癸未这个阶段就一定顺利” denies an inference.
            kind = kind_at(match.start(), match.end(), match["gz"])
            actual = stage["ganzhi"] in covering
            if not wrong(kind, actual):
                continue
            if kind == "denied" and actual:
                # A handover year has two candidates; denying one is not provably wrong.
                if len(covering) > 1:
                    continue
                found.append(
                    f"这次看的是{period['start']}至{period['end']}，所在大运是{stage['ganzhi']}；"
                    "正文不能否认这段时间所在的大运阶段"
                )
                continue
            found.append(
                f"这次看的是{period['start']}至{period['end']}，所在大运是"
                f"{'或'.join(covering) or '（没有排到）'}；{stage['ganzhi']}是{year}至{year + 10}年"
                "的大运，不能当成这段时间的大运阶段"
            )
        return found

    @staticmethod
    def role_problems(text: str, state) -> list[str]:
        """Calculated facts put in another role by the words around them (bazi pilot r4): the
        start of the cycles said as at birth, a relation fact led by another pillar, a natal
        pillar named as a luck cycle, and positions timed by a period."""
        natal = state.get("bazi_result") or {}
        found = []
        dayun = natal.get("dayun") or {}
        years = re.match(r"(\d+)年", dayun.get("start_after") or "")
        born = (natal.get("solar_date") or "")[:4]
        for match in AT_BIRTH.finditer(text):
            if not years or not born or not dayun.get("start_solar"):
                break
            when = match["when"]
            if when in ("出生当年", "出生那年"):
                actual = dayun["start_solar"][:4] == born
            elif "不久" in when:
                actual = int(years[1]) < 2
            else:
                actual = int(years[1]) == 0
            kind = claim(text, match.start(), match.end())
            if kind == "denied" and reasserted(text, match.end(), match["when"]):
                kind = "asserted"
            if wrong(kind, actual):
                found.append(
                    f"“{match[0]}”与计算不符：{dayun['start_solar']}起运，"
                    f"是出生后{dayun['start_after']}"
                )
        for match in LEAD_PILLAR.finditer(text):
            if match["lead"] != match["natal"]:
                found.append(
                    f"“{match[0]}”：前面写的是{match['lead']}柱，后面的事实是与"
                    f"{match['natal']}柱的关系；按事实里的柱写"
                )
        pillars = natal.get("pillars") or {}
        for match in NATAL_AS_DAYUN.finditer(text):
            if pillars.get(PILLAR_KEY[match["name"]]) == match["gz"]:
                found.append(f"“{match[0]}”：{match['name']}柱{match['gz']}是原局，不是大运")
        if INVESTMENT.search(state.get("question") or ""):
            found += Bazi.trade_problems(text)
        return found

    @staticmethod
    def aggregate_problems(text: str) -> list[str]:
        """A summary (“这两处偏财”“都是正财”) of ten gods listed earlier in its sentence."""
        found = []
        for sentence in re.split(r"(?<=[。！？!?\n])", text):
            for match in AGGREGATE_GOD.finditer(sentence):
                god = match["god"] or match["both"]
                listed = [m["god"] for m in LISTED_GOD.finditer(sentence, 0, match.start())]
                if len(listed) < 2:
                    continue
                count = {"两": 2, "二": 2, "三": 3, "四": 4}.get(match["count"])
                if count is not None and count < len(listed):
                    before = sentence[: match.start()]
                    if re.search(r"(?:后|末|最后)$", before):
                        listed = listed[-count:]
                    elif re.search(r"(?:前|最前)$", before):
                        listed = listed[:count]
                    elif sum(g == god for g in listed) >= count:
                        # “其中两处偏财” need not include every preceding item.
                        continue
                if all(g == god for g in listed):
                    continue
                lead = sentence[: match.start("god") if match["god"] else match.start("both")]
                if AGGREGATE_DENIED.search(lead) or AGGREGATE_DENIED.search(
                    sentence[: match.start()]
                ):
                    continue
                found.append(
                    f"“{match[0]}”与前面写的十神不符：前面依次是{'、'.join(listed)}；"
                    "分别写出各柱的十神，不要合并成一种"
                )
        return found

    @staticmethod
    def festival_problems(text: str) -> list[str]:
        """春节 written as where a flow year begins or ends (r8 investment #2), unless denied."""
        for match in YEAR_AT_FESTIVAL.finditer(text):
            at = match.start("at") if match["at"] else match.start("prep")
            if claim(text, at, match.end()) != "denied":
                return [FESTIVAL_PROBLEM]
        return []

    @staticmethod
    def count_problems(text: str) -> list[str]:
        """A five-element count is the natal chart's; a count said of a period is misplaced.

        Commas within a count list do not end its clause. Each list takes the nearest preceding
        scope, including whether that scope or the list itself is explicitly denied.
        """
        text = ELEMENT_COUNT_LIST.sub(lambda m: m[0].replace("，", "、").replace(",", "、"), text)
        for sentence in re.split(r"(?<=[。！？!?\n])", text):
            scope = None
            for clause in CLAUSE_OR_TURN.split(sentence):
                words = [
                    (m, "natal")
                    for m in NATAL_SCOPE_WORD.finditer(clause)
                    if not NATAL_SCOPE_DENIED.search(clause[: m.start()])
                ] + [(m, "period") for m in PERIOD_WORD.finditer(clause)]
                words.sort(key=lambda item: item[0].start())
                groups = [(m.start(), m.end()) for m in ELEMENT_COUNT_LIST.finditer(clause)]
                if not groups:
                    # Keep recognizing prose-separated counts, e.g. “木2个、火4个、土2个”.
                    items = list(ELEMENT_COUNT.finditer(clause))
                    if len(items) >= 3:
                        groups = [(items[0].start(), items[-1].end())]
                for start, end in groups:
                    current = scope
                    for word, kind in words:
                        if word.start() >= start:
                            break
                        current = (kind, claim(clause, word.start(), word.end()))
                    if not current or current[0] != "period" or current[1] == "denied":
                        continue
                    if claim(clause, start, end) in (None, "denied"):
                        continue
                    # An explicit suffix also identifies a natal count: “木2、火4、土2是原局的”.
                    tail = clause[end:]
                    natal = NATAL_SCOPE_WORD.search(tail)
                    if natal and re.fullmatch(
                        r"\s*(?:是|为|属于|来自)(?:你的|你)?", tail[: natal.start()]
                    ):
                        continue
                    return [COUNT_PROBLEM]
                if words:
                    word, kind = words[-1]
                    scope = (kind, claim(clause, word.start(), word.end()))
        return []

    @staticmethod
    def trade_problems(text: str) -> list[str]:
        for sentence in re.split(r"(?<=[。！？!?\n])", text):
            # The period governs its own clause and the clauses after it, not those before
            # (“每次操作前对照，尤其留意三月……这几个时段”).
            timed, offset = False, 0
            for clause in CLAUSE_OR_TURN.split(sentence):
                offset = sentence.find(clause, offset)
                start, offset = offset, offset + len(clause)
                timed = timed or bool(PERIOD_WORD.search(clause))
                if not timed:
                    continue
                actions = list(TRADE_ACTION.finditer(clause))
                previous_end, governed = 0, ""
                for index, action in enumerate(actions):
                    before = clause[previous_end : action.start()]
                    # Only a bare list shares its preceding governor (“不要加仓、买入”).
                    # “不要追涨而要买入” starts a new predicate and cannot inherit 不要.
                    if index and TRADE_COORDINATION.fullmatch(before):
                        before = governed + before
                    next_start = (
                        actions[index + 1].start() if index + 1 < len(actions) else len(clause)
                    )
                    after = clause[action.end() : next_start]
                    tail = sentence[start + action.end() :]
                    if recommended_trade(clause, action, before, after, tail):
                        return [TRADE_PROBLEM]
                    governed, previous_end = before, action.end()
        return []

    def relation_problems(self, text: str, state) -> list[str]:
        natal = state.get("bazi_result") or {}
        pillars = natal.get("pillars", {})
        periods = (state.get("bazi_period_result") or {}).get("periods", [])
        found = []
        seen = set()
        named = sorted(
            (m.start(), m.end(), m["subject"])
            for pattern in (RELATION_AFTER, RELATION_BEFORE)
            for m in pattern.finditer(text)
        )
        for pattern in (RELATION_AFTER, RELATION_BEFORE, RELATION_CARRY):
            for match in pattern.finditer(text):
                if (match.start(), match["kind"]) in seen:
                    continue
                seen.add((match.start(), match["kind"]))
                key = PILLAR_KEY[match["natal"]]
                natal_gz = pillars.get(key)
                if not natal_gz or (match["ngz"] and match["ngz"] != natal_gz):
                    continue  # a wrong or unknown natal pillar is refused elsewhere
                if pattern is RELATION_CARRY:
                    sentence = max(text.rfind(c, 0, match.start()) for c in "。！？!?\n") + 1
                    earlier = [n for n in named if sentence <= n[0] and n[1] <= match.start()]
                    if not earlier:
                        continue
                    subject = earlier[-1][2]
                else:
                    subject = match["subject"]
                subjects = self.subjects(subject, periods)
                if not subjects:
                    continue
                word = match["kind"]
                kinds = next((v for k, v in RELATION_KINDS.items() if word.endswith(k)), {word})
                if word.startswith("天干"):
                    kinds = {k for k in kinds if k.startswith("天干")}
                elif word.startswith("地支") or word == "六合":
                    kinds = {k for k in kinds if not k.startswith("天干")}
                actual = any(
                    r["type"] in kinds for gz in subjects for r in relations(gz, {key: natal_gz})
                )
                between = match["between"] or ""
                clause = max(text.rfind(c, 0, match.start()) for c in CLAUSE_BREAK) + 1
                lead = text[clause : match.start()]
                denied = bool(RELATION_DENIED.search(between)) and not DOUBLE_DENIAL.search(between)
                if denied and OUTER.search(
                    lead + between[: RELATION_DENIED.search(between).start()]
                ):
                    denied = False
                if denied and self.relation_reasserted(text, match.end(), word):
                    denied = False
                if denied == actual:
                    found.append(
                        f"“{match[0]}”：{subject}与本命{PILLAR_ZH[key]}{natal_gz}"
                        + ("有" if actual else "没有")
                        + f"{word.lstrip('相')}的关系"
                    )
        return found

    @staticmethod
    def relation_reasserted(text: str, end: int, word: str) -> bool:
        """“流月丙子不冲月柱，但其实相冲”: a later clause of the sentence states the relation."""
        stop = min(
            (i for i in (text.find(c, end) for c in "。！？!?\n") if i != -1), default=len(text)
        )
        core = word.lstrip("相")[-1]
        for clause in re.split(r"[，,；;]", text[end:stop])[1:]:
            found = re.search(rf"相?{core}", clause)
            if found and not RELATION_DENIED.search(clause[: found.start()]):
                return True
            if found and DOUBLE_DENIAL.search(clause[: found.start()]):
                return True
        return False

    @staticmethod
    def subjects(subject: str, periods: list[dict]) -> list[str]:
        gz = GANZHI.search(subject)
        if gz:
            return [gz[0]]
        key = FLOW_KEY.get(subject)
        if not key:
            return []
        return list(dict.fromkeys(p["pillars"][key] for p in periods if key in p["pillars"]))

    def reading_problems(self, args, facts, session):
        """The summary's time words must name a span inside the computed range (as astro), and
        a section title's time must lie in the range and match the flow periods it cites."""
        state = session.state
        period = state.get("bazi_period_result") or {}
        length = self.length_problems(args)
        if state.get("bazi_question_type") != "timing" or not period or not session.calendar_anchor:
            return length
        start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        today = date.fromisoformat(session.calendar_anchor)
        first = re.split(r"[。！？!?]", args.get("summary") or "")[0]
        found = list(length)
        for clause in re.split(r"[，,；;：:]", first):
            if COMPARED.search(clause):
                continue
            for match in RELATIVE.finditer(clause):
                low, high = relative_span(match[0], today)
                if high < start or low > end:
                    found.append(
                        f"摘要第一句写成了“{match[0]}”，这次看的是{period['start']}至"
                        f"{period['end']}；按用户说的时间写"
                    )
        found += list(dict.fromkeys(p for p, _ in self.section_findings(args, facts, session)))
        return found

    @staticmethod
    def length_problems(args) -> list[str]:
        """A body within 1200 characters as written can exceed it once its numbers expand into
        facts with dates (bazi pilot r2: 24 numbers, 396 characters written, about 1400 after;
        the submission's schema error twice, then a degraded reading). Said before submission,
        with what to do."""
        found = []
        for index, section in enumerate(args.get("sections", []), 1):
            body = section.get("body") or ""
            if len(body) > BODY_LIMIT:
                found.append(
                    f"第{index}层正文的编号展开成事实后有{len(body)}字，超过{BODY_LIMIT}字的上限："
                    "每个编号会展开成带日期的整句，把这一层拆成两层，或少引几个编号"
                )
        return found

    def reading_quotes(self, args, facts, session) -> dict[str, list[str]]:
        """problem → the title that raised it, for the repair request (as astro r4)."""
        quotes: dict[str, list[str]] = {}
        for problem, sentence in self.section_findings(args, facts, session):
            if sentence not in quotes.setdefault(problem, []):
                quotes[problem].append(sentence)
        return quotes

    def section_findings(self, args, facts, session) -> list[tuple[str, str]]:
        """(problem, title) for section titles whose time is outside the range or the flow
        periods the section cites (by number, or by a flow pillar written by hand)."""
        state = session.state
        period = state.get("bazi_period_result") or {}
        if state.get("bazi_question_type") != "timing" or not period:
            return []
        start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        today = date.fromisoformat(session.calendar_anchor) if session.calendar_anchor else None
        tz = period.get("tz") or "Asia/Shanghai"
        periods = period.get("periods", [])
        spans = merged_spans(periods)
        by_alias = {}
        for fact in facts:
            fact_text = fact.ref.split(":", 2)[-1] if fact.ref.count(":") >= 2 else ""
            if not fact_text.startswith("period:"):
                continue
            # period:<start>:<pillar>:<ganzhi>:<ten god>, or …:<ganzhi>:<relation>:<natal side>.
            parts = fact_text.split(":")
            offset = 3 if parts[-1] in TEN_GODS else 4
            if len(parts) < offset + 2:
                continue
            key, gz = parts[-offset], parts[-offset + 1]
            run = (key, gz, ":".join(parts[1:-offset]))
            if run in spans:
                by_alias[fact.alias] = (spans[run], key, gz)
        starts: dict[str, list[date]] = {}
        for (key, gz, _), span in spans.items():
            day = max(local_day(span["start_utc"], tz), start)
            if key == "month" and day not in starts.setdefault(gz, []):
                starts[gz].append(day)
        found = []
        for section in args.get("sections", []):
            title = section.get("title") or ""
            cited = [by_alias[a] for a in section.get("ref_ids", []) if a in by_alias]
            body = section.get("body") or ""
            for match in re.finditer(rf"(流年|流月|流日)({JIAZI})", body):
                key = FLOW_KEY[match[1]]
                cited += [
                    (spans[(key, match[2], p["start_utc"])], key, match[2])
                    for p in periods
                    if p["pillars"].get(key) == match[2]
                    and (key, match[2], p["start_utc"]) in spans
                ]
            local = [
                (
                    local_day(span["start_utc"], tz),
                    local_day(span["end_utc"], tz, end=True),
                    FLOW_ZH[key] + gz,
                    key,
                )
                for span, key, gz in cited
            ]
            problems = title_findings(title, start, end, [(a, b) for a, b, _, _ in local], today)
            problems = problems or title_scope_findings(
                title,
                start,
                end,
                list(dict.fromkeys((a, b, label) for a, b, label, key in local if key != "year")),
                today,
            )
            for problem in problems:
                found.append((problem, title))
            found += start_findings(body, start, end, starts)
        return found

    # ---- what code writes ----------------------------------------------------------------

    def note(self, session) -> str:
        """Which clock the flow periods are dated in, when code chose the birth place's."""
        state = session.state
        if not state.get("timeframe_default"):
            return ""
        period = state.get("bazi_period_result") or {}
        binding = getattr(session, "birth_binding", None) or {}
        place = (binding.get("location") or {}).get("name") or session.profile.get("birth_place")
        note = requirements.Period(
            period.get("start", ""), period.get("end", ""), period.get("tz", ""), True
        ).note(place)
        # Bazi pilot r1: “不用真太阳时，按固定UTC+8” chose the birth clock, which a reader (and the
        # judge) took for the dates' clock. Say that the two are different things.
        chart = (state.get("bazi_result") or {}).get("input") or {}
        clock = "真太阳时" if chart.get("true_solar_time") else "固定UTC+8"
        return f"出生时刻按{clock}排盘；{note}"

    def complete(self, args, session):
        """Owner, 2026-11-08: an overseas birth without a stated residence is dated in the birth
        place's timezone, and the reading says so (as astro_timing, 2026-11-07)."""
        note = self.note(session)
        if not note:
            return
        closing = args.get("closing") or ""
        room = 200 - len(note) - 1
        if len(closing) > room:
            closing = closing[: max(0, room - 1)] + "…" if room > 1 else ""
        args["closing"] = f"{closing}\n{note}" if closing else note

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        state = session.state
        period = state.get("bazi_period_result") or {}
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        what = (
            f"{period['start']}至{period['end']}的八字流年流月计算"
            if question_type == "timing" and period
            else "八字原局的计算"
        )
        if safety_only:
            args = {
                "question_type": question_type,
                "systems_used": ["bazi"],
                "summary": f"这是{what}。这个问题牵涉重大的现实决定，这次不作解读。",
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：现实中的重要决定，请结合专业人士的意见。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出八字解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
            self.complete(args, session)
            return args
        meanings = {}
        for key in ("bazi_result", "bazi_period_result"):
            for item in (state.get(key) or {}).get("interpretations", []):
                meanings[item["ref_id"]] = item.get("meaning") or {}
        groups = {label: [] for label in SECTION_ORDER}
        for fact in facts:
            if fact.label != "约定":
                groups.setdefault(fact.label, []).append(fact)
        rows = []
        for label, group in groups.items():
            for fact in group:
                keywords = "、".join(
                    relevant_keywords(meanings.get(fact.ref, {}).get("keywords"), fact.text)[:3]
                )
                sentence = (
                    f"{fact.text}，常和{keywords}联系在一起。" if keywords else f"{fact.text}。"
                )
                rows.append((label, sentence, fact.alias))
        sections, omitted = keyword_sections(rows)
        if HIGH_RISK.search(risk_text):
            # The question asks for a real decision: the summary answers it before the facts.
            summary = f"不能依据八字作这类重大现实决定。以下是{what}，只能作反思参考。"
        else:
            summary = f"这是{what}。下面先列出各项依据和一般说法，请当作提示参考。"
        advice = ["当作提示：对照自己的安排，选一两件事多留意。"]
        if omitted:
            advice.append(f"篇幅有限：另有{omitted}项依据未在正文展开，已保留在本次计算记录中。")
        args = {
            "question_type": question_type,
            "systems_used": ["bazi"],
            "summary": summary[:200],
            "sections": sections,
            "evidence": evidence,
            "advice": advice,
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了各项的一般说法。"},
            "safety": safety,
        }
        self.complete(args, session)
        return args
