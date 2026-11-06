# r12 异常与修复归因

助手离线复核，非负责人或独立人工校准。保留所有原始评分；覆盖质量失败、未提交、流水线修复/降级，共32条。

| 组别 | 题目/重复 | 终态 | 原质量 | 归因与限定 |
| --- | --- | --- | --- | --- |
| Dream-single | dream_lost_in_mall#1 | retry_limit | 失败 | 未收录手机没电的原文规范化被拒，后续提交又反复解读该意象，达到重试上限；不把整条失答认作已隔离误拒。 |
| Dream-single | dream_hospital_health#1 | retry_limit | 失败 | 三次提交均报医院不是本次命中意象，最终失答；需要区分现实就医建议与梦境意象，原始工具参数保留供复核，尚未逐句隔离。 |
| Dream-single | dream_chased_to_exam#2 | retry_limit | 失败 | 三次提交因考场未收录仍被解读而拒，最终失答。 |
| Dream-single | dream_hospital_health#2 | ask_user | 失败 | 追问出生日期、时辰、城市及身体症状，未正面回答梦与检查的关系；解梦不需要出生信息。 |
| Dream-single | dream_chased_to_exam#3 | retry_limit | 失败 | 没准备与原文什么都没复习的规范化失败，随后预兆及考场未收录检查反复拒绝，最终失答。 |
| Dream-single | dream_flood_and_snake#3 | retry_limit | 失败 | 站在床上未收录解读与预兆检查被拒，最终失答；可能混有否定措辞误拒，未将全部失败归为单一原因。 |
| Dream-single | dream_hospital_health#3 | retry_limit | 失败 | 住院未收录、预兆检查及末次verdict枚举不合法先后失败，未完成提交。 |
| Dream-pipeline | dream_chased_to_exam#1 | submit_reading | 失败 | 没复习的解释被闭集规则拒，有引句且改写后提交。原评分编造失败归叙述类；评委所引手头事情多、事情一件接一件分别位于如果及自查问句，存在尺度异议；另有这段时间不太有真正放松的间隙等直接推断，不能因此宣布整条合格。 |
| Dream-pipeline | dream_flood_and_snake#1 | submit_reading | 通过 | 首稿解读未收录站在床上及事实表外床上情境，有三项引句。修复稿改写了原句，仍用这种保持距离的反应承接事实表外水里游来游去，被再次拒绝后keywords降级。与现有禁止泛指承接的规则一致，未确认为误拒。 |
| Dream-pipeline | dream_flood_and_snake#2 | submit_reading | 通过 | 蛇在水里游来游去被进一步解释为不安活动，触发事实表外情境校验；引句后修复成功，无降级。 |
| Dream-pipeline | dream_hospital_health#2 | submit_reading | 通过 | 而不是身体疾病的预兆属于否定预兆，但被预兆规则误拒；原句最小离线复现，提示引句后改写成功，无降级。 |
| Dream-pipeline | dream_chased_to_exam#3 | submit_reading | 通过 | 标题跑进考场又发现没复习触发考场未收录检查，有引句，修复后通过。 |
| Name-single | name_compound_surname#1 | retry_limit | 失败 | 人格1、天格2与计算不符及猜测释义key失败，达到重试上限。 |
| Name-single | name_without_lead_in#1 | ask_user | 通过 | 追问姓名写法、本人关系及可选出生资料；原评分通过，但未完成姓名计算提交。 |
| Name-single | name_career_grid#1 | ask_user | 通过 | 追问本人关系、出生信息，要求额外确认只评名字；原评分通过，任务未完成。 |
| Name-single | name_ambiguous_form#2 | retry_limit | 失败 | 先遇工具参数JSON错误，后因正文重复免责声明反复拒绝，最终失答。 |
| Name-single | name_compound_surname#2 | retry_limit | 失败 | 猜测释义key失败及天格2数值错误反复拒绝，最终失答。 |
| Name-single | name_without_lead_in#2 | ask_user | 通过 | 追问繁体、性别、生年及姓名关系，原评分通过，但这些不是五格计算全部必需信息，未完成提交。 |
| Name-single | name_ambiguous_form#3 | ask_user | 通过 | 把生年称为五格必要信息，转为追问出生年月日地点；原评分通过但任务未完成，必要资料依据存疑。 |
| Name-single | name_without_lead_in#3 | ask_user | 通过 | 追问本人关系、出生日期地点和写法，原评分通过但未完成计算提交。 |
| Name-pipeline | name_compare_two#1 | submit_reading | 失败 | 李娜段落写外格张伟的外格2，跨人引用/表达归属混淆。评委列为事实类；两人外格均2，且文字仍明写张伟，不能宣称发现了错误格数。保留对象归属错误指控和上述限定，不改原分。 |
| Name-pipeline | name_career_grid#2 | submit_reading | 通过 | 其中人格一格最值得留意被读成林晓人格1，与原计算24冲突；实为量词表达误拒。提示准确引句后改写成功，无降级。 |
| Daily-single | daily_today_general#1 | submit_reading | 失败 | 实际流日丙戌从上海23:00开始，正文及时间表写15:00后，UTC直接当本地时间。评委另有五分相字样与原文三分相不符，不影响已核实的换日错误。 |
| Daily-single | daily_tomorrow_work#1 | submit_reading | 失败 | 同一答复将丁亥说成第二天，又在时间表注明11月8日23点后，存在日界措辞冲突；原时间失分保留。 |
| Daily-single | daily_unknown_birth_time#1 | submit_reading | 失败 | 流日15:00与相位上午/傍晚存在UTC本地混用；代理月亮狮子被用为确定性格、消息邀约等场景外推。按评委指控记事实+叙述，但狮子来自实际代理计算，不是凭空编造落座；真实问题包括不确定性表述与推断尺度。评委把部分UTC流日段当本地正确，另记异议。 |
| Daily-single | daily_today_general#2 | submit_reading | 失败 | 将23:00流日切换写成15点后，23:49金星相位概括成下午，时间及支持结论两项失败；原评分编造维度仍通过，不回写。 |
| Daily-single | daily_tomorrow_work#2 | submit_reading | 失败 | 将UTC相位时刻1:15、11:53、15:42直接套上海时间，流日交接也写15点前后，时间失分有实际证据。 |
| Daily-single | daily_unknown_birth_time#2 | submit_reading | 失败 | 写上午后段约北京时间17:53及15点整流日切换，确有时间口径混乱。编造指控主要是长辈上级配合、有人要表态等场景外推，记叙述类。评委称少火少水即旺衰定论、丙戌是时柱、乙木流日不能说木旺等理由含过度解释或概念混淆，保留异议。 |
| Daily-single | daily_today_general#3 | submit_reading | 失败 | 月亮三分金星23:49上海时间被写下午傍晚15:49，是时区换算错误。 |
| Daily-pipeline | daily_tomorrow_work#1 | submit_reading | 通过 | 别把合得来当成事情必然顺利为否定确定性的说明，仍被必然规则误拒；准确引句后改写通过，无降级。 |
| Daily-pipeline | daily_investment_risk#1 | submit_reading | 失败 | 原时间失分有明确评委异议：回答和计算均为乙酉00:00–17:52、17:52–23:00，丙戌23:00–24:00；评委自己列出相同区间却称不一致。离线逐段核对一致，原分保留。 |
| Daily-pipeline | daily_unknown_birth_time#2 | submit_reading | 失败 | 原时间失分理由仅称2026-11-07不是今天。本轮上海时间11月7日01:43–02:31运行，计算日期就是今天；无依据日期判断，原分保留。 |

21条原始质量失败，其中pipeline4条；15条非提交。Name-single的5条追问虽获原质量通过，仍不计作任务完成。工程指标和task_success沿用原定义，不能等同质量。
