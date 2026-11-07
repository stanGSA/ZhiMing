# 失败归因

## 指标

| 指标 | Astro-single |
| --- | --- |
| 模式 / 模型 | single / deepseek-v4.1-flash |
| 评委规则版本 | v2-2026-10-24 |
| 任务完成（不计 zero_tool_errors） | 11/18 |
| 已提交回答 | 11/18 |
| 评委已评分 | 17/18 |
| 评委未评分 | 1/18 |
| 无工具错误（P1 口径，不要求任务完成） | 10/18 |
| 任务完成且一次做对（无工具错误、无修复、无降级） | 6/18 |
| 流水线修复过 | 0/18 |
| 流水线降级 | 0/18 |
| 意象无命中（no_symbol） | 0/18（0.0%） |
| 流水线降级（排除 no_symbol，分母仍为全部请求） | 0/18（0.0%） |
| 质量通过 | 8/18 |
| 已提交回答的质量通过率 | 7/11 |
| 任务完成且质量通过 | 7/18 |
| 原严格综合（v1 口径） | 3/18 |
| 每题工具错误 | 1.0 |
| 每题模型调用 | 7.3 |
| 中位 / P95 耗时（秒） | 58.3 / 355.5 |
| 每题输入 / 输出 token | 61886 / 3387 |
| 前缀缓存命中率 | 74.4% |
| 每题估算成本（USD；仅被测运行，不含评委） | — |

## Astro-single：工具错误（按次数排序）

| 类别 | 次数 | 涉及题 | 其中最终未完成的题 |
| --- | ---: | ---: | ---: |
| E 事实与计算不符 | 15 | 7 | 3 |
| B 参数不符合schema | 1 | 1 | 0 |
| I 表达策略 | 1 | 1 | 0 |
| Z 其他：没有属于当前用户的占卜记录 | 1 | 1 | 0 |

最终未完成的原因：

- 结局为 ask_user，未通过：expected_status、expected_tools、saved、systems：3 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems：2 题
- 结局为 retry_limit，未通过：expected_status、expected_tools、saved、systems、safety_flag：1 题
- 达到步数或预算上限：1 题

质量维度失败次数：

- supported_conclusion：8
- direct_answer：6
- time_consistent：5
- no_fabricated_facts：3

## 参数 JSON 解析失败原因（来自 trace 的 raw_arguments）

- 没有找到
