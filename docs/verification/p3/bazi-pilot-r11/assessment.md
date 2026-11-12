# P3 八字调参实验 r11

本轮不满足 B，暂不冻结，也不运行 p3-bazi-final。pipeline 提交18/18、原始质量16/18，single 提交14/18、质量9/14；36条均有完整评分。阻塞来自投资#1的可定位误拒导致 safety 降级和质量失败，以及大运#3把第4步的前一步写成第1步的已知放过。投资#3亦因交易检查误拒走 keywords 降级，虽原质量通过仍不满足“没有造成降级的可定位误拒”。

## 原始结果

| 指标 | single | pipeline |
| --- | ---: | ---: |
| 尝试 | 18 | 18 |
| 提交回答 | 14/18 | 18/18 |
| 原始工程检查全部通过 | 8/18 | 17/18 |
| 完整四维评分 | 18/18 | 18/18 |
| 已提交原始质量通过 | 9/14，另 0 条未评分 | 16/18，另 0 条未评分 |
| 修复 / 降级 | 0 / 0 | 6 / 2 |
| 最多运行模型调用 | 11 | 2 |
| 运行模型调用总数 | 113 | 24 |
| 运行输入 / 输出 token | 802,772 / 49,456 | 125,337 / 16,190 |
| 延迟 P50 / P95（秒） | 28.8 / 88.8 | 10.0 / 19.6 |
| 费用 | 未知 | 未知 |

6题各重复3次，不是18个独立样本。运行延迟和运行token不含rubric评委；pricing.yaml没有模型费率，费用未知。

## 评分与验收

原评分全部保留；single 18次评委请求、pipeline 21次。pipeline 海外#1、文字出生#1/#3各在既有 judge_answer 的最多2次解析流程中用了第2次请求，最终均评分成功。没有在 campaign 结束后追加评分，最终未评分0。两组运行/评分请求与返回模型都是 deepseek-v4.1-flash，评委 thinking=disabled、reasoning_effort未设置；这不是独立模型评审。配对描述为 pipeline胜7、single胜0、平11，不作统计显著性结论。

| 条件 | 结果 |
| --- | --- |
| all_pipeline_answers_submitted | True |
| no_pipeline_step_or_budget_failures | True |
| max_pipeline_model_calls_le_3 | True |
| submitted_quality_at_least_same_batch_single | True |
| 两组评分、分类完整 | True |
| pipeline事实类失败为0 | False |
| pipeline叙述类占比不高于single | True |
| 未发现造成失败的可定位误拒 | False |
| 无已知放过 | False |
| B全部条件 | False |

原评委失败分类表完整：single叙述类4/14（28.6%），pipeline叙述类1/18（5.6%），原评分事实类均0。但是Codex离线复核明确发现pipeline大运#3的事实性放过，实际不能满足事实错误为0；acceptance.json同时保留“原评委事实类失败0”与“离线发现1条回答有事实错误”的区别。两次降级为2/18（11.1%），超过≤10%的监控参考值，且至少一条原质量失败与误拒降级相连。

## 修复及成稿复核

pipeline两条原质量失败：投资#1 direct_answer=false、supported_conclusion=false（safety答复明言不作解读）；事业#2 no_fabricated_facts=false（解释场景越界/评委误读争议）。工程17/18：投资#1在最终降级提交前记录了一次 submit_reading validation_failed，错误为高风险确定性结论。single工程8/18，三条海外均ask_user，一条投资#1 retry_limit；已提交失败包括事业#1/#2、文字出生#1/#2、性格#3。文字出生#1范围实际漂移到2026-11—2027-02，原time=false有依据。

PR #70顺逆排修正：18份pipeline最终回答中未发现与computed forward相反的排法表述；r10错误原句、两方向掩盖错误、条件规则、单条定义与正确命盘说法5个离线探针结果符合预期。本轮没有实际顺逆排问题命中或修复事件，不能声称已验证该路径的真实修复效果。12条时机题计算范围/时区、海外三次各一次真太阳时澄清、文字出生三次均零追问通过。最终稿自动扫描为空仍漏掉大运#3前后步关系错误；该已知放过已单列。一次keywords稿由原事实复现，3层1180/1196/192字，整句结束，无配对关键词错配或可显示事实遗漏；只能说明这些结构检查。

## 证据与限制

运行和评分模型相同；--judge pro是配置角色名。编造分类和成稿检查由Codex离线完成，未经过独立人工校准；原始评分保留，未对缺失评分补评。

- [execution.md](execution.md)：命令、版本、配置恢复和哈希。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)：分类和理由。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：全部回答及原始评分。
- [investment-review.md](investment-review.md)、[temporal-manual-review.md](temporal-manual-review.md)：投资与正文时间逐份复核。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：修复及原句。
- [integrity.json](integrity.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)：来源和完整性。

本轮仅运行调参实验及离线后处理，没有修改被测代码、剔除失败、冻结或运行最终验收集。
