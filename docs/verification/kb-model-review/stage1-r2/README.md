# 阶段1第二轮知识库审核（活动目录）

本目录是第二轮审核的活动目录，运行步骤见[本机运行手册](../../stage1/r2-runbook.md)。

| 文件 | 来源 | 何时出现 |
| --- | --- | --- |
| `calibration.yaml` | `python -m scripts.draft_calibration` 生成的标注校准集草稿（Anthropic Claude 起草） | 已提交 |
| `owner-decisions.json` | 负责人 2026-10-22 的决定 | 已提交 |
| `calibration.lock.json` | 负责人确认后运行 `kb_review_calibration freeze` | 第 2 步 |
| `preregistration.json`、`campaign-acceptance.json` | `kb_review_live preregister`；写入后不能改写，并关闭逐批写账本 | 第 3 步，须在审核前推送 |
| `<体系>-initial/`、`<体系>-rereview-N/` | 每次审核的完整证据：计划、原始输入输出、修改稿、已应用的修改、指标 | 第 4 步 |
| `budget.json` | 本活动的调用与用量账本 | 第 4 步 |
| `campaign/`、`coverage.json` | `kb_review_live accept`：按登记口径的体系验收与三态覆盖率 | 第 5 步 |

2026-10-21 的第一轮活动保留在 [20261021-live](../20261021-live/) 中，作为失败记录。本活动独立验收，其结论取代第一轮写入的账本批准。
