# P3 八字调参实验 r12

本轮不满足B，建议暂不冻结，也不运行p3-bazi-final。pipeline提交18/18、质量16/18（88.9%），single提交14/18、质量10/14（71.4%）；36/36完整评分。P1四条满足，但事业#2的“配合松动”被当成“有配合”而误拒，两稿后keywords降级并失答；大运#2把2026说成2023—2033段的“中段偏后”，还有投资#3按流月时段建议资金分批的漏拦。

## 原始结果

| 指标 | single | pipeline |
| --- | ---: | ---: |
| 尝试 | 18 | 18 |
| 提交回答 | 14/18 | 18/18 |
| 原始工程检查全部通过 | 6/18 | 18/18 |
| 完整四维评分 | 18/18 | 18/18 |
| 已提交原始质量通过 | 10/14，另 0 条未评分 | 16/18，另 0 条未评分 |
| 修复 / 降级 | 0 / 0 | 6 / 2 |
| 最多运行模型调用 | 11 | 2 |
| 运行模型调用总数 | 113 | 24 |
| 运行输入 / 输出 token | 792,665 / 44,820 | 128,901 / 17,430 |
| 延迟 P50 / P95（秒） | 31.8 / 66.3 | 14.5 / 26.0 |
| 费用 | 未知 | 未知 |

6题各重复3次，不是18个独立样本。运行延迟和运行token不含rubric评委；pricing.yaml没有模型费率，费用未知。

## 评分与验收

原评分全部保留。single评委请求19次，投资#3在运行器既有解析重试流程中用了第2次请求；pipeline18次，无解析重试。没有事后补评或重跑失败样本。两组运行/评委请求与返回模型均为deepseek-v4.1-flash，评委thinking=disabled、未设reasoning_effort、max_tokens=8192。配对描述：pipeline胜7、single胜1、平10；6题各重复3次，不能当18个独立样本或统计优越性证明。

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

原编造失败表完整：single叙述类3/14（21.4%）、pipeline叙述类0/18；原评分归因事实类均0。但大运#2存在可核验的时间位置错误（原time_consistent已经判false），所以不能据原编造计数0宣称事实错误为0。误拒造成的事业#2降级与已知漏拦足以阻塞B。pipeline降级2/18（11.1%），高于≤10%的监控参考值；质量率比较满足P1，仍不能覆盖B的其他条件。

## 修复及成稿复核

pipeline原质量失败2份：大运#2 time_consistent=false；事业#2 direct_answer=false、supported_conclusion=false。两组工程检查全部通过分别为single6/18、pipeline18/18；single首次无错误8/18属于另一指标，不与工程检查混算。pipeline无工具错误、步数或预算失败，最多2次运行模型调用。single海外三次ask_user、大运#2 retry_limit；已提交质量失败为事业#1、文字出生#2/#3、投资#2。single海外#2虽原quality=true，因未提交不计入10/14。

大运三份均正确写虚岁6岁、当前第4步己未与下一步庚申；#2/#3明确前一步第3步戊午，未复现r11将首步误作相邻前步的错误。18份最终稿未发现反向排运断言；没有实际相邻大运/虚岁错误的修复事件，不能据此证明所有修复路径已被实时覆盖。12条时机题计算范围与时区检查通过，海外各一次澄清、文字出生均零追问。成稿自动检查为空仍漏掉大运位置错误和投资分批建议。两份关键词稿均可从原事实离线复现，整句结束、无可显示事实遗漏或配对关键词错配。

## 证据与限制

运行和评分模型相同；--judge pro是配置角色名。编造分类和成稿检查由Codex离线完成，未经过独立人工校准；原始评分保留，未对缺失评分补评。

- [execution.md](execution.md)：命令、版本、配置恢复和哈希。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)：分类和理由。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：全部回答及原始评分。
- [investment-review.md](investment-review.md)、[temporal-manual-review.md](temporal-manual-review.md)：投资与正文时间逐份复核。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：修复及原句。
- [integrity.json](integrity.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)：来源和完整性。

本轮仅运行调参实验及离线后处理，没有修改被测代码、剔除失败、冻结或运行最终验收集。
