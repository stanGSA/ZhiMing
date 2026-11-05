# r8 质量失败、未评分与修复归因

本轮108条运行完成，其中107条有完整四维评分：90条质量通过、17条明确不通过、1条未评分。90条含姓名 single 的3条澄清回复，不等于90条已提交解读；96条已提交回答中87条质量通过、8条不通过、1条未评分。以下覆盖全部17条不通过及1条未评分，也覆盖10次 pipeline 修复、2次降级。原稿、回答与评委理由见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[pipeline-problems-raw.md](pipeline-problems-raw.md)。所有分数、失败样本和未评分状态保留，复核不追加模型请求。

## 1. single 未完成与质量失败

| 组／回答 | 原始失败维度／状态 | 归因 |
| --- | --- | --- |
| Dream-single / dream_teeth_falling#1 | direct、supported；retry_limit | 重复处理错误后停止，最终只有未完成说明，没有解梦结论 |
| Dream-single / dream_flood_and_snake#1、dream_flood_and_snake#2 | direct、supported；retry_limit，两条 | 同上；水蛇床命中不能替代已引用释义和最终作答 |
| Dream-single / dream_lost_in_mall#2 | direct、supported；retry_limit | 同上；命中商场、迷路后仍未完成解读 |
| Dream-single / dream_hospital_health#2 | direct、supported；retry_limit | 同上；没有给出健康疑问或检查问题的有效回应 |
| Name-single / name_compound_surname#1 | direct、supported；retry_limit | 已计算五格，但只留下处理失败说明 |
| Name-single / name_three_character#1 | direct、supported；retry_limit | 已算三才，最终未作解读、引用为空 |
| Name-single / name_compare_two#3 | direct、supported；retry_limit | 未给出姓名比较结论 |
| Name-single / name_career_grid#3 | direct、supported；retry_limit | 未回答事业及关键格位问题 |
| Name-single / name_compound_surname#2 | no_fabricated | 叙述类指控成立；另有木生水方向错误被原评委漏掉，单列事实复核 |
| Daily-single / daily_lucky_color#2 | time | 原评委承认UTC换算后属于上海11月5日，又怀疑归属，理由自相矛盾。但正文确有“傍晚之后（约23点前一段）气氛转向正官”，实际正官段23:00才开始；整条不能归为纯评委误判 |
| Daily-single / daily_tomorrow_work#3 | time、supported | 原文日界23点基本正确，但把00–23点整体称“白天”，并从仅一小时七杀段泛化晚间体验；保留原评委对边界表述及结论强度的批评 |
| Daily-single / daily_today_family#3 | time | 原评委称2026-11-05“不是今天”；实验就在该日上海运行，属日期上下文误判。保留原分，不把它擅自改成通过 |
| Daily-single / daily_unknown_birth_time#3 | supported、no_fabricated | 由象征推出具体会议、家庭行为等叙述，并从五行简单计数推个性；叙述和支持不足 |

Dream-single共5条 retry_limit，13条提交；其工具校验错误涉及意象闭集、原文绑定与预兆表达，不把所有工具错误一概认定为程序误拒。Name-single另有2条 ask_user（`name_ambiguous_form#1`、`name_without_lead_in#1`）及1条 text（`name_without_lead_in#2`）：三条原评委质量通过，但没有提交分析，仍属实验任务未完成。请求繁简体澄清与额外追问出生信息并非都同等必要，不能因评委通过就宣称没有过度追问。各组工具错误类别见 `failures-*-single.md`。

## 2. Daily-pipeline 的3条失败与1条未评分

| 回答 | 原始结果 | 复核 |
| --- | --- | --- |
| daily_unknown_birth_time#1 | time=false、supported=false | 评委把2026-11-05视作未来日期，与执行日不符；另对未经审核象征能否综合成“平稳”提出结论强度异议。日期批评可定位为评委上下文错误，支持维度仍单独保留争议，不能整条补分 |
| daily_investment_risk#2 | direct=false、supported=false | 否定“稳赚”的初稿与修复稿均被误拒，最终 safety 模板不作解读；评委就最终文本判未正面作答有依据，上游可定位缺陷是降级诱因，不以模板安全性抵消失答 |
| daily_today_family#3 | no_fabricated=false | 具体家人行为、心理及互动写成现实状态；归叙述类，见分类记录 |
| daily_unknown_birth_time#3 | quality_pass=null；scored=false | `ValueError`，评委 `parse_attempts=2`、`review_request_attempts=2`；产品回答已提交且工程检查通过，缺的是评委有效评分。保留未知，不判产品内容失败，不补跑、不手动评分 |

未知时辰题中未评分样本不妨碍完成对记录的归因，但它使评分及编造统计不完整。每日 pipeline 的14/18是“已确认通过／全部提交”；14/17只是已评分子集的描述，不能用它消除缺失。若未知条最终通过，理论上限为15/18，本轮不作该假设。

## 3. 全部 pipeline 修复与降级

| 体系／回答 | 修复／降级 | 原稿问题与处理 |
| --- | --- | --- |
| Dream / dream_teeth_falling#1 | 1／无 | “牙齿是一颗一颗掉下来的”复述未绑定掉牙，已定位归一化误拒 |
| Dream / dream_chased_to_exam#1 | 1／keywords | 首稿考场等未收录意象，修复稿又写“逃跑”；维持既有受控范围，最终关键词模板质量通过 |
| Dream / dream_flood_and_snake#1、dream_flood_and_snake#2 | 各1／无 | 从“不敢下去”等状态推出心理解释，当前闭集不接受，未临时扩大范围 |
| Dream / dream_lost_in_mall#1、dream_lost_in_mall#3 | 各1／无 | “到处走却找不到出口”“到处找出口却找不到”未纳入已有受控构式；记录表达成本，不等同于模型编造 |
| Dream / dream_chased_to_exam#3 | 1／无 | 再次解读未收录考场，修复后通过 |
| Name / 全部 | 0／0 | 本轮未观察到修复、降级或最终质量失败 |
| Daily / daily_today_general#2 | 1／无 | “不是事情必然顺利的保证”被当确定性，误拒后修复通过 |
| Daily / daily_investment_risk#2 | 1／safety | 两种带状语否定“稳赚”均误拒；最终模板质量失败，详见上表 |
| Daily / daily_lucky_color#3 | 1／无 | “别把配合当成必然有利”命中确定性；另有未作为首个报错显示的“直接当成稳赚”命中，修复后通过 |

共12份拒绝稿（解梦8、每日4），每稿可含多个问题；问题次数、修复次数、降级次数不能互相替换。10次修复＝解梦7＋每日3；2次降级＝keywords 1＋safety 1。拒绝稿及最小对照均离线回放，见 [validation-findings.md](validation-findings.md)。三次解梦医疗题均最终提交、0修复、无降级；每日投资只有第2次修复降级，第1／3次直接完成。不能仅凭部分原句回放成功就宣布整个否定规则已无缺陷。

## 4. 评分局限与事实核对

运行与 pro 配置评委均为 `deepseek-v4.1-flash`，不是独立模型评审；分类由助手完成，不是独立人工校准。时区事实、日界分段、姓名相生方向以及执行时间见 [fact-review.json](fact-review.json)。每日 single 幸运色题还将本命年柱关系描述成“流年”关系，属于来源层次混同；不把此漏判塞入原始编造计数。

三个 pipeline 仍满足提交率100%、最多模型调用≤3、无步数／预算失败。六组 trace 没有 model_error 或 limit_reached；这不代表没有工具校验错误。评委共有3条发生解析重试，其中1条最终未评分。完整性及 B 门槛见 [integrity.json](integrity.json)：未评分与可定位误拒均阻止冻结，不能运行 p2-final。
