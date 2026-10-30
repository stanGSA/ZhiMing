# 评测总表

由 `uv run python -m evals.report` 生成于 2026-10-30T17:07:41+00:00（Linux-6.18.44-fc-v185-x86_64-with-glibc2.39，Python 3.11.17，用时 10.2 秒）。

离线可复现：离线演示模型与确定性代码，不调用任何付费模型。离线演示的工具选择与审校是规则基线，只验证流程与计分口径，不代表真实模型的工具选择、解读质量或安全能力。

## 离线结果

| 维度 | 指标 | 结果 | 数据集（状态） | 说明 |
| --- | --- | --- | --- | --- |
| 工具选择 | 工具集合 F1（single） | 1.000；适用 12/80 题，通过 12（草稿） | `trajectory.yaml`（草稿，待审核） | 离线演示规则模型回放 evals.run 的塔罗题；其余题需要真实模型 |
| 工具选择 | 工具 / 专家集合 F1（multi） | 1.000 / 1.000；适用 12/80 题，通过 12（草稿） | `trajectory.yaml`（草稿，待审核） | 同上，编排者经专家子会话调用工具 |
| 事实 | 参考星盘 | 11/11，最大黄经误差 0.000110364° | `reference_charts.yaml`（计算生成并交叉校验） | Skyfield/JPL 交叉校验未运行（缺少 data/ephe/de440s.bsp） |
| 事实 | 八字边界 | 50/50 用例，57 个规则或追问变体 | `bazi_boundary.yaml`（计算生成并交叉校验） | 立春、节气、子时、真太阳时、夏令时、闰月 |
| 事实 | 姓名笔画 | 200/200；其中 19 字的金标待人工定稿，这部分 19/19（草稿） | `name_strokes.yaml`（计算生成并交叉校验） | 公认姓氏五格笔画 37/37 |
| 事实 | 每日运势跨会话一致 | 10 次调用 1 种结果；同 seed 抽牌 100 次一致 | 合成画像，无数据集 | 后 9 次中 9 次读缓存 |
| 安全 | 危机识别 | 5/5（草稿） | `safety.yaml`（草稿，待审核） | 运行时停止占卜并给出求助回复（与 tests/runtime 同一组检查） |
| 安全 | 高风险提示（代码层） | 4/25（草稿） | `safety.yaml`（草稿，待审核） | HIGH_RISK 命中的题强制 safety.flag 与安全说明；其余依赖模型自行标注，离线不评估 |
| 审校 | 漏拦率 / 过度干预率 | 6.7% / 6.7%（草稿） | `reviewer_drafts.yaml`（草稿，待审核） | 离线关键词基线，不是 LLM 审校；关口 ≤10% / ≤5%，未全部达到 |
| 延迟 | 离线单轮 P50 / P95 | single 31.0 / 68.0 ms；multi 35.0 / 49.0 ms | `trajectory.yaml`（草稿，待审核） | 审校单次 1.1 / 1.3 ms；本机测得，不含模型调用耗时 |

标“草稿”的结果来自待审核数据集，不作为验收结论。

## 真实模型（只读归档摘要）

以下数字读取 `docs/verification/p1/` 的已归档摘要，用 `scripts.failure_taxonomy` 的口径重算，本命令不重新运行任何模型。评委与被测模型同厂商，人工校准未完成，评委可靠性未经人工验证；详见 [P1 实施与验收](../../docs/verification/p1/README.md)。

| 批次 | 日期 | 被测模型 | 模式 | 评委 | 口径版本 | 题 × 次 | 任务完成 | 质量通过 | 已提交回答质量通过 | 严格综合 | P50 / P95 秒 |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0-multi | 2026-10-24 | deepseek-flash | multi | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 10/60 | 8/60 | 5/8 | 2/60 | 0.5 / 83.8 |
| B0-single | 2026-10-24 | deepseek-flash | single | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 38/60 | 31/60 | 20/29 | 10/60 | 21.4 / 88.7 |
| codego-v4/B0-multi | 2026-10-24 | deepseek-v4-flash | multi | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 37/60 | 25/60 | 11/25 | 14/60 | 138.5 / 252.7 |
| codego-v4/B0-single | 2026-10-24 | deepseek-v4-flash | single | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 34/60 | 24/60 | 10/26 | 9/60 | 73.9 / 163.7 |
| codego-v4/Compare-multi-lite | 2026-10-25 | deepseek-v4-flash | multi-lite | deepseek-v4-pro | v2-2026-10-24 | 12 × 3 | 6/36 | 4/36 | 4/8 | 0/36 | 148.6 / 254.3 |
| codego-v4/Compare-multi | 2026-10-25 | deepseek-v4-flash | multi | deepseek-v4-pro | v2-2026-10-24 | 12 × 3 | 6/36 | 6/36 | 5/11 | 0/36 | 147.1 / 216.7 |
| codego-v4/Compare-single | 2026-10-25 | deepseek-v4-flash | single | deepseek-v4-pro | v2-2026-10-24 | 12 × 3 | 11/36 | 8/36 | 8/12 | 1/36 | 117.4 / 284.7 |
| codego-v4/Final-multi | 2026-10-25 | deepseek-v4-flash | multi | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 33/60 | 28/60 | 11/22 | 8/60 | 106.6 / 231.9 |
| codego-v4/Final-single | 2026-10-25 | deepseek-v4-flash | single | deepseek-v4-pro | v2-2026-10-24 | 20 × 3 | 37/60 | 24/60 | 13/25 | 10/60 | 92.2 / 280.3 |

留出场景（规则断言，无评委）：codego-v4/B0-heldout（2026-10-25，deepseek-v4-flash）14/17；codego-v4/Final-heldout（2026-10-25，deepseek-v4-flash）16/17。

日期取自批次编号。`p1/` 顶层两批是改用中转接口前的旧活动，`codego-v4/` 是中转接口活动，其中 Final 为当前实现。任务完成不计 zero_tool_errors；严格综合为 v1 口径（全部工程检查与四项质量评审同时通过）。

## 数据集状态

| 数据集 | 文件 | 状态 |
| --- | --- | --- |
| trajectory | `evals/cases/trajectory.yaml` | 草稿，待审核 |
| reference_charts | `evals/cases/reference_charts.yaml` | 计算生成并交叉校验 |
| bazi_boundary | `evals/cases/bazi_boundary.yaml` | 计算生成并交叉校验 |
| name_strokes | `evals/cases/name_strokes.yaml` | 计算生成并交叉校验；逐项：auto_ok 181，needs_review 19 |
| safety | `evals/cases/safety.yaml` | 草稿，待审核 |
| reviewer_drafts | `evals/cases/reviewer_drafts.yaml` | 草稿，待审核 |

## 未通过的用例

- 工具选择（single）：无
- 工具选择（multi）：无
- 参考星盘：无
- 八字边界：无
- 姓名笔画：无
- 高风险提示未被代码识别：safety-001、safety-002、safety-003、safety-005、safety-006、safety-007、safety-008、safety-010、safety-012、safety-013、safety-014、safety-015、safety-017、safety-018、safety-019、safety-020、safety-026、safety-027、safety-028、safety-029、safety-030
- 审校判错：draft-001、draft-006、draft-039
