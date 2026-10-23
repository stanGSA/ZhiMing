# 知识库模型交叉审核：运行目录

每个子目录是 `scripts/model_review_kb.py` 的一次审核运行，结论见[阶段1验收](../stage1/20261022-acceptance/report.md)和[阶段1执行记录](../stage1/README.md)。

## 2026-10-23 精简

为减少仓库体积，以下两类原始文件已从当前目录树移除，共 1672 个文件、约 12.4 MB：

| 移除内容 | 数量 | 说明 |
| --- | --- | --- |
| `*/runner_source/`、`*/revision_runner_source/` | 344 个文件，约 7.0 MB | 每次运行时复制的审核脚本源码（`model_review_kb.py`、`llm.py` 等）。各运行的 `manifest.json` 记录了 `script_sha256`，与这些副本一致 |
| `*/calls/` | 1328 个文件，约 5.4 MB | 每次模型调用的原始请求与返回记录 |

保留的是汇总与判定依据：`manifest.json`、`batches.json`、`merged.json`、`checks.json`、`revisions.json`、`revision_queue.json`、各级 `report.md`、`campaign/` 下的账本事件、预算 `budget.json`，以及测试和脚本直接读取的文件。`knowledge/reviews/*.yaml` 引用的报告全部保留。

移除前的完整目录在提交 [`64ec624`](https://github.com/stanGSA/ZhiMing/tree/64ec62489bbd26a836b85e3708a9595d4164e302/docs/verification/kb-model-review) 中，内容未作任何改动。需要对这些历史运行重新执行 `merge`、`ledger` 或断点续跑时，先恢复原始文件：

```bash
git checkout 64ec62489bbd26a836b85e3708a9595d4164e302 -- docs/verification/kb-model-review
```

新的审核运行仍会在各自目录下写出 `runner_source/` 与 `calls/`。
