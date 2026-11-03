# P2 r4：全部质量失败及未评分归因

逐条复核原答、评委理由、计算事实及相关trace；助手复核不替换原始评分。每次pipeline修复及降级另见解梦、姓名归因。

| 回答 | 终态 | 原失败维度 | 复核依据 |
| --- | --- | --- | --- |
| `Dream-single/dream_chased_to_exam#1` | retry_limit | direct_answer, supported_conclusion | 重试耗尽，最终错误提示未作答；原追赶命中、考场等未命中，未产生解读。 |
| `Dream-single/dream_flood_and_snake#1` | retry_limit | direct_answer, supported_conclusion | 反复解释未命中的不敢下去，重试耗尽；最终错误提示无结论。 |
| `Dream-single/dream_lost_in_mall#1` | retry_limit | direct_answer, supported_conclusion | 手机没电等抽取规范化反复不获授权，查询失败后重试耗尽；最终未作答。 |
| `Dream-single/dream_lost_in_mall#2` | retry_limit | direct_answer, supported_conclusion | 查询和输出校验反复失败，涉及没电、找不到出口等；最终错误提示无结论。 |
| `Dream-single/dream_teeth_falling#3` | retry_limit | direct_answer, supported_conclusion | 牙齿、画等输出校验失败后耗尽重试；single没有pipeline的原话映射。原错误提示未作答。 |
| `Dream-single/dream_chased_to_exam#3` | submit_reading | 未评分 | 成功提交但评委两次JSON解析失败，保留未评分；不能补判通过。 |
| `Dream-pipeline/dream_lost_in_mall#3` | model_error | 未评分 | 运行模型APITimeoutError，评委三次请求也超时，model_error且未评分；不是规则修复或降级。 |
| `Name-single/name_without_lead_in#1` | ask_user | direct_answer, supported_conclusion | 索取五格不需要的出生日期、地点和时辰；仅姓名字形确认合理，未完成原任务。 |
| `Name-single/name_compound_surname#2` | submit_reading | no_fabricated_facts | 数理象征写成使用者经历；另有木生水的方向错误。原评分与双重分类依据见fabrication-review-notes.md。 |
| `Name-single/name_three_character#2` | retry_limit | direct_answer, supported_conclusion | 数理四吉一凶的四误识别为数理值4，已离线复现；最终重试耗尽，未作答。 |
| `Name-single/name_ambiguous_form#3` | retry_limit | direct_answer, supported_conclusion | 人格是五格里的五误识别为人格5，已离线复现；最终重试耗尽。 |
| `Name-single/name_compare_two#3` | retry_limit | direct_answer, supported_conclusion | 总格三项的三误识别为总格3，已离线复现；最终重试耗尽。 |
| `Name-single/name_career_grid#3` | retry_limit | direct_answer, supported_conclusion, no_fabricated_facts | 地格三个位置的三误识别为地格3，已离线复现；最终重试耗尽。评委编造false理由没有指明编造，保留原判，未提交不进入分类表。 |
| `Daily-single/daily_today_general#1` | submit_reading | time_consistent, supported_conclusion, no_fabricated_facts | 当地08:43误称凌晨、壬午流日误称时辰；对用户当日事件作具体扩展，事实/叙述双重分类。 |
| `Daily-single/daily_unknown_birth_time#1` | submit_reading | no_fabricated_facts | UTC15:08、15:00误作当地下午3/4点，实际23:08、23:00；并外推具体生活场景。原时间true漏判已说明。 |
| `Daily-single/daily_investment_risk#1` | retry_limit | direct_answer, time_consistent, supported_conclusion | 相位检查反复失败，最终错误提示未作答；原摘要今日火星四分本命太阳缺少行运标记而走本命检查，离线加行运两字后接受。不是事实中不存在该事件。评委以日期不一致判时间false但无比较时点依据，原分保留。 |
| `Daily-single/daily_today_general#2` | submit_reading | no_fabricated_facts | no_fabricated_facts=false与评委文字整体尚可互相矛盾；原答月金六分凌晨表述、行运/本命宫位混述有可核错误，分类事实类。 |
| `Daily-single/daily_unknown_birth_time#2` | submit_reading | no_fabricated_facts | 具体心理与场景外推，分类叙述类；辛金、三柱、年柱正印/月柱伤官都在实际事实表，不能称这些本身捏造。 |
| `Daily-single/daily_today_general#3` | submit_reading | time_consistent, supported_conclusion, no_fabricated_facts | 月冥刑当地20:09误置下午；牌义与当日心理具体扩展，双重分类。原文已说明23点换日，不仅凭晚间一词否定。 |
| `Daily-single/daily_today_family#3` | submit_reading | time_consistent | 摘要说17点流日换段，正文另一处说23点，内部矛盾；实际23点换段。原编造true保留，牌面画面额外扩展单独备注。 |
| `Daily-single/daily_lucky_color#3` | submit_reading | no_fabricated_facts | 月木六分10:53UTC、换段15UTC误当当地10:53和15点；外推已做不少却无人肯定等处境。原时间true漏判保留。 |
| `Daily-pipeline/daily_lucky_color#1` | submit_reading | supported_conclusion | 原支持性false保留。四项壬午关系的ref_id都绑定15:00UTC段，换算当地23点，故评委称缺少最后一小时依据不符合事实。星币国王逆位措辞强弱仍可讨论，不据复核改分。 |
| `Daily-pipeline/daily_lucky_color#3` | submit_reading | time_consistent | 原时间false保留，但理由承认水海当地07:27、月木18:53均当天且边界正确，未指出实际冲突；原答并未给错误时刻，属于判定与理由不一致。 |

共23条：21条原quality_pass=false，2条quality_pass=null。全部失败原文与理由见[完整证据](quality-reasons-with-answers.md)。两条未评分分别为single已提交解析失败和pipeline未提交服务超时；未评分不是质量通过。

Daily-pipeline的两条失败均无修复/降级，编造维度均true。两个幸运色回答均按当地00:00–23:00和23:00–24:00渲染流日；第一条关系引用绑定该段，第二条的时间false理由与原文无法对上。保留原16/18，不用离线复核替换评委评分。

Dream-single有一条已提交未评分，因此六组编造分类表中该组仍“不完整”；所有已评分的编造失败已逐条分类，不能将此称六组全部完整。
