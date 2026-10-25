# 失败归因

## 指标

| 指标 | B0-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 34/60 |
| 已提交回答 | 26/60 |
| 评委已评分 | 55/60 |
| 评委未评分 | 5/60 |
| 一次做对（无工具错误） | 20/60 |
| 质量通过 | 24/60 |
| 已提交回答的质量通过率 | 10/26 |
| 任务完成且质量通过 | 17/60 |
| 原严格综合（v1 口径） | 9/60 |
| 每题工具错误 | 3.0 |
| 每题模型调用 | 6.6 |
| 中位 / P95 耗时（秒） | 73.9 / 163.7 |
| 每题输入 / 输出 token | 83489 / 4963 |
| 前缀缓存命中率 | 64.4% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## B0-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| C 资料来源/地点未确认就计算 | 71 | 24 | 16 |
| C 画像写入越界（地理/历法口径） | 33 | 12 | 11 |
| A 参数不是合法JSON | 21 | 16 | 6 |
| B 参数不符合schema | 18 | 15 | 7 |
| E 事实与计算不符 | 16 | 8 | 4 |
| F 流程跳步/依赖缺失 | 8 | 8 | 8 |
| D ref_id不属于本次计算 | 6 | 5 | 1 |
| Z 其他：节气当天时辰未知请先追问，不能擅自确认候选 | 3 | 1 | 1 |
| I 表达策略 | 2 | 2 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 1 |
| Z 其他：行运星、本命星与相位须匹配同一计算事件 | 1 | 1 | 1 |

最终未完成的原因：

- 达到步数或预算上限：15 题
- 用普通文本代替 ask_user：6 题
- 结局为 ask_user，未通过：expected_tools：2 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：2 题
- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems、response_saved：1 题

质量维度失败次数：

- supported_conclusion：26
- direct_answer：20
- no_fabricated_facts：12
- time_consistent：7

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- Expecting ',' delimiter：13
- Expecting value：7
- Extra data：1
