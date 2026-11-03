# r3 全部质量失败归因

共24条原始质量失败：Dream-single 6、Name-single 4、Daily-single 12、Daily-pipeline 2；另两组流水线0。以下均以本轮原答、原理由与计算结果为依据。保留所有布尔评分，不剔除样本，不重评分。助手复核不代表新增人工校准。

## 1. single 未完成导致的失败

| 组 / 回答 | 原失败维度 | 对照原文的归因 |
| --- | --- | --- |
| Dream-single `dream_flood_and_snake#1` | direct_answer、supported_conclusion | 对`站在床上`的未收录校验连续失败，最终`retry_limit`。展示的是“同一处理错误重复出现3次……尚未完成解读”，确实不是解梦回答。 |
| Dream-single `dream_teeth_falling#3` | direct_answer、supported_conclusion | 连续工具校验失败后`retry_limit`；最终只展示未完成说明，未提交解读。 |
| Dream-single `dream_chased_to_exam#3` | direct_answer、supported_conclusion | 同上，最终`retry_limit`，不能用已有关键词代替完成解读。 |
| Dream-single `dream_flood_and_snake#3` | direct_answer、supported_conclusion | 同上，最终`retry_limit`，引用释义为空。 |
| Dream-single `dream_lost_in_mall#3` | direct_answer、supported_conclusion | 达12步上限，最终`limit_reached`；原文明确“尚未完成解读”，本组唯一执行步数失败。 |
| Dream-single `dream_hospital_health#3` | direct_answer、supported_conclusion | 连续校验失败后`retry_limit`；既没回答是否健康预兆，也没回答如何判断检查。 |
| Name-single `name_compound_surname#1` | direct_answer、supported_conclusion | `lookup_meaning`猜key未命中，随后连续五格校验失败，最终`retry_limit`；不能把工具已有的五格当作已呈现给用户的分析。 |
| Name-single `name_compare_two#1` | direct_answer、supported_conclusion | 检索key及两人五格校验重复失败，最终`retry_limit`；没有完成比较。 |
| Name-single `name_compare_two#2` | direct_answer、supported_conclusion | 重复校验失败，最终`retry_limit`；最后回答只是故障说明。 |
| Name-single `name_three_character#3` | direct_answer、supported_conclusion | 重复校验失败，最终`retry_limit`；未解释王小明的三才。 |
| Daily-single `daily_investment_risk#2` | direct_answer、time_consistent、supported_conclusion | 最终`retry_limit`，未提供解读。直接作答和支持性失败成立；时间理由称11月3日不是用户当天，与运行日期及计算日期相矛盾，不能据此另造日期问题。 |

这些归因说明终态为什么失败；未把每个工具错误文字都当成独立证实的模型事实错误。single的2条解梦追问，以及姓名的3条追问、2条text终态有质量评分通过，但未提交，故不进入“已提交质量”的分母。

## 2. Daily-single 已提交质量失败（11条）

| 回答 | 原失败维度 | 原句与复核 |
| --- | --- | --- |
| `daily_today_general#1` | time_consistent、no_fabricated_facts | 共鸣清单把“确实有人……”“有人提议合作或花钱……”当用户经历，叙述失败保留。时间理由把白天/23点的建议当相位现实预测；23点换柱本身正确，不据这一理由自动记事实编造。 |
| `daily_tomorrow_work#1` | time_consistent、supported_conclusion | 原文“下午23点前后”“傍晚之后……偏财”，实际末段只有当地23:00–24:00，确有写作上的时段错误。另有从六合、命运之轮推工作结果/具体安排的支持性争议，原失败保留。 |
| `daily_today_family#1` | no_fabricated_facts | 家庭场景预设导致叙述失败；额外核对发现“凌晨月水四分”实际当地11:29，评委`time_consistent=true`漏判。编造分类为双重，详见分类备注。 |
| `daily_unknown_birth_time#1` | time_consistent | 原答用“白天至约14:00”概括较顺窗口，相关土星相位14:44、木星23:08；未知时辰下本来也有不确定性。该失败涉及时段概括与建议的边界，不等于编造出生资料、宫位或时柱；原评分保留。 |
| `daily_investment_risk#1` | time_consistent、supported_conclusion | 评委称“当前并非11月3日”，缺乏依据；本轮确在该日运行。原文还用上午/傍晚概括相位，并由五行数量、牌面等引出投资相关判断，支持性失败保留，不能因建议方向保守就删除。 |
| `daily_today_general#2` | time_consistent | 除精确时间窗口的写法，原文还有“凌晨火星四分太阳”“凌晨月水四分”“中午前后月冥四分”；实际当地分别08:43、11:29、20:09，确有UTC/当地时间混用。其`no_fabricated_facts=true`原评分保留，此行不新增进编造计数。 |
| `daily_today_family#2` | time_consistent、supported_conclusion、no_fabricated_facts | 月冥当地20:09写成“中午前后”，日柱换段写成“流时”；又推断家人具体反应与用户性格。双重分类。 |
| `daily_today_general#3` | no_fabricated_facts | 把15:00 UTC日界当当地15点、日柱当“壬午时”，并扩展为整个下午/晚上；共鸣清单把一直自己收尾当经历。评委时间布尔为true但理由已承认时段问题，双重分类。 |
| `daily_tomorrow_work#3` | time_consistent、supported_conclusion、no_fabricated_facts | 将当地11月4日主体写成癸未而不是壬午；把当地11月5日00:03、05:45的相位用于11月4日下午/晚间；又从六合外推特定年龄、老关系/同乡人物与资源消息。双重分类。用户出生资料已经预置，评委“未确认出生资料”的附加指责不成立。 |
| `daily_today_family#3` | time_consistent、supported_conclusion、no_fabricated_facts | “莫名火气上头……今天比较明显”、共鸣条目及家庭反应被写得较实，叙述与支持性失败保留。时间线约9/10/20点基本正确；时间失败主要是白天/傍晚建议依据不足，不把这直接算作事实数值编造。 |
| `daily_unknown_birth_time#3` | time_consistent、no_fabricated_facts | 叙述例子虽带“可能表现为”，后续仍直接写用户的误解与低落，保留叙述失败。时间理由错误地拿天王星05:38 UTC核对水星04:30当地；实际水星为前日20:32 UTC=当天04:32。原时间线四个钟点均能对应，另称不是当天同样缺乏依据。 |

## 3. Daily-pipeline 两条失败

两条均一次写成，0修复、0降级、1次模型调用；都不是编造失败。完整理由与原答见`quality-reasons-with-answers.md`。

### `daily_today_general#3`：time_consistent=false

原答明确辛巳仅当地00:00–23:00，壬午及冲合仅当地23:00–24:00，并使用“若这段时间还在沟通”的条件句。实际UTC区间分别为11月2日16:00至11月3日15:00、11月3日15:00至16:00，换算后恰好相同。评委先认可这些标注，也承认没有把相位日期当现实事件日期，随后却用“辛巳偏财段跨11月2日夜”否定当地11月3日主题。这混淆了UTC日期与用户时区，不是产品遗漏跨日说明。原失败保留，不据此改代码或重评分。

### `daily_lucky_color#3`：time_consistent=false、supported_conclusion=false

时间：原答既标明00:00–23:00，又单列23:00–24:00的正财、自刑、破、六合，明确“只适用于这一小时……不是整天的基调”。两段相加完整覆盖当地当天。水海相位11月2日23:27 UTC=11月3日07:27当地，月木相位11月3日10:53 UTC=当地18:53，均在当天。评委以UTC日期不同质疑全天范围，没有对应到一个实际写错的日期或时刻。

支持性：评委称命运之轮逆位只说“反复变化可能令人焦躁”，不能支持准备替代路径；本轮引用释义实际全文为：

> 反复变化可能令人焦躁，适合稳定日常安排并准备替代路径。这是象征性反思线索，不代表事件必然发生。

原答“建议给自己留一条替代路径，比如提前想好**如果**原计划被打断，下一步先做什么”，与给定释义相符，也不是承诺原计划必然中断。三会释义明确写：

> 白话说，就是把同一季节的三个地支看作一组，强调某种力量的集中。

原答写“力量较集中的感觉”，没有断言成格。进一步“适合集中处理同一类事情”的建议是否过度，以及整体稳的措辞是否平衡，仍可作写作边界讨论，但不足以证明事实表、日期或引用校验存在新的确定缺陷。原稿同时专门处理了最后一小时的偏阻信号，并非完全忽略。保留这两个维度的原失败，不据单条争议再调参。

## 4. 冻结判断

以上评分争议不改变原始16/18。三个流水线的已提交质量都不低于同批single。但解梦另有两项确定性误拒已离线复现，见`dream-attribution.md`；所以“没有能定位的代码缺陷”这一冻结条件不满足。本轮不冻结，也不执行最终验收集。
