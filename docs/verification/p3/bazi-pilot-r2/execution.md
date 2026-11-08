# r2 执行记录

依据截图，在 PR #61 合并并完成修复后的本机工作区执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r2 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r2
```

| 项目 | 值 |
| --- | --- |
| 被测提交 | `c683cf6c35e0e064e03e65740d9b1f49fd210ec6` |
| PR #61 合并提交 | `cb04418fb1836f8b874be229ec0eaf5cc88a6f1b` |
| 源码指纹（183 文件） | `ca76af32f8251c6b8075f8907a28faa1b7071479514f4a3d919976866626fe62` |
| 实验 config.yaml SHA256 | `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b` |
| 原有本地 config.yaml SHA256 | `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24` |
| pricing.yaml SHA256 | `d6d6cb2c2c385d894d79cb6c054a330f79458e068ef6183744f58ea65c812ef6` |
| 北京时间 | 2026-11-09 02:49:54–03:06:49，约 16 分 55 秒 |
| single run_id | `20261108T184957-3f1e3743` |
| pipeline run_id | `20261108T190158-516d0b66` |
| 请求 / 返回运行模型 | `deepseek-v4.1-flash` |
| 请求 / 返回评委模型 | `deepseek-v4.1-flash` |

包装器 `reports/run_bazi_pilot_r2.py` 加载本机凭据后临时切换至约定配置，并在 finally 中按字节恢复运行前的本地配置。两组源文件哈希相同；除实验配置外的 182 项均与提交一致。运行结束后再次核对配置已恢复。配置原本就有未提交改动，本次没有覆盖或提交这些改动。

campaign 和包装器退出码为 0，36 条均已尝试，campaign 状态为 complete。两个评测子进程各退出 1：这是存在工程/质量失败的评测结果，不能解释为全部通过。single 另外有 12 条评委连接失败；没有在运行后重试模型、补评分或覆盖任何原始结果。证据见 [run-metadata.json](run-metadata.json)、[integrity.json](integrity.json)、[unscored-reviews.json](unscored-reviews.json)。

本机原始数据：

```text
reports/p3-bazi-r2/campaign.json
reports/p3-bazi-r2/Bazi-single/20261108T184957-3f1e3743/live.json
reports/p3-bazi-r2/Bazi-pipeline/20261108T190158-516d0b66/live.json
reports/p3-bazi-r2/config.before-bazi.yaml
reports/p3-bazi-r2/config.experiment.yaml
```

完成截图要求的后处理命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r2/Bazi-single reports/p3-bazi-r2/Bazi-pipeline --answers --output reports/p3-bazi-r2/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r2/Bazi-single reports/p3-bazi-r2/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r2/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r2/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r2/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r2/pipeline-problems-raw.md
```

`reports/extract_bazi_pilot_r2.py` 整理原答案、时间事实、修复链并核对原始哈希；`reports/finish_bazi_pilot_r2.py` 进行离线标题检查、时间核对、降级复现及生成验收 JSON。两者均不调用模型。原始报告与 trace 的哈希见 [raw-manifest.json](raw-manifest.json) 和 [trace-manifest.json](trace-manifest.json)。发布摘要保留原始分数；补充报告与摘要中缺失评分引起的统计限制。

本轮仅调参实验，未执行最终验收、冻结或额外产品修复。实验报告完成后，按用户要求将本目录材料提交并推送至 `claude_modify_model`；原始 reports 数据保留本机，原有 config.yaml 改动不纳入提交。

发布的 Markdown 和 JSON 统一为 LF 换行，并据此重算 evidence-manifest，确保 Git 中的文件字节与发布哈希一致；原始报告、trace、评分内容及 pricing.yaml 原始字节保持不变。
