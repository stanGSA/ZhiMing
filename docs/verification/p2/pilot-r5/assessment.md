# P2 r5 实验评估：未冻结

2026-11-03；被测提交 `a609baaa74ef31e7cb98090578fb7bf2743a0ffe`，配置 SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。六组共 108 条，全部完成并评分；每题三次重复、single/pipeline 配对完整。源码指纹 `bbbe083a9725166a8c4a6d72aee3859b54db6cfec5edae01ca67b24fb28747b2`，逐组 source hashes 相同且匹配被测文件。原本机 config 已恢复，SHA256 为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。

| 体系 | single 提交/质量 | pipeline 提交/质量 | pipeline 调用上限 | 步数/预算失败 | pipeline 修复/降级 |
| --- | --- | --- | ---: | ---: | ---: |
| 解梦 | 12/18；12/12 | 18/18；18/18 | 3 | 0 | 8/1 |
| 姓名 | 11/18；9/11 | 18/18；16/18 | 2 | 0 | 4/4 |
| 每日运势 | 18/18；10/18 | 18/18；18/18 | 1 | 0 | 0/0 |

提交率、调用、预算和 pipeline 事实类编造门槛均满足。三个 pipeline 已提交质量不低于同批 single。108 条全部有四维评分；八条已提交的 `no_fabricated_facts=false` 已逐条分类，详见 [编造分类计数](fabrication-counts.md)。所有成功调用和评委返回模型均为 `deepseek-v4.1-flash`；运行与评委是同一模型，不构成独立评审。费用未知，未运行最终验收集。

**不满足冻结条件，不运行 `p2-final`。** Dream-pipeline 虽为 18/18，但 8/18 有修复、1/18 降级。离线问题报告发现校验把来源原句中的“到处找不到出口”变体（如“商场里找不到出口”）报成事实表外内容；这属于可定位的解梦校验误拒，需先修复并另行重跑。其余 dream 候选拒绝、姓名 4 次修复/降级及全部质量失败的逐条原文和处理依据见 [问题报告](pipeline-problems-raw.md)、[质量理由与回答](quality-reasons-with-answers.md) 与 [质量归因](quality-attribution.md)。八条编造失败的具体分类见[分类依据](fabrication-review-notes.md)。原始评分不变；错误/拒绝和未完成样本均保留，不补分、不剔除。

原始 live 数据、trace、数据库和问题草稿保留在本机 `reports/p2-r5/`。发布材料是合成评测数据的复核摘录，不含本机配置或密钥。结构和来源审计见 [integrity.json](integrity.json)，发布文件哈希见 [evidence-manifest.json](evidence-manifest.json)。
