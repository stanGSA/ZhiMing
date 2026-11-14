# 失败归因

## 指标

| 指标 | Bazi-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 14/18 |
| 已提交回答 | 14/18 |
| 评委已评分 | 18/18 |
| 评委未评分 | 0/18 |
| 无工具错误（P1 口径，不要求任务完成） | 8/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 7/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 12/18 |
| 已提交回答的质量通过率 | 11/14 |
| 任务完成且质量通过 | 11/18 |
| 原严格综合（v1 口径） | 6/18 |
| 每题工具错误 | 1.1 |
| 每题模型调用 | 6.9 |
| 中位 / P95 耗时（秒） | 13.8 / 30.3 |
| 每题输入 / 输出 token | 43330 / 2544 |
| 前缀缓存命中率 | 76.9% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Bazi-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| A 参数不是合法JSON | 5 | 5 | 2 |
| G 释义查询未命中 | 5 | 2 | 0 |
| E 事实与计算不符 | 4 | 4 | 2 |
| I 表达策略 | 4 | 2 | 1 |
| B 参数不符合schema | 1 | 1 | 0 |
| C 资料来源/地点未确认就计算 | 1 | 1 | 0 |

最终未完成的原因：

- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：3 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：1 题

质量维度失败次数：

- supported_conclusion：5
- no_fabricated_facts：4
- direct_answer：3
- time_consistent：2

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：2
- Expecting value：2
- Expecting ':' delimiter：1
