# P2 final 本机运行记录

按截图命令完成解梦、姓名、每日运势的 single / pipeline 六组对照，每组 4 题、重复 3 次，共 72 条。运行时间为 2026-11-07 16:32:47–17:07:02（Asia/Shanghai），约 34 分 15 秒，campaign 正常退出（exit code 0）。单组 exit code 1 表示有评测断言未通过，六组报告均完整生成。

## 命令与冻结范围

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```

- 运行提交：`1c3341c2e24a9221e56cfeafc4f55bc0e97b9a58`。此前 PR [#53](https://github.com/stanGSA/ZhiMing/pull/53) 已合并至 `claude_modify_model`，合并提交为 `83ce4f41319b456c89fa99b3761362177d02f4d1`。
- 六组均使用 r13 同一份被测代码与配置，174 项 source-hashes 逐项相同。源码指纹：`fde7663cdcb41e8a5f55c1f92739a3fd43984ef80ee0dc10ef8f1c984b946b6c`。
- 实验配置 SHA256：`d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。运行期间没有调整提示词、校验规则或用最终集反馈调参。
- 模型与评委均请求并返回 `deepseek-v4.1-flash`；评委配置别名为 `pro`，本次实际型号仍为 Flash，评委思考关闭。comparison 的通用型号尾注已按本次实际记录澄清，指标值照录。
- 原本的本地配置只启用 tarot 流水线，已在结束后按字节恢复；恢复 SHA256：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。配置内容与备份不发布。

## 六组结果

| 组别 | 成功提交 | 工程检查通过 | 质量评分通过 | 已评分 | 修复 / 降级 | 最大模型调用数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DreamFinal-single | 8/12 | 2/12 | 9/12 | 12/12 | 0 / 0 | 11 |
| DreamFinal-pipeline | 12/12 | 12/12 | 12/12 | 12/12 | 5 / 2 | 3 |
| NameFinal-single | 6/12 | 2/12 | 10/12 | 12/12 | 0 / 0 | 7 |
| NameFinal-pipeline | 12/12 | 12/12 | 12/12 | 12/12 | 7 / 2 | 3 |
| DailyFinal-single | 12/12 | 1/12 | 7/12 | 11/12 | 0 / 0 | 5 |
| DailyFinal-pipeline | 12/12 | 12/12 | 10/12 | 12/12 | 2 / 0 | 2 |

质量评分单独评价返回文本，未提交文本也可以通过质量评分，不能以质量通过数替代成功提交数。每日单模型 7/12 是 7 条通过、4 条失败、1 条未评分；只看已评分则为 7/11。工程检查与任务完成口径也不同，详见 [comparison.md](comparison.md) 的原始指标。

三个流水线合计成功提交 36/36、工程检查通过 36/36、质量通过 34/36。14 次修复中 10 次修复稿通过校验，4 次再次被拒后降级，均为 keywords：解梦 `dream_final_dinner_with_ex#2/#3` 与姓名 `name_final_compare#2/#3`。流水线最终回答的编造维度 36/36 为 true，但这只是模型评分，没有独立人工逐条裁决。

## 评分缺失与争议

`DailyFinal-single / daily_final_overall#2` 的评委连续两次返回无效 JSON，`ValueError`、`scored=false`、`quality_pass=null`。已保存两次原始回复到 [unscored-reviews.json](unscored-reviews.json)，没有修补 JSON 后改判或重新调用评委。全批只有 71/72 条完成评分，完整性文件明确标记 `all_results_scored=false`。

每日流水线两条质量失败均为 `daily_final_overall#2/#3`，仅 `time_consistent=false`，没有修复或降级。它们的原始理由和回答见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：

- 第 2 次的理由明确写“时间一致性可判true”“time_consistent应判true”，但返回布尔值为 false，存在输出自相矛盾。
- 第 3 次也承认丙戌段为 UTC 15:00–16:00，即 Asia/Shanghai 23:00–24:00，却仍据相同表述判时间失败；另对乙酉的分段概括提出不够精确的意见。原计算有两个相邻的乙酉段，当地边界为 00:00、17:52:05、23:00，最后一段丙戌为 23:00–24:00。保留原判，未将这些争议自动改成通过。

本轮结果描述运行表现，不代表已完成评委校准或全部规则验收。姓名“外格一样”误报、三才标签重复、解梦场景拦截及否定停药表述误报详见 [repair-attribution.md](repair-attribution.md)。[review-fact-excerpts.json](review-fact-excerpts.json) 保留相关姓名五格、正则匹配片段、原始每日分段及其本地时间换算，便于复核。

## 截图要求的发布材料

1. [fabrication-counts.md](fabrication-counts.md)：通过 `scripts.quality_reasons --counts-only --reviewed reports/p2-final/fabrication-reviewed.yaml` 生成。4 条失败均为每日单模型、离线分类为叙述类；每日单模型仍有 1 条未评分，比例保持 33.3%–41.7% 区间，表格保留“不完整”。分类依据见 [fabrication-attribution.md](fabrication-attribution.md)，分类由 Codex 完成，非独立人工裁决。
2. [pipeline-problems-raw.md](pipeline-problems-raw.md)：通过 `scripts.pipeline_problems` 对三个流水线导出，保留 31 条校验问题原文与候选原句。候选原句不等于 repair 实际引句。
3. [repair-quotes.json](repair-quotes.json) / [repair-quotes.md](repair-quotes.md)：14 次修复的 30 条实际引句、被拒稿、成稿与 trace 哈希。30 条均存在于原稿、均未在最终回答逐字保留；不能把降级回答中的删句认作修复稿成功。

编造计数表的生成命令为：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-final/DreamFinal-single reports/p2-final/DreamFinal-pipeline reports/p2-final/NameFinal-single reports/p2-final/NameFinal-pipeline reports/p2-final/DailyFinal-single reports/p2-final/DailyFinal-pipeline --counts-only --reviewed reports/p2-final/fabrication-reviewed.yaml --output docs/verification/p2/final/fabrication-counts.md
```

问题原文的生成命令为：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-final/DreamFinal-pipeline reports/p2-final/NameFinal-pipeline reports/p2-final/DailyFinal-pipeline --output docs/verification/p2/final/pipeline-problems-raw.md
```

## 完整性与可复核范围

[integrity.json](integrity.json) 验证六组各 12 条、每轮 4 条、题号/轮次不重复，六个原始报告 SHA256 与 [raw-manifest.json](raw-manifest.json) 相符；六组 174 项源码哈希相同并匹配 r13，发布副本匹配原始 source-hashes。72 条 trace 存在，campaign 锁已释放，本地配置已恢复。

[evidence-manifest.json](evidence-manifest.json) 记录发布文件的 SHA256、原始报告清单与全部 trace 哈希。发布文本按 UTF-8 / LF 计哈希，与 Git 文件内容一致；原始报告与 trace 仍按运行时原始字节计哈希。原始完整 live.json、日志、trace 和配置备份保留在本机 `D:\知命\reports\p2-final`；发布材料包含所要求的原句和必要诊断副本。

本次仅增加实验结果与离线证据，未改被测代码，因此没有另跑实现回归测试；验证范围是本次执行、报告与证据的一致性。relay 的核实 token 单价缺失，费用保持未知；同题三次重复并非独立样本，不将小样本结果外推为总体保证。
