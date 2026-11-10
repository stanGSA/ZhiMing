# 失败归因

## 指标

| 指标 | Bazi-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4.1-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 13/18 |
| 已提交回答 | 13/18 |
| 评委已评分 | 18/18 |
| 评委未评分 | 0/18 |
| 无工具错误（P1 口径，不要求任务完成） | 10/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 9/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 6/18 |
| 已提交回答的质量通过率 | 6/13 |
| 任务完成且质量通过 | 6/18 |
| 原严格综合（v1 口径） | 4/18 |
| 每题工具错误 | 1.1 |
| 每题模型调用 | 7.0 |
| 中位 / P95 耗时（秒） | 36.8 / 69.9 |
| 每题输入 / 输出 token | 44094 / 2781 |
| 前缀缓存命中率 | 68.7% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Bazi-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| I 表达策略 | 6 | 2 | 2 |
| E 事实与计算不符 | 3 | 3 | 2 |
| G 释义查询未命中 | 3 | 1 | 0 |
| B 参数不符合schema | 2 | 2 | 0 |
| Z 其他：节气当天时辰未知请先追问，不能擅自确认候选 | 2 | 1 | 1 |
| C 资料来源/地点未确认就计算 | 1 | 1 | 1 |
| Z 其他：出生时间未知须由用户明确说明；请先追问 | 1 | 1 | 1 |
| Z 其他：时间范围问题需要相应行运或流期计算，不能只用原局 | 1 | 1 | 0 |

最终未完成的原因：

- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：3 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：1 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题

质量维度失败次数：

- supported_conclusion：9
- no_fabricated_facts：5
- direct_answer：5
- time_consistent：1

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- 没有找到
