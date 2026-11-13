# 失败归因

## 指标

| 指标 | Bazi-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4.1-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 12/18 |
| 已提交回答 | 12/18 |
| 评委已评分 | 18/18 |
| 评委未评分 | 0/18 |
| 无工具错误（P1 口径，不要求任务完成） | 5/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 5/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 9/18 |
| 已提交回答的质量通过率 | 9/12 |
| 任务完成且质量通过 | 9/18 |
| 原严格综合（v1 口径） | 4/18 |
| 每题工具错误 | 1.3 |
| 每题模型调用 | 7.2 |
| 中位 / P95 耗时（秒） | 34.0 / 52.6 |
| 每题输入 / 输出 token | 45247 / 2738 |
| 前缀缓存命中率 | 72.1% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Bazi-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| E 事实与计算不符 | 6 | 6 | 4 |
| I 表达策略 | 6 | 2 | 2 |
| A 参数不是合法JSON | 2 | 2 | 0 |
| B 参数不符合schema | 2 | 2 | 0 |
| C 资料来源/地点未确认就计算 | 2 | 2 | 0 |
| G 释义查询未命中 | 2 | 1 | 0 |
| Z 其他：时间范围问题需要相应行运或流期计算，不能只用原局 | 2 | 2 | 0 |
| Z 其他：节气当天时辰未知请先追问，不能擅自确认候选 | 1 | 1 | 1 |

最终未完成的原因：

- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：4 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：1 题

质量维度失败次数：

- supported_conclusion：7
- direct_answer：6
- time_consistent：5
- no_fabricated_facts：3

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：2
