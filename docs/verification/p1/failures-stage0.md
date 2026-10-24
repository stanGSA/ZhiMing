# 失败归因

## 指标

| 指标 | baseline-single-summary | baseline-multi-after-topup-summary |
| --- | --- | --- |
| 模式 / 模型 | single / deepseek-flash | multi / deepseek-flash |
| 评委规则版本 | v1 | v1 |
| 任务完成（不计 zero_tool_errors） | 16/20 | 11/20 |
| 一次做对（无工具错误） | 7/20 | 3/20 |
| 质量通过 | 9/20 | 9/20 |
| 任务完成且质量通过 | 8/20 | 7/20 |
| 原严格综合（v1 口径） | 2/20 | 2/20 |
| 每题工具错误 | 1.4 | 5.9 |
| 每题模型调用 | 5.1 | 13.8 |
| 中位 / P95 耗时（秒） | 23.6 / 59.6 | 48.0 / 88.4 |
| 每题输入 / 输出 token | 64642 / 5078 | 94438 / 9072 |
| 前缀缓存命中率 | — | 82.2% |

## baseline-single-summary：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| A 参数不是合法JSON | 8 | 8 | 0 |
| D ref_id不属于本次计算 | 8 | 2 | 0 |
| E 事实与计算不符 | 6 | 6 | 0 |
| C 资料来源/地点未确认就计算 | 5 | 2 | 1 |
| F 流程跳步/依赖缺失 | 1 | 1 | 1 |

最终未完成的原因：

- 用普通文本代替 ask_user：2 题
- 结局为 ask_user，未通过：expected_tools：1 题
- 达到步数或预算上限：1 题

质量维度失败次数：

- supported_conclusion：9
- no_fabricated_facts：4
- direct_answer：3
- time_consistent：1

## baseline-multi-after-topup-summary：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 57 | 12 | 6 |
| E 事实与计算不符 | 15 | 6 | 6 |
| A 参数不是合法JSON | 13 | 10 | 5 |
| B 参数不符合schema | 11 | 8 | 6 |
| F 流程跳步/依赖缺失 | 10 | 4 | 3 |
| G 释义查询未命中 | 6 | 4 | 2 |
| D ref_id不属于本次计算 | 4 | 3 | 2 |
| H 审校工具协议 | 1 | 1 | 0 |
| I 表达策略 | 1 | 1 | 1 |

最终未完成的原因：

- 达到步数或预算上限：4 题
- 结局为 submit_reading，未通过：no_model_error：2 题
- 结局为 ask_user，未通过：expected_status、expected_tools、no_model_error、saved、systems：1 题
- 结局为 ask_user，未通过：no_model_error：1 题
- 结局为 submit_reading，未通过：no_model_error、systems：1 题

质量维度失败次数：

- supported_conclusion：11
- direct_answer：7
- no_fabricated_facts：4
- time_consistent：2

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：15
- Expecting ':' delimiter：11
