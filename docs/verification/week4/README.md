# 第四周验收材料（脱敏汇总）

日期：2026-10-13。这里只保存指标和测试状态，不含对话、trace、数据库或下载数据；原始 JUnit 和离线评估输出在被忽略的 `reports/week4/`。

| 材料 | 结果 |
|---|---|
| [pytest.json](pytest.json) | 275 项：263 通过，12 项（doctor 1 项、Skyfield 11 项）因本环境无法下载 JPL DE440s 而失败或报错；新增多 Agent 测试 18 项全部通过 |
| [offline.json](offline.json) | demo 模型 week1 流程：single 12/12，multi 12/12（离线专家集合 F1 1.000）；单 Agent 标注路线回放 50/50，跳过 30 |
| 真实模型 | **未验证**：本环境没有 `.env` 和 `OPENAI_API_KEY`，没有发出请求 |

离线数字只说明流程能跑通，不代表真实模型的路由、回答质量或安全能力。详细说明见 [第四周验收报告](../../week4-验收报告.md)。
