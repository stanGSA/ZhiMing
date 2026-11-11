# r10 重跑执行记录

日期：2026-11-11（UTC）

截图指定的 `config.yaml` SHA256 `3dfa2e81…` 在本地工作区、提交历史和 stash 中均不可用。负责人确认改用当前配置后，实验在隔离快照中进行：基于提交 `9def101`，保留当前配置的 DeepSeek `deepseek-v4.1-flash` 运行模型、评委和其他参数，只将 `pipeline.systems` 从 `[tarot]` 扩展为 `[tarot, bazi]`，使 `p3-bazi` 的 pipeline 组实际走 Bazi pipeline。实验快照配置 SHA256：`124e1324177e313e56affd5ff83a19fa8f2d50b2ad50550db026b56ad009a4f0`；两组 source-hashes 均记录此值。主工作区原有 `config.yaml` 未改动。

执行 `scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r10 --snapshot <isolated-snapshot> --baseline <isolated-snapshot> --publish docs/verification/p3/bazi-pilot-r10`。首次启动因隔离快照缺少本机忽略文件 `data/geo/geonamescache-3.0.2.whl`，在 single 组四条记录后中断；该次部分记录保存在 reports 中，不计入最终批次。补入与主工作区其他归档副本 SHA256 相同的 GeoNames wheel 后重跑，最终批次为 single `20261111T130539-c957eeb8`、pipeline `20261111T133204-493a5b80`，各 18 条，三次重复。

Campaign 状态为 complete。两组 live evaluation 的退出码均为 1，表示有验收失败，但完整 `live.json` 和报告已生成。single：13/18 提交、10/18 已评分、3/18 未评分、提交样本质量通过 2/13；pipeline：18/18 提交并评分，质量通过 16/18。配对结果为 pipeline 胜 15、single 胜 1、平 2。费用未知；运行模型和评委均报告为 `deepseek-v4.1-flash`，不属于独立评审。

`quality-reasons.md` 保存在 `reports/p3-bazi-r10/`，`pipeline-problems-raw.md` 与比较报告保存在本目录。编造分类计数已生成，但分类仍待人工复核：single 有 5 条编造失败待判、另有 3 条未评分；pipeline 有 2 条待判。没有伪造负责人判定或补评分。原始回答和 trace 保留在本机 `reports/p3-bazi-r10/`。
