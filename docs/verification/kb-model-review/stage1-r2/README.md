# 阶段1第二轮知识库审核（活动目录）

本目录是第二轮审核的活动目录，运行步骤见[本机运行手册](../../stage1/r2-runbook.md)。

| 文件 | 来源 | 何时出现 |
| --- | --- | --- |
| `dream-alias-review.yaml` | `python -m scripts.dream_alias_review draft`：被删解梦别名的逐条复核（Anthropic Claude 起草） | 已提交；负责人决定后 `apply` |
| `calibration.yaml` | `python -m scripts.draft_calibration`：标注校准集，分开发集与保留集（Anthropic Claude 起草） | 已提交 |
| `owner-decisions.json` | 负责人 2026-10-22 的决定 | 已提交 |
| `dream-alias-regression-after.json` | 恢复别名后重测解梦准确率与召回率 | 第 1 步 |
| `calibration.lock.json` | 负责人确认后 `kb_review_calibration freeze`；记录开发集、保留集各自的哈希与历次冻结 | 第 2 步 |
| `pilot-N/<体系>/` | `kb_review_live pilot`：只审开发集；`pilot-summary.json` 含分歧清单 | 第 3 步，最多 3 轮 |
| `preregistration.json`、`campaign-acceptance.json` | `kb_review_live preregister`：写入后不能改写，并关闭逐批写账本 | 第 4 步，须在审核前推送 |
| `<体系>-initial/`、`<体系>-rereview-N/` | 正式审核的完整证据 | 第 5 步 |
| `budget.json` | 本活动（含试跑）的调用与用量账本 | 第 3 步起 |
| `campaign/`、`coverage.json` | `kb_review_live accept`：按登记口径的体系验收与三态覆盖率 | 第 6 步 |

试跑目录位于第二层（`pilot-N/<体系>/`），不会被体系验收计入。2026-10-21 的第一轮活动保留在 [20261021-live](../20261021-live/) 中，作为失败记录；本活动独立验收，其结论取代第一轮写入的账本批准。
