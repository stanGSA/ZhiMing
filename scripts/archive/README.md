# 归档脚本

这里是为某一次验收或数据整理写的一次性脚本，保留下来是为了能复现历史报告，不属于日常开发流程。2026-10-23 之前它们位于 `scripts/` 顶层，历史文档里的 `python -m scripts.<名称>` 现在对应 `python -m scripts.archive.<名称>`。

其中 `live_pr1`、`bootstrap_week23_data`、`archive_week23` 没有命令行参数，运行即执行（分别会调用真实模型、访问网络改写数据清单、改写 `docs/verification/week23`），请先读源码再运行。

| 脚本 | 用途 | 对应记录 |
| --- | --- | --- |
| `bootstrap_week23_data.py` | 一次性抓取星历与地名数据的来源信息，生成 `scripts/data_manifest.yaml` | 第二、三周 |
| `verify_week23.py` | 逐例输出参考星盘与八字边界的计算证据，并做 Skyfield 独立核验 | [第二周](../../docs/week2-验收报告.md)、[第三周](../../docs/week3-验收报告.md) |
| `archive_week23.py` | 把本机验收指标按白名单导出到 `docs/verification/week23` | [联合测试证据](../../docs/verification/week23/README.md) |
| `review_week23.py` | 用完整行运证据重新评审已保存的真实模型回答 | 第二、三周 |
| `gate_evidence.py` | 汇总第一周关口证据（trace、SQLite、回归测试） | [第一周](../../docs/week1-验收报告.md) |
| `live_pr1.py` | PR #1 整改后的并发真实模型批次 | [PR #1 整改验收](../../docs/pr1-整改验收.md) |
| `live_week5_postmerge.py` | 第五周合并后的真实模型检查 | [第五周合并后](../../docs/week5-合并后边界修复与真实模型测试.md) |
| `live_v2_review.py` | v2 截图复评的串行延迟基线与回归场景 | [v2 截图整改](../../docs/v2-截图整改验收.md) |
| `review_week5_datasets.py` | 第五周两份草稿数据集的结构审核 | [第五周](../../docs/week5-验收报告.md) |
| `review_week6_datasets.py` | 第六周数据集定稿与结构审核 | [第六周](../../docs/week6-验收报告.md) |
| `dream_alias_regression.py` | 阶段1审核前后的解梦别名匹配对比 | [阶段1验收](../../docs/verification/stage1/20261022-acceptance/report.md) |
