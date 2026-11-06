# 失败归因

## 指标

| 指标 | Daily-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4.1-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 10/18 |
| 已提交回答 | 15/18 |
| 评委已评分 | 18/18 |
| 评委未评分 | 0/18 |
| 无工具错误（P1 口径，不要求任务完成） | 9/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 6/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 11/18 |
| 已提交回答的质量通过率 | 11/15 |
| 任务完成且质量通过 | 8/18 |
| 原严格综合（v1 口径） | 5/18 |
| 每题工具错误 | 1.6 |
| 每题模型调用 | 4.8 |
| 中位 / P95 耗时（秒） | 27.2 / 63.7 |
| 每题输入 / 输出 token | 37383 / 2663 |
| 前缀缓存命中率 | 71.2% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Daily-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| E 事实与计算不符 | 13 | 6 | 4 |
| C 资料来源/地点未确认就计算 | 7 | 7 | 5 |
| G 释义查询未命中 | 5 | 4 | 2 |
| B 参数不符合schema | 1 | 1 | 0 |
| I 表达策略 | 1 | 1 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 0 |

最终未完成的原因：

- 结局为 submit_reading，未通过：systems：4 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems、safety_flag：2 题
- 结局为 submit_reading，未通过：expected_tools、systems：1 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：1 题

质量维度失败次数：

- no_fabricated_facts：5
- time_consistent：4
- supported_conclusion：4
- direct_answer：3

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- 没有找到
