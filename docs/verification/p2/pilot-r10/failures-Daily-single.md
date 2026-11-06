# 失败归因

## 指标

| 指标 | Daily-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4.1-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 8/18 |
| 已提交回答 | 16/18 |
| 评委已评分 | 18/18 |
| 评委未评分 | 0/18 |
| 无工具错误（P1 口径，不要求任务完成） | 5/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 4/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 8/18 |
| 已提交回答的质量通过率 | 8/16 |
| 任务完成且质量通过 | 5/18 |
| 原严格综合（v1 口径） | 2/18 |
| 每题工具错误 | 1.1 |
| 每题模型调用 | 4.6 |
| 中位 / P95 耗时（秒） | 31.2 / 54.3 |
| 每题输入 / 输出 token | 33912 / 2872 |
| 前缀缓存命中率 | 62.8% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Daily-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| E 事实与计算不符 | 13 | 8 | 6 |
| B 参数不符合schema | 5 | 5 | 3 |
| A 参数不是合法JSON | 1 | 1 | 1 |
| C 资料来源/地点未确认就计算 | 1 | 1 | 1 |

最终未完成的原因：

- 结局为 submit_reading，未通过：systems：7 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：2 题
- 结局为 submit_reading，未通过：expected_tools、systems：1 题

质量维度失败次数：

- supported_conclusion：8
- no_fabricated_facts：6
- time_consistent：5
- direct_answer：2

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：1
