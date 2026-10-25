# 失败归因

## 指标

| 指标 | B0-multi |
| --- | --- |
| 模式 / 模型 | multi / deepseek-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 10/60 |
| 一次做对（无工具错误） | 45/60 |
| 质量通过 | 8/60 |
| 任务完成且质量通过 | 7/60 |
| 原严格综合（v1 口径） | 2/60 |
| 每题工具错误 | 1.6 |
| 每题模型调用 | 3.9 |
| 中位 / P95 耗时（秒） | 0.5 / 83.8 |
| 每题输入 / 输出 token | 25726 / 2074 |
| 前缀缓存命中率 | 82.7% |
| 每题估算成本（USD；仅被测运行，不含评委） | 0.001977 |

## B0-multi：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 53 | 10 | 7 |
| E 事实与计算不符 | 12 | 6 | 5 |
| D ref_id不属于本次计算 | 6 | 5 | 2 |
| F 流程跳步/依赖缺失 | 6 | 2 | 2 |
| A 参数不是合法JSON | 5 | 4 | 2 |
| B 参数不符合schema | 5 | 4 | 3 |
| I 表达策略 | 4 | 3 | 0 |
| G 释义查询未命中 | 3 | 2 | 2 |
| H 审校工具协议 | 2 | 2 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 1 |

最终未完成的原因：

- 模型服务错误：42 题
- 达到步数或预算上限：3 题
- 结局为 submit_reading，未通过：systems：2 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：2 题
- 用普通文本代替 ask_user：1 题

质量维度失败次数：

- direct_answer：7
- supported_conclusion：4
- no_fabricated_facts：1

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：2
- Expecting ':' delimiter：2
- Expecting value：1
