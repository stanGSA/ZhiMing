# P3 八字调参实验 r8

**实验完成；P1 四条满足，B 不满足，不冻结。** pipeline提交18/18，工程检查18/18，原始已提交质量15/18（83.3%）；single提交13/18，已提交质量7/13（53.8%）。pipeline 3次修复均为真实重复标签，0降级、最多2次调用；投资#1分批投入建议、海外#3下旬错写及投资#2春节/立春混写被放过。

## 原始结果

| 指标 | single | pipeline |
| --- | ---: | ---: |
| 尝试 | 18 | 18 |
| 提交回答 | 13/18 | 18/18 |
| 全部原始工程检查通过 | 5/18 | 18/18 |
| 全部样本评分覆盖 | 18/18 | 18/18 |
| 已提交回答评分覆盖 | 13/13 | 18/18 |
| 已提交回答原始质量通过 | 7/13（53.8%） | 15/18（83.3%） |
| 修复 / 降级 | 0 / 0 | 3 / 0 |
| 最多运行模型调用 | 12 | 2 |
| 运行模型调用总数 | 121 | 21 |
| 运行输入 / 输出 token | 720,922 / 40,727 | 91,797 / 13,146 |
| 延迟 P50 / P95，秒 | 36.4 / 67.3 | 9.7 / 15.7 |
| 费用 | 未知 | 未知 |

延迟不含 rubric 评分和准备工作；token 不含 rubric 评委。pricing.yaml 无模型费率，费用未知，不能记为零。6 题各重复 3 次，不等于 18 个独立样本。

## 评分完整性与验收

36/36条都有完整原始四维评分。single有4条ask_user、1条limit_reached，不进入已提交质量分母。single投资#3内置评分解析重试1次，single共19次、pipeline共18次评委请求，总37次；没有离线补评。首次失败原文在成功重试后未被现有脚本保留，只能确认JSON提取或布尔字段校验的ValueError，不能还原具体错误（scoring-retry.json）。最终理由虽没有维度标签，四维布尔完整。运行及评分均为deepseek-v4.1-flash，同模型且未经独立人工校准。

| B 条件 | 本轮 |
| --- | --- |
| pipeline 提交 18/18、步数预算失败 0、调用 ≤3 | True |
| 两组评分及编造分类完整 | True（分类方法见下文） |
| pipeline 事实类评分失败为 0 | True |
| 未发现造成降级、失答或质量失败的可定位误拒 | True |
| 无已知放过 | False |
| 已提交质量 ≥ 同批 single（调参报告项） | True |

原评分编造分类完整：pipeline事实类0、叙述类3/18（16.7%）；single事实类2/13（15.4%）、叙述类5/13（38.5%），两类可重叠。满足叙述类“不高于single”，未达争取≤10%。事实类0只表示原评委失败归因，不表示无事实错误。离线逐份核对发现3项已知放过，足以阻断B：投资#1省略动词的分批投入推荐、海外#3正文下旬错写、投资#2春节/立春混写。未发现造成降级、失答或质量失败的可定位误拒；本轮没有实际交易检查触发，也不能由此证明交易规则完整。

## 质量失败与修复归因

pipeline质量失败3条：下个月事业#2和文字出生#2仅no_fabricated_facts=false，分别涉及工作/财务场景与相遇方式；投资#3同时supported_conclusion=false及no_fabricated_facts=false，涉及全年重仓风险排序和未知行为。部分理由与rubric允许建议/条件句有解释张力，全部保留原分。3次修复都在大运#1–#3，1/4/1项重复标签，共6项，每类都有原句定位，一次修好且最终质量全部通过。交易修复0、标题修复0、降级0。

## 时间、降级与历史对照

四类时机题的计算范围与时区核对均通过；海外各一次澄清、固定UTC+8出生排盘，文字出生零追问。下个月事业和海外共6次0修复0降级。18份最终稿标题与规则离线重放无findings，但正文仍有下旬/春节时间错配，不能把规则通过等同于语义正确。25个选定离线探针通过（9明确推荐、7克制/核实、4正确局部归纳、5错误归纳），只覆盖给定句式。无实际降级，不能声称本轮再验证了降级结构。

与 r7 的描述性对照：pipeline 质量通过从 15/18 到 15/18，修复从 5 到 3，降级从 1 到 0，最大调用从 2 到 2。题集、澄清、rubric 和配置与 r7 一致，代码已变，小样本不作显著性或能力提升结论。

## 证据与限制

运行与评分请求、返回的模型标识见 integrity.json；本轮使用同一 DeepSeek 模型运行与评分，`--judge pro` 是配置角色名。没有独立评委或人工校准。编造类别由 Codex 对原评分失败离线归因，工具显示的“人工判定”仅为既有接口措辞，不代表独立人工复核；原始评分未更改。

- [execution.md](execution.md)：命令、提交、指纹、退出码及配置恢复。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：36 条回答和原始评委理由。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：每次修复及原句。
- [fabrication-attribution.md](fabrication-attribution.md)、[fabrication-counts.md](fabrication-counts.md)：分类证据及计数。
- [title-repair-focus.md](title-repair-focus.md)：下个月、海外及零标题修复。
- [manual-known-escapes.json](manual-known-escapes.json)、[r8-observations.md](r8-observations.md)：分批投入推荐、正文时间错写及呈现残留。
- [investment-review.md](investment-review.md)：三份投资最终稿逐份复核。
- [scoring-retry.json](scoring-retry.json)、[usage-accounting.json](usage-accounting.json)：评分重试的证据缺口与含/不含评委的token口径。
- [supplemental-checks.json](supplemental-checks.json)：修复定位引句、最终稿重放及回归探针。
- [acceptance.json](acceptance.json)、[integrity.json](integrity.json)、[evidence-manifest.json](evidence-manifest.json)：机器可读判断与哈希。

本轮仅执行调参实验及离线后处理，没有补评、重跑缺口、剔除失败、修改被测实现、冻结或运行最终验收集。
