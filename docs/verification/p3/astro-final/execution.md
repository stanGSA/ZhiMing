# 星盘最终验收执行记录

- 时间：2026-11-08 19:22:04至19:38:16（Asia/Shanghai），约16分12秒。
- 工作区：`D:/知命`；Python 3.11，`.venv/Scripts/python.exe`。
- 被测提交：`babeceaad67d2ab8887cbc30041b568aece4051e`，分支 `claude_modify_model`。
  对比冻结合并 `d7c3ff89f6e39f48f41038be781e85e7fdbd0cf1` 仅有docs变更，符合截图要求。
- 最终验收集 `evals/cases/astro_final.yaml`，4题×3次×2模式，共24条；single、pipeline串行运行一次。
- 配置直接取r3保存字节，SHA256为
  `248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`；
  启用体系为 `[tarot, dream, name, daily, astro]`。
- 两组源码指纹均为
  `1b96414d8332a4c3388150b99d6992d94117296a13030fe0f99ba1dc0a5ff53c`。
  共179项哈希，其中178个非配置文件与被测Git提交逐字节一致。
- 原有个人配置运行前备份、结束后按原字节恢复；恢复SHA256为
  `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。
- 24/24完成四维评分，无未评分记录；12对repeat/id匹配，24份trace存在并记录哈希。
- rubric `v2-2026-10-24`；运行和评分请求及返回模型均为 `deepseek-v4.1-flash`。
  `--judge pro`不是实际型号；本批为同模型评分，未经独立人工校准。
- single模型请求85次，pipeline13次；评分各12条，single评分请求尝试13次、pipeline12次。
  评分层既有自动重试保留，未手动重新评分或补跑。
- 两子批次因断言失败均退出1，但完整报告各12条；campaign状态complete、退出0。
  完整执行与验收通过是不同判定，验收结论见 [assessment.md](assessment.md)。
- 未修改产品源码、提示词、计算器、知识库、题目或rubric，未替换失败样本。
- pricing沿用此前用户提供的中转配置，费率未核实，`models: {}`，费用未知。

## 命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-astro-final --root reports/p3-astro-final --snapshot . --baseline . --publish docs/verification/p3/astro-final
```

本机 `reports/run_astro_final.py` 包装了配置备份与恢复、冻结提交检查、配置和源码指纹校验、
凭据环境载入、pricing准备以及执行元数据记录；实际campaign参数与截图一致。
报告处理脚本位于忽略的reports目录，没有加入被测源码目录。

```powershell
.venv\Scripts\python.exe -X utf8 -m reports.finalize_astro_final
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-astro-final/AstroFinal-single reports/p3-astro-final/AstroFinal-pipeline --counts-only --reviewed docs/verification/p3/astro-final/fabrication-reviewed.yaml --output docs/verification/p3/astro-final/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-astro-final/AstroFinal-pipeline --output docs/verification/p3/astro-final/pipeline-problems-raw.md
```

后处理只读取已保存数据，不调用模型或改分。编造分类是Codex离线分类，分类表“完整”不表示独立人工复核完成。
全部发布文本统一LF，生成 [evidence-manifest.json](evidence-manifest.json)；原始报告与trace字节未改。
凭据、原始配置备份和本地数据库未纳入发布材料。

## 证据位置

原始记录保留在 `D:/知命/reports/p3-astro-final`，执行元数据为该目录 `run-metadata.json`。
run ID分别为 `20261108T112206-a16e9965`（single）、`20261108T113344-7e91f1c8`（pipeline）。

- [assessment.md](assessment.md)：验收判定、指标与局限。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：24条原始回答与完整评委理由。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)：分类计数与依据。
- [repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)：唯一修复的原文与引句。
- [temporal-evidence.json](temporal-evidence.json)：各题实际计算区间、时区和澄清次数。
- [acceptance.json](acceptance.json)：按原始评分的四条通过条件及编造指标。
- [integrity.json](integrity.json)、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)：源码、原始报告及trace的完整性。
