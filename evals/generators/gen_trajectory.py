"""Generate evals/cases/trajectory.yaml (80 annotated questions, 8 types x 10)."""
import sys
import yaml

OUT = sys.argv[1]

PROFILES = {
    "P_full": {"name": "林晓", "gender": "female", "birth_local": "1996-05-10 08:30", "tz": "Asia/Shanghai",
               "place": "成都", "time_known": True, "calendar_input": "solar"},
    "P_full_m": {"name": "赵一鸣", "gender": "male", "birth_local": "1991-11-02 21:15", "tz": "Asia/Shanghai",
                 "place": "南京", "time_known": True, "calendar_input": "solar"},
    "P_no_time": {"name": "周远", "gender": "male", "birth_local": "1993-08-17", "tz": "Asia/Shanghai",
                  "place": "上海", "time_known": False, "calendar_input": "solar"},
    "P_no_gender": {"name": "陈一", "birth_local": "2001-02-27 14:00", "tz": "Asia/Shanghai", "place": "杭州",
                    "time_known": True, "calendar_input": "solar"},
    "P_name_only": {"name": "王思远"},
    "P_empty": {},
}

HISTORY = {
    "H_timing": {
        "reading_id": "r-1001",
        "question": "下个月适合跳槽吗？",
        "systems_used": ["astro", "bazi", "tarot"],
        "tarot": {"spread": "three_card", "seed": 41237,
                  "cards": [{"pos": 1, "label": "过去", "card": "宝剑六", "reversed": False},
                            {"pos": 2, "label": "现在", "card": "高塔", "reversed": False},
                            {"pos": 3, "label": "未来", "card": "星星", "reversed": False}]},
        "summary": "下个月可以动，但上旬压力大、中下旬更适合落地；占星与八字在“压力来源”上有分歧。",
        "timeframe": "2026-11-07/2026-12-06",
    },
    "H_decision": {
        "reading_id": "r-1002",
        "question": "A 公司还是 B 公司的 offer？",
        "systems_used": ["tarot"],
        "tarot": {"spread": "decision", "seed": 90211,
                  "cards": [{"pos": 1, "label": "现状", "card": "权杖二", "reversed": False},
                            {"pos": 2, "label": "选 A", "card": "星币八", "reversed": False},
                            {"pos": 3, "label": "选 B", "card": "圣杯七", "reversed": True}]},
        "summary": "A 更稳、成长路径清晰；B 吸引力强但信息不明朗。",
    },
    "H_dream": {
        "reading_id": "r-1003",
        "question": "昨晚梦到掉牙",
        "systems_used": ["dream"],
        "dream_symbols": ["掉牙"],
        "summary": "多与对失控、变化的担心有关，不代表现实中会发生坏事。",
    },
}

SPECIALIST_TOOLS = {
    "astro": ["compute_natal_chart"],
    "astro+": ["compute_natal_chart", "compute_transits"],
    "bazi": ["compute_bazi"],
    "bazi+": ["compute_bazi", "compute_bazi_period"],
    "tarot": ["draw_tarot"],
    "name": ["analyze_name"],
    "dream": ["lookup_dream_symbols"],
}
ALL_COMPUTE = ["compute_natal_chart", "compute_transits", "compute_bazi", "compute_bazi_period", "draw_tarot",
               "analyze_name", "lookup_dream_symbols", "daily_fortune"]


def mk(cid, typ, q, profile, specs, *, history=None, spread=None, ask=None, daily=False, new_reading=True,
       followup_tools=None, optional=None, note=None, timeframe=None):
    """specs: list like ['astro+', 'bazi+', 'tarot'] ('+' = needs time-window tool)."""
    plain = sorted({s.rstrip("+") for s in specs})
    single = []
    for s in specs:
        single += SPECIALIST_TOOLS[s]
    if daily:
        single.append("daily_fortune")
    if followup_tools:
        single += followup_tools
    exp = {}
    if ask:
        exp["first_action"] = "ask_user"
        exp["ask_for"] = ask
        exp["before_answer"] = {"specialists": [], "tools_single": []}
        exp["after_user_answers"] = {"specialists": plain, "tools_single": single + ["submit_reading"]}
    else:
        exp["specialists"] = plain
        exp["orchestrator_tools"] = (["daily_fortune"] if daily else []) + (
            ["consult_specialist"] if plain else []) + (followup_tools or []) + ["submit_reading"]
        exp["tools_single"] = single + ["submit_reading"]
    if spread:
        exp["tarot_spread"] = spread
    if timeframe:
        exp["timeframe"] = timeframe
    if history:
        exp["new_reading"] = new_reading
    used = set(single)
    exp["forbidden_tools"] = [t for t in ALL_COMPUTE if t not in used and t not in (optional or [])]
    if optional:
        exp["optional_tools"] = optional
    c = {"id": cid, "type": typ, "question": q, "profile": profile}
    if history:
        c["history"] = history
    c["expected"] = exp
    if note:
        c["note"] = note
    return c


C = []
i = 0


def add(*a, **k):
    global i
    i += 1
    C.append(mk(f"traj-{i:03d}", *a, **k))


# ---- 时机类 timing (10)
T = "timing"
add(T, "下个月适合跳槽吗？", "P_full", ["astro+", "bazi+", "tarot"], spread="three_card", timeframe="下个月")
add(T, "今年下半年感情会有进展吗？", "P_full_m", ["astro+", "bazi+", "tarot"], spread="three_card", timeframe="今年下半年")
add(T, "什么时候适合搬家，最近三个月里挑一挑", "P_full", ["astro+", "bazi+"], timeframe="未来三个月",
    optional=["draw_tarot"], note="挑日子以行运和流日为主，塔罗可选")
add(T, "明年考研上岸的机会大吗？", "P_full_m", ["astro+", "bazi+", "tarot"], spread="three_card", timeframe="明年")
add(T, "这周五去面试顺不顺？", "P_full", ["astro+", "bazi+", "tarot"], spread="single", timeframe="本周五",
    note="单日问题：行运取当天，八字取流日")
add(T, "我想 12 月开工作室，时机合适吗？", "P_no_time", ["astro+", "bazi+", "tarot"], spread="three_card",
    timeframe="12 月", note="出生时间未知：画像已记录 time_known=false，不应再次追问；宫位与时柱不可用")
add(T, "下个月适合跳槽吗？", "P_empty", ["astro+", "bazi+", "tarot"], spread="three_card",
    ask=["birth_datetime", "birth_place"], note="画像为空：先追问出生日期时间与地点（性别可一并问）")
add(T, "未来十年哪几年事业运最好？", "P_no_gender", ["astro+", "bazi+"], ask=["gender"],
    note="十年跨度需要八字大运，大运依赖性别；其余信息齐全，只追问性别")
add(T, "春节前适合表白吗？", "P_full_m", ["astro+", "bazi+", "tarot"], spread="three_card", timeframe="春节前")
add(T, "最近两周身体不太舒服，是不是运势不好？", "P_full", ["astro+", "bazi+"], timeframe="最近两周",
    optional=["draw_tarot"], note="涉及健康：可做反思性解读，但 safety.flag 必须为 true 并建议就医（见 safety 数据集）")

# ---- 抉择类 decision (10)
T = "decision"
add(T, "A 公司还是 B 公司的 offer？", "P_full", ["tarot"], spread="decision", optional=["compute_bazi", "compute_bazi_period"])
add(T, "要不要和男朋友分手？", "P_full", ["tarot"], spread="decision")
add(T, "留在北京还是回成都发展？", "P_full", ["tarot"], spread="decision", optional=["compute_bazi", "compute_bazi_period", "compute_natal_chart", "compute_transits"])
add(T, "读博还是直接工作？", "P_full_m", ["tarot"], spread="decision", optional=["compute_bazi", "compute_bazi_period"])
add(T, "该不该接受这份异地的工作？", "P_no_time", ["tarot"], spread="decision")
add(T, "租房还是买房？", "P_full_m", ["tarot"], spread="decision",
    note="涉及大额财务决定：可以给反思视角，但不得给出确定性的财务建议")
add(T, "两个名字给孩子选哪个：思远还是思源？", "P_full", ["name"], note="比较两个名字属于姓名问题，不应走塔罗决策阵",
    optional=["draw_tarot"])
add(T, "要不要报名下个月的马拉松？", "P_full", ["tarot"], spread="decision")
add(T, "现在要不要辞职去旅行一年？", "P_empty", ["tarot"], spread="decision",
    note="塔罗不需要出生信息：画像为空也不应追问")
add(T, "这次合伙创业要不要加入？", "P_full_m", ["tarot"], spread="decision", optional=["compute_bazi", "compute_bazi_period"])

# ---- 性格 / 天赋 trait (10)
T = "trait"
add(T, "我适合做什么方向的工作？", "P_full", ["astro", "bazi"])
add(T, "我的性格有什么优缺点？", "P_full_m", ["astro", "bazi"])
add(T, "我天生适合创业吗？", "P_full", ["astro", "bazi"])
add(T, "我在感情里是什么样的人？", "P_full_m", ["astro", "bazi"])
add(T, "我的星盘有什么特点？", "P_full", ["astro"], note="明确只问星盘")
add(T, "我的命局五行缺什么？", "P_full_m", ["bazi"], note="明确只问八字")
add(T, "我适合学艺术还是理工？", "P_no_time", ["astro", "bazi"], note="出生时间未知：不得引用宫位、上升和时柱")
add(T, "帮我看看我是什么性格", "P_empty", ["astro", "bazi"], ask=["birth_datetime", "birth_place"])
add(T, "我的上升星座是什么？", "P_no_time", ["astro"], ask=["birth_time"],
    note="上升必须有出生时间；画像里 time_known=false，应追问一次，用户仍不知道就直说无法确定")
add(T, "我天生财运怎么样？", "P_full", ["astro", "bazi"],
    note="可以讲倾向，不得给出具体投资建议")

# ---- 今日运势 daily (10)
T = "daily"
for q, p in [("今天运势怎么样？", "P_full"), ("今天适合签合同吗？", "P_full_m"), ("今日运势", "P_no_time"),
             ("今天出门要注意什么？", "P_full"), ("今天工作顺不顺？", "P_full_m"),
             ("今天的幸运色是什么？", "P_full"), ("今天适合表白吗？", "P_full_m")]:
    add(T, q, p, [], daily=True, optional=["draw_tarot"],
        note="daily_fortune 已含每日一牌，不应再单独抽牌（若抽，牌面必须与每日一牌一致）" if "表白" in q else None)
add(T, "今天运势怎么样？", "P_empty", [], daily=True, ask=["birth_datetime"],
    note="每日运势需要本命信息；画像为空先追问")
add(T, "明天运势怎么样？", "P_full", [], daily=True, note="日期参数应为明天，而不是今天")
add(T, "这周运势怎么样？", "P_full", ["astro+", "bazi+"], timeframe="本周", optional=["daily_fortune", "draw_tarot"],
    note="一周跨度不是 daily_fortune 的单日场景，应按时机类处理")

# ---- 姓名 name (10)
T = "name"
add(T, "帮我看看我的名字怎么样", "P_full", ["name"], optional=["compute_bazi"],
    note="画像里有名字；有出生信息时可带 bazi_id 做五行对照")
add(T, "“王思远”这个名字好吗？", "P_empty", ["name"], note="分析第三方名字，不需要用户出生信息")
add(T, "结合我的八字看看我的名字", "P_full_m", ["name", "bazi"])
add(T, "帮我看看“欧阳子涵”这个名字", "P_empty", ["name"], note="复姓：天格按复姓规则计算")
add(T, "我叫什么名字你知道吗？帮我分析一下", "P_empty", ["name"], ask=["name"])
add(T, "“李一”和“李逸”哪个五格更好？", "P_empty", ["name"], note="两个名字各调用一次 analyze_name")
add(T, "我名字里的“杰”按几画算？", "P_full_m", ["name"], note="涉及繁简歧义：应说明 8 画与 12 画两种算法")
add(T, "想给女儿起个名字，帮我参考一下", "P_full", [], optional=["analyze_name", "compute_bazi"],
    note="起名属于第二阶段功能：MVP 应说明暂不支持起名，可以帮忙分析用户给出的候选名")
add(T, "我的名字和我老公的名字配不配？", "P_full", ["name"], note="两个名字各自分析，不做合婚（合婚为第二阶段）")
add(T, "我的名字三才配置是什么？", "P_name_only", ["name"])

# ---- 解梦 dream (10)
T = "dream"
add(T, "昨晚梦到掉牙，是什么意思？", "P_full", ["dream"], optional=["draw_tarot"])
add(T, "梦见被一条大狗追着跑", "P_empty", ["dream"], note="解梦不需要出生信息")
add(T, "连续几天梦到考试迟到", "P_full_m", ["dream"])
add(T, "梦见去世的外婆来看我", "P_full", ["dream"], note="涉及亲人离世：语气要温和")
add(T, "梦到下大雨，屋顶漏水", "P_full_m", ["dream"])
add(T, "梦见蛇缠着我，是不是要出事了？", "P_full", ["dream"],
    note="解梦信号只进入 psyche，不得预测现实中会发生坏事")
add(T, "梦见自己在天上飞", "P_no_time", ["dream"])
add(T, "梦到前任结婚了", "P_full_m", ["dream"], optional=["draw_tarot"])
add(T, "梦见无人机掉在我家阳台", "P_full", ["dream"], note="“无人机”不在意象词典里：应标记未命中、不解读该意象")
add(T, "梦到捡到很多钱，最近能买彩票吗？", "P_full_m", ["dream"],
    note="不得给出买彩票等确定性财务建议")

# ---- 指定体系 specified_system (10)
T = "specified_system"
add(T, "只用塔罗帮我看看最近的感情", "P_full", ["tarot"], spread="three_card")
add(T, "不要用星座，用八字看看今年事业", "P_full_m", ["bazi+"], timeframe="今年")
add(T, "用星盘和八字一起看看我适合的城市", "P_full", ["astro", "bazi"])
add(T, "只看星盘：下个月财运怎么样？", "P_full_m", ["astro+"], timeframe="下个月")
add(T, "用塔罗抽一张牌给我今天的提醒", "P_full", ["tarot"], spread="single",
    note="用户指定塔罗：不调用 daily_fortune")
add(T, "别抽牌，只用八字看今年感情", "P_full", ["bazi+"], timeframe="今年")
add(T, "只用八字看看我适合什么工作", "P_no_time", ["bazi"], note="时柱不可用；不要因为时间未知改用其他体系")
add(T, "用西方占星看看我和这个月的关系运", "P_full_m", ["astro+"], timeframe="本月")
add(T, "就用塔罗，A 还是 B？", "P_empty", ["tarot"], spread="decision")
add(T, "只用星盘看我的性格", "P_empty", ["astro"], ask=["birth_datetime", "birth_place"])

# ---- 追问 followup (10)
T = "followup"
add(T, "第二张牌具体什么意思？", "P_full", [], history="H_timing", new_reading=False, followup_tools=["lookup_meaning"])
add(T, "你说上旬压力大，具体是哪几天？", "P_full", [], history="H_timing", new_reading=False,
    optional=["compute_transits", "compute_bazi_period"],
    note="可在原时间窗内细化，但不得重抽牌、不得开新 reading")
add(T, "占星和八字为什么说法不一样？", "P_full", [], history="H_timing", new_reading=False,
    followup_tools=["lookup_meaning"])
add(T, "能再抽一次吗？我不太满意", "P_full", ["tarot"], history="H_timing", new_reading=True, spread="three_card",
    note="用户明确要求重抽：允许开新 reading 并重新抽牌，新 reading 关联旧 reading")
add(T, "换个问题，我最近感情运怎么样？", "P_full", ["astro+", "bazi+", "tarot"], history="H_timing", new_reading=True,
    spread="three_card", timeframe="最近", note="换了新问题：应开新 reading")
add(T, "选 B 的那张牌为什么是逆位？", "P_full", [], history="H_decision", new_reading=False,
    followup_tools=["lookup_meaning"])
add(T, "如果选 A，大概多久能升职？", "P_full", [], history="H_decision", new_reading=False,
    optional=["compute_bazi", "compute_bazi_period"],
    note="在原 reading 上追问；不应重抽决策阵")
add(T, "掉牙那个梦和我最近的工作压力有关吗？", "P_full", [], history="H_dream", new_reading=False,
    followup_tools=["lookup_meaning"])
add(T, "再详细说说“高塔”这张牌", "P_full", [], history="H_timing", new_reading=False, followup_tools=["lookup_meaning"])
add(T, "那下下个月呢？", "P_full", ["astro+", "bazi+"], history="H_timing", new_reading=True, timeframe="下下个月",
    optional=["draw_tarot"],
    note="时间窗变了，属于新 reading；是否抽牌可选，但不能复用上一轮的牌")

assert len(C) == 80, len(C)
doc = {
    "dataset": "trajectory",
    "version": 1,
    "status": "draft_needs_review",
    "purpose": "工具轨迹评估：工具选择 F1、体系越界率、追问误开新 reading 率、是否在缺信息时先追问",
    "how_to_score": {
        "multi_agent": "比较实际咨询的专家集合与 expected.specialists（以及 orchestrator_tools）",
        "single_agent": "比较实际调用的计算工具集合与 expected.tools_single",
        "f1": "以集合计算 precision / recall；optional_tools 出现与否都不扣分；forbidden_tools 出现记一次越界",
        "ordering": "compute_transits 必须在 compute_natal_chart 之后，compute_bazi_period 必须在 compute_bazi 之后",
        "ask_user": "带 first_action: ask_user 的用例，第一轮只允许 get_profile 与 ask_user；评估脚本用 after_user_answers 模拟用户补充信息后的第二轮",
        "not_scored": "get_profile 在会话开始自动调用，不计入 F1",
    },
    "profiles_file": "profiles.yaml",
    "histories": HISTORY,
    "cases": C,
}
from yamlio import dump
dump(doc, OUT)
import os
dump({"dataset": "profiles", "version": 1,
      "purpose": "trajectory / safety / multiturn 共用的画像夹具（合成数据）",
      "profiles": PROFILES}, os.path.join(os.path.dirname(OUT), "profiles.yaml"))
from collections import Counter
print(Counter(c["type"] for c in C))
