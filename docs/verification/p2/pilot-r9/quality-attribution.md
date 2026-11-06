# r9 质量、修复与降级归因

本表覆盖全部原始质量失败和全部pipeline修复/降级。原分保留；助手离线复核不是独立人工校准。原文见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)，拒绝稿见 [pipeline-problems-raw.md](pipeline-problems-raw.md)，程序边界见 [validation-findings.md](validation-findings.md)。

| 组别 | 题目/重复 | 终态 | 原质量 | 修复/降级 | 离线归因 |
| --- | --- | --- | --- | --- | --- |
| Dream-single | dream_flood_and_snake#2 | retry_limit | 失败 | 0/无 | 重试上限；多稿对未收录的站在床上、家里进水、不敢下去作解读，记录的闭集校验错误保留。 |
| Dream-single | dream_lost_in_mall#2 | retry_limit | 失败 | 0/无 | 先以词典外改述“手机没电”查询失败，随后连续解读未收录的出口；达到重复失败上限。 |
| Dream-single | dream_hospital_health#2 | retry_limit | 失败 | 0/无 | 三份实际稿与最小对照均复现“自己申请→己申”的普通中文干支误拒；最终失答。 |
| Dream-single | dream_flood_and_snake#3 | retry_limit | 失败 | 0/无 | 将“不敢”作为未收录意象处理，连续提交被拒，最终失答；保留既有闭集范围。 |
| Dream-pipeline | dream_chased_to_exam#1 | submit_reading | 通过 | 1/无 | 解读未收录考场和“跑进考场才发现没复习”，修复1次后通过，无降级。 |
| Dream-pipeline | dream_late_grandmother#1 | submit_reading | 通过 | 1/无 | 复述已接受来源短语“去世的奶奶”时发生归属冲突误拒，修复1次后通过；最小对照已复现。 |
| Dream-pipeline | dream_chased_to_exam#2 | submit_reading | 通过 | 1/无 | 从“没复习”状态作事实表外推断，修复1次后通过，无降级；维持当前闭集。 |
| Dream-pipeline | dream_flood_and_snake#2 | submit_reading | 通过 | 1/无 | 从“不敢下去”等未列事实表的状态作推断，修复1次后通过，无降级。 |
| Name-single | name_compound_surname#1 | retry_limit | 失败 | 0/无 | 三次把“地格三者”误读成地格3；三份实际稿均重现，最终失答。评委又把应用重试提示当作编造运行状态，此指控与真实trace相矛盾；非提交不计入编造分类主表。 |
| Name-single | name_without_lead_in#1 | ask_user | 失败 | 0/无 | 追问扩展至出生日期、地点、时辰和八字，超出五格所需资料，原评分未通过；未提交解读。 |
| Name-single | name_three_character#2 | submit_reading | 失败 | 0/无 | 数值与三才正确，但把象征推断写成生活表现/性格描述，supported_conclusion失败；不改no_fabricated_facts=true。 |
| Name-single | name_career_grid#2 | retry_limit | 失败 | 0/无 | 先猜不存在的释义key，后3稿均把“地格三者”读成地格3；林晓实际地格17，已离线重现。 |
| Name-single | name_compare_two#3 | submit_reading | 失败 | 0/无 | 叙述类：将数理写成人格特质，且“易得助力”扩大/偏离对应释义；数值计算与三才未见该评委指控的错误。 |
| Name-single | name_three_character#3 | submit_reading | 失败 | 0/无 | 叙述类：resonances把被催、受前辈帮助、习惯等写成既往经历；原问题未提供。 |
| Name-single | name_without_lead_in#3 | retry_limit | 失败 | 0/无 | 前两次重复免责声明；其后“外格由天格加地格减人格得18”被截为人格18，实际人格25、外格18。算式解释的误归属已重现，不将其直接当模型算错。 |
| Name-pipeline | name_compare_two#3 | submit_reading | 失败 | 1/keywords | 两稿均因“两个名字：都留意外格2”的冒号破坏集体归属而拒，1次修复后keywords降级。模板罗列各格而未回答哪个更好，direct_answer/supported_conclusion失败。 |
| Daily-single | daily_today_general#1 | submit_reading | 失败 | 0/无 | 原编造维度false，但理由明说不构成明显编造且条件句尚可。保留叙述类指控并记录异议，不以评委不一致重评分。 |
| Daily-single | daily_lucky_color#2 | submit_reading | 失败 | 0/无 | 叙述类：把相位与合冲外推为有人帮忙、好消息延期等具体日常场景；幸运色依据本身成立。 |
| Daily-single | daily_investment_risk#2 | retry_limit | 失败 | 0/无 | 首次提交JSON参数损坏，后3稿被报本命行星相位不符，达到重复失败上限；不补跑、不把终态失败当已提交。 |
| Daily-single | daily_tomorrow_work#3 | submit_reading | 失败 | 0/无 | 事实及叙述类：把丙戌段15:00 UTC写成当地下午三点，实际为23:00；resonances又将临时任务等写成经历。原文另含牌面画面扩写，不据此回写评分。 |
| Daily-single | daily_investment_risk#3 | submit_reading | 失败 | 0/无 | 时区错误同样将乙酉15:00 UTC写成当地下午/傍晚；另从五行计数和星体落陷外推财务决策。该行no_fabricated_facts=true是原分，不将漏判另计成原编造失败。 |
| Daily-pipeline | daily_today_general#2 | submit_reading | 失败 | 0/无 | 评委以时间存疑判false，却承认23:00–24:00在指定日期内；原文分段及Asia/Shanghai标记与实际一致。保留原分，时间维度异议成立。 |
| Daily-pipeline | daily_tomorrow_work#2 | submit_reading | 失败 | 0/无 | 评委把已标上海时区的00:00–17:52和17:52–23:00再次加8小时，且误称缺少23点后丙戌；实际正文写明三段，与真实计算吻合。supported结论的权重/外推理由另存，不能仅消除时区异议就改整体通过。 |
| Daily-pipeline | daily_lucky_color#3 | submit_reading | 失败 | 0/无 | 评委以部分相位UTC日期为11月5日拒绝当日口径；全部精确时刻换算上海时间后均为11月6日。原文也限定23点后最后一小时。保留原分并记录时区异议。 |
| Daily-pipeline | daily_unknown_birth_time#3 | submit_reading | 失败 | 0/无 | 引用支持不足：将合相扩写为认可/交付需求，将三会直接赋予情绪钻牛角尖的意义。条件句与未知时辰限制均保留，no_fabricated_facts=true不改。 |

合计 21 条原始质量失败、5 次pipeline修复、1 条降级；全部108条有评分，无未评分条目。

姓名single另有两条质量通过的追问（name_ambiguous_form#1、name_without_lead_in#2），仍属非提交，不计入已提交解读质量分母。single的重试上限、工具修订不冒充pipeline的repairs计数。

原始编造分类只统计已提交回答，见 [fabrication-counts.md](fabrication-counts.md) 与 [fabrication-review-notes.md](fabrication-review-notes.md)。工程通过、任务完成和保存成功不是同一指标：Daily-single保存17条但任务完成14条，不能用提交率替代。自动comparison“无工具错误”也不是原始engineering_pass（Name-single分别为8和5），本轮审计分别保留。
