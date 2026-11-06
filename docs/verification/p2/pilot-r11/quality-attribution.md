# r11 异常与修复归因

助手离线复核，非独立人工校准；保持所有原始评分。覆盖质量失败、非提交终态和全部流水线修复/降级，共29条。

| 组别 | 题目/重复 | 终态 | 原质量 | 离线归因 |
| --- | --- | --- | --- | --- |
| Dream-single | dream_hospital_health#1 | retry_limit | 失败 | 3 次提交因住院未收录被拒。草稿包含否定未来住院、明确说明未收录及现实就医建议；逐字段回放还把现实医院提及判成未命中意象。记录范围误拒线索，不把原稿其他推断都认作合格。 |
| Dream-single | dream_teeth_falling#3 | retry_limit | 失败 | 初次规范词查询被拒；首稿“不是任何现实事件的预兆”仍误拒，之后心里很慌未收录及其说明多次被拒，最终失答。最小预兆句已复现误拒，不能将整段失答只归给它。 |
| Dream-single | dream_chased_to_exam#3 | retry_limit | 失败 | 奔跑规范词查询、考场/一直跑未收录解读及预兆句先后被拒；没有最终提交。原始 errors 保留在 validation-diagnostics.json。 |
| Dream-pipeline | dream_chased_to_exam#1 | submit_reading | 通过 | 两稿被事实表外情境检查拒绝，分别点名“发现”“跑进一个需要应对”，keywords 降级。两句分开检查均通过，合并则拒，故逐句重跑找不到引句。原稿确把未收录考场/没准备的转折解释为压力，仍属于待厘清的闭集边界；不能仅凭错误标签奇怪就判整稿被误拒。 |
| Dream-pipeline | dream_flood_and_snake#1 | submit_reading | 通过 | 事实表外反应“看得见却不敢下去”解读被拒；有引句，改写后提交，不降级。 |
| Dream-pipeline | dream_hospital_health#1 | submit_reading | 通过 | 复述生病住院并联想到身体敏感的句子被拒；提示引用该句，修复后提交。 |
| Dream-pipeline | dream_chased_to_exam#2 | submit_reading | 通过 | “梦里逃跑的终点”被读为未命中逃跑，提示引句后修改并通过。被追释义本身含逃跑，但既有别名绑定边界未覆盖此表达；本轮无降级。 |
| Dream-pipeline | dream_chased_to_exam#3 | submit_reading | 通过 | 首稿因跨句情境归属被标“发现”不在事实表，引句为空，仍修复成功，无降级。 |
| Dream-pipeline | dream_flood_and_snake#3 | submit_reading | 通过 | 摘要中不敢下床的解释被闭集规则拒绝；有引句，修复后提交。 |
| Dream-pipeline | dream_lost_in_mall#3 | submit_reading | 通过 | 两项迷路/出口变体被拒，其中一项有引句；修复后提交。受控“找不到出口”和更复杂的“没找到出口”覆盖不同，保留边界证据。 |
| Dream-pipeline | dream_hospital_health#3 | submit_reading | 通过 | 住院复述及“比担心梦的预兆更有用”被拒，两项都有引句并修复通过。后一项为否定/劝解措辞误拒，最小对照已复现，无降级。 |
| Name-single | name_ambiguous_form#1 | text | 通过 | 普通文本输出伪 result/tool 片段及虚构 needs_input 规则，没有真实完成姓名计算；评委判通过，记录异议，任务不算完成。 |
| Name-single | name_compare_two#1 | text | 通过 | 普通文本追问写法、关注点及出生资料，未提交；原质量通过，但不算计算完成。 |
| Name-single | name_without_lead_in#1 | ask_user | 失败 | ask_user 索取使用状态、出生日期等非五格必需资料；原质量失败，未提交。 |
| Name-single | name_career_grid#1 | text | 通过 | 普通文本索取写法、笔画口径和出生资料，未提交；原质量通过，扩展追问必要性有异议。 |
| Name-single | name_compare_two#2 | retry_limit | 失败 | 3 次提交均因重复免责声明被拒，达到重试上限；保留原始失败。 |
| Name-single | name_without_lead_in#2 | text | 通过 | 普通文本追问写法及出生年月日地点等非必要信息，未提交；原质量通过，不算计算完成。 |
| Name-single | name_three_character#3 | retry_limit | 失败 | 地格2与计算不符反复被拒，另有 lookup_meaning 缺条目，最终失答；不认作已隔离误拒。 |
| Name-single | name_career_grid#3 | ask_user | 失败 | ask_user 索取额外姓名/口径资料，未提交且原质量失败。 |
| Name-pipeline | name_ambiguous_form#1 | submit_reading | 通过 | “不能据此说你一定会遭遇什么”被确定性校验误拒，提示引句后改写成功，无降级。 |
| Name-pipeline | name_compare_two#2 | submit_reading | 通过 | 展开后的“地格李娜的地格1111数”确有重复拼接错值；提示引出该句，修复后提交。 |
| Daily-single | daily_today_family#1 | submit_reading | 失败 | 真实时间错误：23:00换日写成傍晚；no_fabricated_facts 的失败指控属于叙述场景外推，具体相位/本命落座被评委明确承认为真实。 |
| Daily-single | daily_lucky_color#1 | submit_reading | 失败 | 编造维度主要指控容易/可能类心理场景被写实，归为叙述类并保留尺度异议；23点换日正确。 |
| Daily-single | daily_investment_risk#1 | retry_limit | 失败 | 地名输入被拒后，3 稿又因原局柱位与干支归属不符拒绝，最终失答；未隔离具体唯一触发句，不宣称误拒。 |
| Daily-single | daily_tomorrow_work#2 | submit_reading | 失败 | 确有节气换月17:52写成14:00/13:52的事实错误；编造维度理由主要为具体工作场景外推，按其指控归叙述类，另列时间错误。 |
| Daily-single | daily_today_family#2 | retry_limit | 失败 | 性别输入无依据、释义缺条目，随后原局柱位/干支错误3次拒绝，最终失答；未把其全部归为误拒。 |
| Daily-single | daily_lucky_color#3 | submit_reading | 失败 | 原评分指控事实+叙述两类：将本命月亮天蝎写入当日段落，及场景外推。前者原文未明说行运月亮，存在本命/行运指代异议；保留原分和指控分类，不把该项宣布为已确认事实编造。白天概括凌晨相位另记时间失分。 |
| Daily-single | daily_investment_risk#3 | retry_limit | 失败 | 本命行星相位不符3次拒绝，失答。评委却以2026-11-06不是今天、未作答等理由判no_fabricated_facts=false；实验发生在本地11月6日且失败提示没有事实编造，明确记录评委维度混淆，不改原分。 |
| Daily-pipeline | daily_investment_risk#1 | submit_reading | 通过 | 否定收益句仍触发 hard_claim=稳赚，提示引用原句后改写通过，无降级。共用谓词最小回放确认误拒，不代表全transaction回放。 |

原始质量失败14条，无未评分；11次pipeline修复，1条降级。Name-single的4条文本虽然原评分通过，均未完成提交。Daily-single提交15条、质量通过11条，而既有task_success指标为10；指标按原定义分别保留。

修复引句：11次修复中9次有引句，2次没有；9次有引句均不降级，被引用的整句在后续修复稿/最终答案中均不再原样出现。该结果只证明字符串层面的改写，不证明语义问题全部解决或改写由提示单独造成。
