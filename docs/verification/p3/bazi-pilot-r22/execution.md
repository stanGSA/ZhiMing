# r22 执行记录：原有 deepseek-flash 配置

已完成6个合成题目、每题3次：Single 18份、Pipeline 18份，36份全部获得有效原始评分。使用原有工作区 config.yaml 和原项目 D:\知命\.env 中的凭据，官方接口 https://api.deepseek.com，运行和评委均为 deepseek-flash；没有读取或使用 C:\Users\Stan\Desktop\key.txt。

评委别名pro，thinking=disabled，max_tokens=8192。预检三项通过（见 preflight.md、service-probe.json）。请求与返回模型字段一致，但只作为服务元数据；reasoning_tokens未提供，不能当成实测零。当前官方费率未核实，pricing.yaml保留空费率，费用未知。

运行时间：北京时间2026-11-17 19:58:05—20:08:38（UTC 11:58:05.945776—12:08:38.989415）。启动器退出0，campaign状态complete。两组live子任务退出1表示存在未通过样本，未将它改记为全通过。

命令（在工作区、已注入原项目凭据的子进程内执行）：

```powershell
python -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r22 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r22
```

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 总数 / 有效评分 | 18 / 18 | 18 / 18 |
| 提交 | 14 | 18 |
| 已提交质量通过 | 11/14（78.6%） | 16/18（88.9%） |
| 严格综合通过（全部18份为分母） | 4/18 | 16/18 |
| 工程检查通过 | 5/18 | 17/18 |
| 运行模型调用 / 每题最多 | 116 / 11 | 25 / 2 |
| 修复 / 降级 | 0 / 0 | 7 / 0 |
| 评委行数 / 请求尝试 | 18 / 18 | 18 / 18 |
| 运行耗时中位数 / P95（秒） | 16.1905 / 38.736 | 7.535 / 12.801 |
| 评委耗时中位数（秒） | 3.243 | 3.000 |
| 运行输入token总数 | 831372 | 141241 |
| 运行输出token总数 | 53996 | 18455 |
| 评委输入token总数 | 185484 | 243878 |
| 评委输出token总数 | 7001 | 5978 |
| 每行运行输入中位数 | 41207 | 5196.5 |
| 每行评委输入中位数 | 8500 | 11599 |
| 每行合计输入中位数 | 49257.5 | 15880.5 |
| 每行运行输出÷调用数的中位数 | 417.842857 | 713 |
| 每次运行响应输出中位数 | 140 | 747 |
| 每行评委输出中位数 | 373.5 | 329.5 |

每行比值的中位数与逐响应中位数是不同统计量，未混用。配对严格结果为Pipeline胜7、Single胜2、平9；仅作本批描述。

Single状态为14次submit_reading、3次ask_user（海外三次）、1次retry_limit（大运#1）。大运#1一次JSON参数错误后，正文免责声明重复三次触发重试上限。Pipeline全部提交；投资#2曾submit_reading validation_failed，修复后提交，故工程检查仍为失败。原始失败未剔除或替换。

Single run_id：20261117T115815-e9fee030；Pipeline run_id：20261117T120512-b0ccbfec。

被测HEAD为 f15353ce100f8acc1af1ca78756973bb16a313ca。两组184项源码哈希相同，指纹为 9ad34f3678d943d9a0206887ba9a029c73a63d03619dc85e293aaa8da3331586。除个人config外均与被测commit匹配；该commit相对PR #83合并后的代码仅增加r21报告。配置SHA256为 a802e8c261869acfea4994f5953fc8ebd5361db87fb8a7d5aa07b26523dedbc3，运行前后逐字节相同。运行、评委及预算字段与r20配置语义相同，其他历史知识库配置及注释存在差别。

原始live.json和36份trace位于 reports/p3-bazi-r22，哈希见raw-manifest.json、trace-manifest.json。发布目录保存全部36份最终回答、结构化输出与计算事实（supplement-answers.json / .md）、原始失败、7份被拒首稿及7组修复引句。大运#2的成功compose原始草稿未单独归档，漏检证据使用最终structured、原始评分与计算事实。evidence-manifest.json覆盖除自身外的Git暂存文件字节。未补跑、重评、修改答案或被测实现，未执行最终验收集。
