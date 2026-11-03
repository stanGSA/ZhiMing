# P2 r5：质量失败归因

逐条保留自动评委的原评分和理由；本表不改分。全部 108 条均已评分。

| 批次 | 失败回答 | 失败维度 | 归因 |
| --- | --- | --- | --- |
| Dream-single | `dream_flood_and_snake#1/#2`、`dream_teeth_falling#2`、`dream_chased_to_exam#3`、`dream_lost_in_mall#3` | direct_answer、supported_conclusion | single 模式重试耗尽，报告为处理错误而没有解读；保留未完成，不视为有效回答。 |
| Name-single | `name_compound_surname#1/#3` | no_fabricated_facts | 将五格象征扩写成用户既有家庭支持、关系和经历；属叙述类，需使用条件句/自我观察方式。 |
| Name-single | `name_compare_two#1/#2`、`name_three_character#1/#3` | direct_answer、supported_conclusion | 重试耗尽或追问，没有完成用户要求的姓名比较/三才解释；未编造事实，但任务未完成。 |
| Name-pipeline | `name_compare_two#1` | direct_answer、supported_conclusion | 分列两个人名五格，没有回答哪个更好，缺少比较结论。 |
| Name-pipeline | `name_career_grid#3` | direct_answer、supported_conclusion | 罗列五格但没有回答哪个格最重要及对事业的帮助。 |
| Daily-single | `daily_today_general#1/#2`、`daily_today_family#1/#2`、`daily_investment_risk#2` | time_consistent（部分另有其他维度） | 将精确相位/流日边界映射为不准确的本地时段，或把短时流日段写成白天/傍晚趋势。原理由及具体时刻见完整质量报告。 |
| Daily-single | `daily_today_family#1/#2`、`daily_today_general#2`、`daily_tomorrow_work#2`、`daily_investment_risk#2` | no_fabricated_facts | 其中 #1 family 将象征推成具体家庭/身体场景；#2 general、tomorrow work、investment 将象征写成具体经历/时段；归为叙述类。 |
| Daily-single | `daily_unknown_birth_time#2`、`daily_today_general#3` | no_fabricated_facts | 分别把未由用户提供的生日当作已知资料，以及引用事实表未提供的天干相冲；归为事实类。 |

编造失败共 8 条，Name-single 2 条叙述类；Daily-single 3 条事实类、3 条叙述类；无待复核项。六组计数完整，见 [分类计数](fabrication-counts.md) 和 [逐条分类依据](fabrication-review-notes.md)。全部原始评委理由与回答见 [质量理由与回答全文](quality-reasons-with-answers.md)。

## 修复与降级

Dream-pipeline 的 8 次修复：`dream_chased_to_exam#1/#3`、`dream_flood_and_snake#1/#2/#3`、`dream_lost_in_mall#1/#2/#3`；其中 `dream_flood_and_snake#1` 另有 1 次 `keywords` 降级。拒绝稿候选句及错误类别见 [解梦问题报告](pipeline-problems-raw.md)。复核发现“商场里找不到出口”等措辞来自用户原句“到处找不到出口”，仍被当作事实表外片段拒绝，是本轮可定位的解梦校验误拒；因此不满足冻结条件。

Name-pipeline 的 4 次修复/4 次降级分别是 `name_ambiguous_form#1/#3`、`name_compare_two#1`、`name_career_grid#3`，均降级为 `keywords`。最终提交保留一般数理解释；两条质量失败是未正面回答姓名比较和事业/格数优先级问题（见上表）。每日运势流水线无修复或降级。没有请求服务错误，也没有步数/预算失败。
