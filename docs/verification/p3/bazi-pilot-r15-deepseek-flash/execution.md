# r15 官方 deepseek-flash 执行记录

完成：18/18 single、18/18 pipeline，36 条均保留原始评分，未补评或改写。记录时间（北京时间）：2026-11-14T07:40:37.520712+08:00。

按用户 2026-11-14 最新指示，使用新提供的官方 key、官方 API 地址，仅调用 `deepseek-flash`。运行模型、专家、运行审校和 rubric 评委均配置此模型；评委别名仍叫 `pro`，实际不是 Pro 模型，thinking=disabled、max_tokens=8192。

PR #75 已合并为 `cdbe346`。实际运行工作树 HEAD 为 `448c90dcf10a5f4680deebd78f754fbfe48f8a16`（PR head），使用 r9 配置副本调整运行/评委模型名；配置 SHA256 `ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`。不是旧约定配置 `3dfa2e81`；两组源码指纹一致，见 integrity.json / source-hashes。

官方探针三项通过，输出 token 为 1、21、1。前几条正式样本逐条检查未见之前把内部推理直接当回答的现象。首次官方尝试因缺少 GeoNames 文件在 3 条后中断；其数据单独归档，不参与这次 36 条统计。随后 scripts.fetch_data 核验并补齐全部数据、knowledge.build 构建知识库，从全新目录启动。

| 指标 | single | pipeline |
| --- | ---: | ---: |
| 已提交 | 14/18 | 18/18 |
| 已提交质量通过 | 11/14 | 14/18 |
| 综合通过 | 6/18 | 14/18 |
| 每题最多调用 | 11 | 2 |
| 修复 / 降级 | 0 / 0 | 5 / 2 |
| 评委每行输出 token 中位数 | 356.0 | 386.0 |
| 运行每次调用输出 token 中位数 | 137 | 732 |
| 已提交 no_fabricated_facts=false | 3 | 3 |

campaign 正常 complete；job 退出码 1 表示有断言/质量失败，不表示实验中断。两组共用相同题集、rubric、数据和配置，只切换 single/pipeline。费用未知（官方现行单价未复核）；同模型评委未经独立人工校准。

结论：服务已能完成整轮调用，但不能冻结。pipeline 提交更完整、调用更少；已提交质量通过率 14/18（77.8%）低于 single 的 11/14（78.6%），且存在原始编造评分失败。配对任务完成且质量通过为 pipeline 胜6、single胜3、平9，18 对，仅作小样本描述。评委有疑似误读，见原始理由，保留原分，未把怀疑当作已纠正。

可复核证据：comparison.md、metrics.json、36 份 supplement-answers.md/.json、repair-evidence.json、repair-quotes.json、quality-failures.json、quality-reasons-with-answers.md、pipeline-problems-raw.md、service-probe.json、run-metadata.json、integrity.json、raw/trace/evidence-manifest.json。事实类/叙述类人工归因未完成，fabrication-counts.md 明确保留待判项；本轮没有作冻结决定。

执行后恢复个人功能范围，同时永久保留用户授权的新模型/官方连接配置。本地 .env 由 Git 忽略，证据不含 key。旧 key/个人配置仅保存在本地忽略目录备份。
