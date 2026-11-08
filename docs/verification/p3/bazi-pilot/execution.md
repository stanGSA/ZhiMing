# 八字调参集执行记录

- 时间：2026-11-08 23:45:36至2026-11-09 00:04:47（Asia/Shanghai），约19分11秒。
- 工作区：`D:/知命`；Python 3.11，`.venv/Scripts/python.exe`。
- 被测提交：`7ba34e6f4dfc5d1e211f8215b688f60b01975b0c`，分支`claude_modify_model`。
- 调参集：`evals/cases/bazi_pilot.yaml`，6题×3次×2模式，共36条；single、pipeline串行各运行一次。
- 基础配置SHA256：`248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`。
  直接读取此前保存的原始字节，只将`pipeline.systems`末尾增加`bazi`，其他字节未变。
- 八字约定配置SHA256：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。
  体系为`[tarot, dream, name, daily, astro, bazi]`。
- 两组源码指纹：`7a6f3d2d08f69d8ffd68f571c7605fa718a8b548de4be47b22076ea88036548a`。
  183项哈希一致，182个非配置文件与被测Git提交逐字节一致。
- 原有个人配置运行前备份，结束后按字节恢复；恢复SHA256为
  `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。
- 36/36条完成四维评分，无未评分；18对repeat/id一致，36份trace存在且哈希已核验。
- rubric为`v2-2026-10-24`；两组运行及评分请求/返回均为`deepseek-v4.1-flash`。
  `--judge pro`只是角色名，同模型评分未经独立人工校准。
- single模型请求122次；pipeline21次。评分各18条，评分请求尝试分别18次、20次。
  评分自动重试及既有JSON尾逗号清理由原脚本执行，原始返回保留，没有手动重评。
- 两子批次均因部分评测断言失败退出1，但各有18条完整报告；campaign状态complete、退出0。
  完整运行与验收通过是不同判定，见 [assessment.md](assessment.md)。
- 未修改产品源码、提示词、计算器、知识库、题目或rubric；未补跑、替换失败样本。
- pricing采用目录已有文件，与此前星盘配置逐字节相同；中转费率未核实、`models: {}`，费用未知。

## 命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot
```

本机`reports/run_bazi_pilot.py`仅包装版本核对、配置哈希及字节备份/恢复、
源码指纹校验、凭据环境载入及执行元数据记录；实际campaign参数与截图一致。
后处理脚本均保留在忽略的reports目录，没有进入被测源码路径。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi/Bazi-single reports/p3-bazi/Bazi-pipeline --answers --output reports/p3-bazi/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi/Bazi-single reports/p3-bazi/Bazi-pipeline --counts-only --reviewed reports/p3-bazi/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi/Bazi-pipeline --output docs/verification/p3/bazi-pilot/pipeline-problems-raw.md
```

分类是Codex离线分类，不是负责人裁决。后处理只读取保存数据，不调用模型，不修改原始评分。
发布文本统一LF，并生成[evidence-manifest.json](evidence-manifest.json)；原始报告和trace字节未改。
凭据、原始配置和本地数据库未纳入发布材料。

## 证据位置

原始记录：`D:/知命/reports/p3-bazi`；run ID为`20261108T154538-2d7505f9`（single）、
`20261108T155852-51afb4ea`（pipeline）。

- [assessment.md](assessment.md)、[acceptance.json](acceptance.json)：指标、原分结论和局限。
- [Bazi-single-summary.json](Bazi-single-summary.json)、[Bazi-pipeline-summary.json](Bazi-pipeline-summary.json)：两组摘要。
- [Bazi-single-source-hashes.json](Bazi-single-source-hashes.json)、[Bazi-pipeline-source-hashes.json](Bazi-pipeline-source-hashes.json)：两组完整源码哈希。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：36条回答和原始评委理由。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)：分类计数、依据和异议。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：全部修复的引句和复核。
- [temporal-evidence.json](temporal-evidence.json)、[temporal-checks.json](temporal-checks.json)：各题计算范围、时区及追问次数。
- [integrity.json](integrity.json)、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)：完整性核验。
