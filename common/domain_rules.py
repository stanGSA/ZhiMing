"""Domain instructions delivered by start_reading, leaving the system prefix stable."""

RULES = {
    "astro": "性格用本命；时机题须compute_transits，用户指定日期含首尾，不把精确相位日期当现实事件日期。未知时辰不解读宫位四轴；职业题回答工作方式，职业名称只作待验证例子。",
    "bazi": "birth_local和tz为原始出生钟表资料，内部完成转换；默认公历、next_day、true_solar_time=false，海外须确认口径，农历须确认闰月。起运/首步/当前大运说明直接用compute_bazi的dayun、current_candidates和interpretations提交，可用question_type=timing；不为此补算流年流月，不猜大运干支作为god_pillar的key。指定日期运势或行动时机才须compute_bazi_period，year最多3660天、month/day最多366天，节气流月不当公历整月。确需首运与当前区间比较时分别用scope=dayun_first/dayun_current，不能拼接两段端点。start_age是传统岁数，年份标记不代表年初交运。喜用倾向须结合月令与五行说明依据。dayun_time_basis默认civil，physical仅用户要求时使用。",
    "tarot": "single=单张、three_card=过去/现在/未来、decision=现状/A/B。遵守requested_spread，draw_tarot已给精确释义，不重复查询。追问读取旧记录，不重抽。",
    "name": "姓名逐字来自原话，复姓分开；两个名字分别analyze_name，结合八字时先计算并传bazi_id。笔画按康熙繁体；ambiguities的confirmation_prompts写入advice请确认，查不到用ask_user。起名合婚属后续功能，不作数理命运断言。",
    "dream": "从梦境原话抽连续phrase及规范symbol，一次lookup_dream_symbols；只解释hits，misses说明未收录。解梦不写timeline，仅谈心理感受，不谈预兆或现实必发事件。",
    "daily": "今天/明天运势只调用一次daily_fortune，按日历基准定日期，不另排盘抽牌。幸运色说明是流日天干五行的传统配色约定。缺资料按needs_input追问；一周以上按时机题。",
}


def rules_for(systems):
    return {system: RULES[system] for system in systems if system in RULES}
