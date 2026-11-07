# P3 星盘调参实验执行记录

- 执行日期：2026-11-07（Asia/Shanghai）。
- 按负责人提供的截图方案执行 `p3-astro` 调参集；最终验收集不在本轮范围内。
- 被测代码：PR #56 的 `b9b2e47ff5acb9d8ede7cdb08c87fd52c7eed96a`。当前主工作区仍是 `ca7787d335d73d7455a4e8f425388811eb2c3252`，没有为实验合并 PR #56。
- 源码快照：`reports/p3-astro/source`，从 Git 对象逐文件核对；对照两组使用同一份快照。
- P2 原始配置 SHA256：`d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。
- 本轮配置仅在 `pipeline.systems` 末尾增加 `astro`，系统列表为 `tarot, dream, name, daily, astro`；其余 YAML 配置与 P2 逐项一致。
- 本轮配置 SHA256：`248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`。
- 主工作区配置 SHA256：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`；实验通过快照配置运行，主工作区配置未改动。
- 使用本机既有凭据，凭据不入库；运行与评委模型沿用 P2 的 `deepseek-v4.1-flash`，同模型评分，不视为独立评审。
- 调参集 6 题，single 与 pipeline 各重复 3 次，串行运行，共36行。保留所有失败、未评分、修复、降级与原始评分。
- 费率文件与 P2 逐字节一致，费用保持未知。
- 历史留出集重评见 [heldout-rescore.md](../heldout-rescore.md) 与 [heldout-rescore.json](../heldout-rescore.json)，离线执行，无模型调用。

## 命令

在快照目录内使用主工作区 Python，输出路径指回主工作区：

```powershell
D:\知命\.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-astro --root D:\知命\reports\p3-astro --snapshot . --baseline . --publish D:\知命\docs\verification\p3\astro-pilot
```

状态与命令保存于本机 `reports/p3-astro/run-metadata.json`、`campaign.json`；原始报告、trace 和日志均保留在该目录。

实验已完整结束；结果及局限见下文与 [assessment.md](assessment.md)。

## 开跑前离线验证

在同一源码快照运行 `tests/tooling/test_heldout_timing.py`、`tests/pipeline/test_astro_requirements.py`、`tests/pipeline/test_runner_astro.py`、`tests/tooling/test_tarot_campaign.py`：133 项全部通过（527.87 秒）。这些测试使用脚本模型，不调用付费模型；包含提交结构、追问恢复、时区边界和新旧断言守卫。

## 完成状态

- 执行时间：2026-11-07 19:39:04 至 20:23:18（Asia/Shanghai），约44分14秒。
- campaign 状态为 complete，退出码0；两个子批次各退出码1表示存在评测断言失败，两份 live.json 均完整18行，不是实验中断。
- 36/36行均完成四维评分，没有未评分行；36份trace全部存在并计哈希。
- 源码指纹：`f1be4122d15c0da4624f29183a32a7a5dea6dd2b7ecaa045f8a7b2a787b60f2b`，两组179项源码哈希完全相同，全部与冻结快照字节一致。
- 两组模型请求、返回标识及评委模型均为 `deepseek-v4.1-flash`。
- 主工作区 config.yaml 未改动；快照实验配置哈希未变。未修改产品实现、提示词、校验器或评测集，未重评或补跑本批模型输出。
- 本批为调参集，不运行最终验收集，也不据此宣布 P3 完成。

## 发布材料

- [comparison.md](comparison.md)：提交、质量、延迟、调用、修复、降级及配对结果。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)：类别计数与原句归因。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：全部质量失败的评委理由和回答。
- [pipeline-problems-raw.md](pipeline-problems-raw.md)、[repair-quotes.md](repair-quotes.md)、[repair-quotes.json](repair-quotes.json)：校验问题原文与实际修复引句。
- [integrity.json](integrity.json)、[raw-manifest.json](raw-manifest.json)、[evidence-manifest.json](evidence-manifest.json)：行数、指纹、原始报告和发布文件哈希。
- 原始完整报告、trace、日志、实验配置与原配置备份保留于本机 `reports/p3-astro`，凭据文件不发布。

编造分类为 Codex 离线复核，不是独立人工裁决；所有原始失败均保留。费用因中转费率未核实保持未知。同题三次重复不视作独立样本，不外推为总体保证。
