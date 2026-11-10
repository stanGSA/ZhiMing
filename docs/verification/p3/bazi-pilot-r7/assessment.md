# P3 八字调参实验 r7

**实验完成；P1 四条满足，B 不满足，不冻结。** pipeline 提交18/18、工程检查18/18，最多2次模型调用，原始已提交质量15/18（83.3%），single为9/12（75.0%）。下个月事业与海外共6次全部0修复、0降级；唯一标题问题在文字出生#1，一次修复成功。B阻断来自投资#2保守表述误拒造成关键词降级，以及大运#2正财/偏财归纳错配被放过。

## 原始结果

| 指标 | single | pipeline |
| --- | ---: | ---: |
| 尝试 | 18 | 18 |
| 提交回答 | 12/18 | 18/18 |
| 全部原始工程检查通过 | 8/18 | 18/18 |
| 全部样本评分覆盖 | 18/18 | 18/18 |
| 已提交回答评分覆盖 | 12/12 | 18/18 |
| 已提交回答原始质量通过 | 9/12（75.0%） | 15/18（83.3%） |
| 修复 / 降级 | 0 / 0 | 5 / 1 |
| 最多运行模型调用 | 13 | 2 |
| 运行模型调用总数 | 120 | 23 |
| 运行输入 / 输出 token | 752,513 / 32,541 | 118,738 / 15,610 |
| 延迟 P50 / P95，秒 | 44.5 / 473.2 | 9.2 / 20.3 |
| 费用 | 未知 | 未知 |

延迟不含 rubric 评分和准备工作；token 不含 rubric 评委。pricing.yaml 无模型费率，费用未知，不能记为零。6 题各重复 3 次，不等于 18 个独立样本。

## 评分完整性与验收

36/36条均有原始四维评分，36次评委请求各1次，无补评、无剔除。single有4条ask_user、2条model_error，均不进入已提交质量分母。两次错误均为APITimeoutError，single长尾延迟不能直接归因于代码效率。海外#3评委JSON尾逗号按既有容忍解析，原文与解析标记保留。所有运行和评委请求/返回均为deepseek-v4.1-flash，同模型评分且没有独立校准。

| B 条件 | 本轮 |
| --- | --- |
| pipeline 提交 18/18、步数预算失败 0、调用 ≤3 | True |
| 两组评分及编造分类完整 | True（分类方法见下文） |
| pipeline 事实类评分失败为 0 | True |
| 未发现造成降级、失答或质量失败的可定位误拒 | False |
| 无已知放过 | False |
| 已提交质量 ≥ 同批 single（调参报告项） | True |

原评分编造分类已完整：pipeline事实类0、叙述类2/18（11.1%），single事实类0、叙述类3/12（25.0%）。满足叙述类“不高于single”，未达争取≤10%。这些计数按原no_fabricated_facts理由分类，并非全面事实正确率；离线发现的正财/偏财错配另列已知放过。投资#2首稿含“小额验证、设好止损线”等真实操作建议，不能把首稿全称误拒；但修复稿仅剩的交易报错涉及4句保守/否定/核实表述，全稿重放只报交易问题，在离线副本将这4句替换为中性核实提醒后问题为空。原trace显示拒绝后直接keywords降级，最终评分通过并不能抵消误拒造成的降级。B不满足，不冻结、不跑最终验收集。

## 质量失败与修复归因

pipeline原始质量失败3条：下个月事业#1 time_consistent=false，理由承认范围和节令边界正确，但因正文未明确年份给false，存在轻微年份歧义及理由与判断张力；大运#2 no_fabricated_facts=false针对用户当前场景叙述，原文带主题/倾向，解释有余地；文字出生#2 supported_conclusion=false和no_fabricated_facts=false，涉及计数推出性格、未确认关系场景，不是计算干支数值写错。原分全部保留。5次修复分别为大运#1重复、文字出生#1标题、投资#1交易、大运#2重复、投资#2交易。5次均有定位引句；投资#2按现有每类最多2句只引首稿前两处，并非没有引句。

## 时间、降级与历史对照

4类时机题计算范围/时区核对通过，海外每次澄清1次且固定UTC+8出生排盘，文字出生每次零追问；仅证明流程与计算范围。最终标题规则重放无findings，下个月/海外6次无修复；文字出生#1标题7月11日至8月10日与乙未7月7日至8月7日不合，正确触发修复并改为实际日期。9句r6保守话术放行、6句PR66评审守卫拦截、2处r6标题放过被拦截，17个选定离线探针通过，但新保守措辞仍误拒，不能据此宣称规则完整。唯一keywords降级的原事实可重现3层正文，长度1196/1196/192，整句结束、配对关键词无错配、选中可显示事实无遗漏；这是结构检查，原评委本次质量通过。

与 r6 的描述性对照：pipeline 质量通过从 11/18 到 15/18，修复从 7 到 5，降级从 1 到 1，最大调用从 2 到 2。题集、澄清、rubric 和配置与 r6 一致，代码已变，小样本不作显著性或能力提升结论。

## 证据与限制

运行与评分请求、返回的模型标识见 integrity.json；本轮使用同一 DeepSeek 模型运行与评分，`--judge pro` 是配置角色名。没有独立评委或人工校准。编造类别由 Codex 对原评分失败离线归因，工具显示的“人工判定”仅为既有接口措辞，不代表独立人工复核；原始评分未更改。

- [execution.md](execution.md)：命令、提交、指纹、退出码及配置恢复。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：36 条回答和原始评委理由。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：每次修复及原句。
- [fabrication-attribution.md](fabrication-attribution.md)、[fabrication-counts.md](fabrication-counts.md)：分类证据及计数。
- [title-repair-focus.md](title-repair-focus.md)：下个月、海外和唯一标题修复。
- [manual-known-escapes.json](manual-known-escapes.json)、[r7-observations.md](r7-observations.md)：正财/偏财归纳错配与呈现残留。
- [supplemental-checks.json](supplemental-checks.json)：实际草稿、误拒对照及回归探针。
- [acceptance.json](acceptance.json)、[integrity.json](integrity.json)、[evidence-manifest.json](evidence-manifest.json)：机器可读判断与哈希。

本轮仅执行调参实验及离线后处理，没有补评、重跑缺口、剔除失败、修改被测实现、冻结或运行最终验收集。
