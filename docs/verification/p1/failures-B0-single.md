# 失败归因

## 指标

| 指标 | B0-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 38/60 |
| 一次做对（无工具错误） | 21/60 |
| 质量通过 | 31/60 |
| 任务完成且质量通过 | 26/60 |
| 原严格综合（v1 口径） | 10/60 |
| 每题工具错误 | 2.0 |
| 每题模型调用 | 6.6 |
| 中位 / P95 耗时（秒） | 21.4 / 88.7 |
| 每题输入 / 输出 token | 85743 / 5144 |
| 前缀缓存命中率 | 88.2% |
| 每题估算成本（USD；仅被测运行，不含评委） | 0.004832 |

## B0-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 57 | 17 | 10 |
| E 事实与计算不符 | 23 | 14 | 7 |
| A 参数不是合法JSON | 21 | 17 | 6 |
| D ref_id不属于本次计算 | 8 | 6 | 2 |
| B 参数不符合schema | 2 | 2 | 1 |
| F 流程跳步/依赖缺失 | 2 | 1 | 0 |
| I 表达策略 | 1 | 1 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 1 |
| Z 其他：节气当天时辰未知请先追问，不能擅自确认候选 | 1 | 1 | 1 |
| Z 其他：行运星、本命星与相位须匹配同一计算事件 | 1 | 1 | 1 |
| Z 其他：闰月开关须由用户确认，不能猜测 | 1 | 1 | 0 |

最终未完成的原因：

- 达到步数或预算上限：14 题
- 用普通文本代替 ask_user：2 题
- 结局为 ask_user，未通过：expected_tools：2 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、no_recalculation、response_saved：1 题
- 结局为 submit_reading，未通过：expected_status、expected_tools：1 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：1 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题

质量维度失败次数：

- direct_answer：20
- supported_conclusion：18
- no_fabricated_facts：3
- time_consistent：3

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：11
- Expecting ':' delimiter：10
