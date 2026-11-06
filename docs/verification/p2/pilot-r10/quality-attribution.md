# r10 质量、修复、降级与未评分归因

助手离线复核，非独立人工校准；全部原始评分保留。覆盖质量失败、未评分、pipeline修复/降级及所有非提交终态。原文见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)，程序边界见 [validation-findings.md](validation-findings.md)。

| 组别 | 题目/重复 | 终态 | 原质量 | 修复/降级 | 离线归因 |
| --- | --- | --- | --- | --- | --- |
| Dream-single | dream_hospital_health#1 | text | 通过 | 0/无 | 文本终态，未提交；额外索要出生资料。评委全部通过，但这不是已完成梦境解读；保留原分并记录追问范围异议。 |
| Dream-single | dream_chased_to_exam#3 | retry_limit | 失败 | 0/无 | 两次查询参数被拒；提交又因未收录情境及否定并列句“不作诊断或预兆/预示解读”被拒，最终重复失败失答。否定范围误拒已复现，不将全部失败都归于误拒。 |
| Dream-pipeline | dream_chased_to_exam#1 | submit_reading | 通过 | 1/无 | 事实表外“才发现/没复习”的解读被拒，修复1次后通过，无降级；维持现有闭集边界。 |
| Dream-pipeline | dream_late_grandmother#2 | submit_reading | 通过 | 1/keywords | 两稿“这个梦没有预示什么”被误判预言，修复1次后keywords降级；原分是降级稿全部通过，新旧B均阻断。 |
| Dream-pipeline | dream_flood_and_snake#2 | submit_reading | 通过 | 1/无 | 事实表外“不敢下去”的解读被拒，修复1次后通过，无降级。 |
| Dream-pipeline | dream_flood_and_snake#3 | submit_reading | 通过 | 1/无 | 事实表外“上不敢下去”的解读被拒，修复1次后通过，无降级。 |
| Name-single | name_career_grid#1 | ask_user | 通过 | 0/无 | 追问用字、本名/艺名及行业方向，未提交；原质量全部通过。已有姓名仍被扩展追问，单独记录任务未完成。 |
| Name-single | name_without_lead_in#2 | ask_user | 通过 | 0/无 | 追问简繁、是否本人及出生资料，未提交；原质量全部通过。出生资料非五格必需，保留原分并记录异议。 |
| Name-single | name_without_lead_in#3 | ask_user | 通过 | 0/无 | 追问写法及可选出生资料，未提交；原质量全部通过。不把追问质量通过计为保存成功。 |
| Name-single | name_career_grid#3 | ask_user | 通过 | 0/无 | 追问用字、晓的简繁体及出生日期，未提交；原质量全部通过。出生日期非五格必需，保留原分。 |
| Name-pipeline | name_without_lead_in#2 | submit_reading | 通过 | 1/keywords | 两稿“五格数理是一套民间取名习俗”被读成数理1，修复1次后keywords降级；完整回放及最小对照确认，新旧B均阻断。 |
| Name-pipeline | name_career_grid#3 | submit_reading | 未评分 | 0/无 | 已提交，但评委两次返回末尾为],}的非法JSON，原scored=false；未补评，不能按回复中声称的true填分。 |
| Daily-single | daily_today_general#1 | retry_limit | 失败 | 0/无 | 先有JSON引号错误，后三次报本命相位不符，最终失答；实际稿与Astro校验错误可复现，行运/本命上下文尚未隔离为单一误拒。评委将真实错误提示判编造与trace矛盾；非提交不进入编造主表。 |
| Daily-single | daily_tomorrow_work#1 | submit_reading | 失败 | 0/无 | supported_conclusion失败：将象征线索外推为临时改需求、交接不全等工作场景。原no_fabricated_facts=true保留。 |
| Daily-single | daily_today_family#1 | submit_reading | 失败 | 0/无 | 真实时间错误：把23:00才切换的乙酉写成“傍晚起”；相位UTC换算后在当日。原no_fabricated_facts=true，不回写其他维度。 |
| Daily-single | daily_unknown_birth_time#1 | submit_reading | 失败 | 0/无 | 叙述类：把旧友出现、走神等列为彼此呼应。评委指三张牌编造有异议：tarot.cards实际记录这三张，不能只看每日一牌。另有21:00换日段的真实错误（实际23:00），原time_consistent=true保留。 |
| Daily-single | daily_investment_risk#1 | submit_reading | 失败 | 0/无 | 事实/叙述类混合指控：“年支子、日时之类形成申子辰”参与归属含糊；实际年子、时辰与流日申可成局，日支未不属该组合，不能把“日时之类”当严谨事实。确定性时段及心理场景外推另记，不改原分。 |
| Daily-single | daily_tomorrow_work#2 | submit_reading | 失败 | 0/无 | 叙述类：把改时间、方案重做、同事分工争议等写成当天场景；另有精确相位/日段到作息的外推。保留原三维失败。 |
| Daily-single | daily_today_family#2 | submit_reading | 失败 | 0/无 | 时间/依据失败：将凌晨精确相位外推到傍晚情绪，合关系过度有利化。该条通过单项工具计算，无daily_result但有实际transit_result和bazi_period_result；原no_fabricated_facts=true。 |
| Daily-single | daily_unknown_birth_time#2 | submit_reading | 失败 | 0/无 | 叙述类：临时约饭、谈副业、被善待等写成当天场景，未知时辰仍细化时段；保留时间/依据/编造三维原失败。 |
| Daily-single | daily_unknown_birth_time#3 | retry_limit | 失败 | 0/无 | 三稿均将“交际活跃度上升”误读成上升星座，实际Astro校验和最小对照已复现，最终失答。稿件同时有15:00北京时间换段（实际23:00）和牌面画面扩写，不能声称整稿本来合格。 |
| Daily-single | daily_investment_risk#3 | submit_reading | 失败 | 0/无 | 叙述类：“有人给你一个看似不错的投资建议”列为彼此呼应，未由用户提供；原其他三维通过。 |
| Daily-pipeline | daily_tomorrow_work#1 | submit_reading | 失败 | 0/无 | 原supported_conclusion失败：关系衔接与平稳总评支持不足；原no_fabricated_facts=true。评委对合/破/刑的混合叙述有疑义，保留原分。 |
| Daily-pipeline | daily_investment_risk#1 | submit_reading | 通过 | 1/safety | 两稿“不把…当稳赚信号”误拒，修复1次后safety降级；共用hard_claim谓词及最小对照确认。原分为降级安全答复全部通过；新旧B均阻断。 |
| Daily-pipeline | daily_tomorrow_work#3 | submit_reading | 失败 | 0/无 | 时间失败存在评委事实错误：实际17:52–23:00仍乙酉，非其声称的丙戌；正文“仅00:00–17:52”确有限定，并未直接把乙酉标成全天。但缺少后两段的全面说明仍可单记，不能据此自动改为通过。 |
| Daily-pipeline | daily_today_family#3 | submit_reading | 失败 | 0/无 | 时间/依据失败存在异议：正文没有评委声称的21:18Z时刻，并明确23点后仅当天最后一小时；高塔释义实际含“原有预期受到挑战时先检查基础条件”，不是只有免责声明。卡牌被放在最后一小时的衔接仍有讨论空间，保留原分。 |

合计 14 条原始质量失败、1 条未评分、6 次pipeline修复、3 条降级；归因覆盖 26 条。

Dream-single 的质量17/18中包含1条文本回复；Name-single的质量18/18包含4条追问。Daily-single保存16条但任务完成8条。提交、任务完成、工程通过和质量评分分别统计，不能互换。
