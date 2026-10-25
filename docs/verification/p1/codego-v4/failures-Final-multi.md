# 失败归因

## 指标

| 指标 | Final-multi |
| --- | --- |
| 模式 / 模型 | multi / deepseek-v4-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 33/60 |
| 一次做对（无工具错误） | 19/60 |
| 质量通过 | 28/60 |
| 任务完成且质量通过 | 21/60 |
| 原严格综合（v1 口径） | 8/60 |
| 每题工具错误 | 2.5 |
| 每题模型调用 | 9.2 |
| 中位 / P95 耗时（秒） | 106.6 / 231.9 |
| 每题输入 / 输出 token | 67759 / 19144 |
| 前缀缓存命中率 | 3.7% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Final-multi：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 85 | 34 | 15 |
| E 事实与计算不符 | 18 | 15 | 6 |
| Z 其他：没有属于当前用户的占卜记录 | 16 | 10 | 9 |
| B 参数不符合schema | 8 | 7 | 2 |
| D ref_id不属于本次计算 | 3 | 2 | 1 |
| I 表达策略 | 3 | 2 | 0 |
| Z 其他：国家限制必须由用户明确提供，不能自行消歧 | 3 | 3 | 0 |
| Z 其他：子问题指定了时间范围，须计算本体系行运或流期，不能只用原局 | 3 | 2 | 1 |
| Z 其他：时间范围问题需要相应行运或流期计算，不能只用原局 | 3 | 2 | 1 |
| Z 其他：本步已在咨询该专家，请等待其报告 | 2 | 2 | 2 |
| Z 其他：同一reading各体系必须使用相同时间范围；不同区间请开始 | 1 | 1 | 0 |
| Z 其他：省州限制须有用户确认 | 1 | 1 | 1 |
| Z 其他：重复本地时间的fold必须由用户明确确认 | 1 | 1 | 1 |

最终未完成的原因：

- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：9 题
- 结局为 output_truncated，未通过：expected_status、expected_tools、saved、systems：8 题
- 达到步数或预算上限：4 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、response_saved：2 题
- 用普通文本代替 ask_user：2 题
- 结局为 submit_reading，未通过：expected_tools：1 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题

质量维度失败次数：

- supported_conclusion：22
- direct_answer：18
- time_consistent：13
- no_fabricated_facts：3

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- 没有找到
