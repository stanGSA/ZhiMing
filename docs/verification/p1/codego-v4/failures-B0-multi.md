# 失败归因

## 指标

| 指标 | B0-multi |
| --- | --- |
| 模式 / 模型 | multi / deepseek-v4-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 37/60 |
| 一次做对（无工具错误） | 21/60 |
| 质量通过 | 25/60 |
| 任务完成且质量通过 | 25/60 |
| 原严格综合（v1 口径） | 14/60 |
| 每题工具错误 | 1.8 |
| 每题模型调用 | 10.9 |
| 中位 / P95 耗时（秒） | 138.5 / 252.7 |
| 每题输入 / 输出 token | 90888 / 21405 |
| 前缀缓存命中率 | 2.4% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## B0-multi：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 46 | 23 | 13 |
| E 事实与计算不符 | 23 | 16 | 10 |
| B 参数不符合schema | 12 | 12 | 6 |
| G 释义查询未命中 | 8 | 3 | 1 |
| F 流程跳步/依赖缺失 | 6 | 4 | 4 |
| Z 其他：同一reading各体系必须使用相同时间范围；不同区间请开始 | 4 | 2 | 2 |
| I 表达策略 | 3 | 3 | 0 |
| D ref_id不属于本次计算 | 2 | 2 | 1 |
| Z 其他：同一记录内各专家必须使用相同时间范围 | 1 | 1 | 1 |
| Z 其他：时间范围问题需要相应行运或流期计算，不能只用原局 | 1 | 1 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 1 |
| Z 其他：该字段必须是布尔值 | 1 | 1 | 0 |

最终未完成的原因：

- 达到步数或预算上限：11 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：7 题
- 结局为 submit_reading，未通过：systems：3 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、response_saved：1 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题

质量维度失败次数：

- supported_conclusion：27
- direct_answer：20
- time_consistent：10
- no_fabricated_facts：8

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- 没有找到
