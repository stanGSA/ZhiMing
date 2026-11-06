# P2 r13 本机运行记录

PR [#53](https://github.com/stanGSA/ZhiMing/pull/53) 已合并到 `claude_modify_model`，本机快进到合并提交 `83ce4f41319b456c89fa99b3761362177d02f4d1`。合并前 GitHub 的 Ubuntu、Windows deterministic 检查全部成功。

本机运行时间：2026-11-07 04:25:22–05:12:04（Asia/Shanghai），约 46 分 42 秒。六组各 6 题、重复 3 次，共 108 条，批处理正常退出（exit code 0）。单组 exit code 1 表示存在未通过断言的评测，原脚本按设计记录后继续，不表示整组丢失。

## 命令和配置

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r13 --snapshot . --baseline . --publish docs/verification/p2/pilot-r13
```

- 运行与评委模型：`deepseek-v4.1-flash`；开跑前连接测试回复 `OK`。
- 运行配置与 r12 一致，SHA256：`d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。
- 开跑前的本地配置仅启用 tarot 流水线，评委开启思考，不能直接用于本次 P2 对照。已备份到本机 `reports/p2-r13/config.before-r13.yaml`，运行期间使用 r12 配置，结束后按字节恢复原文件；恢复 SHA256 为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。
- 六组源码指纹一致：`fde7663cdcb41e8a5f55c1f92739a3fd43984ef80ee0dc10ef8f1c984b946b6c`。
- 本机针对 r13 修改的回归测试：**11 passed, 365 deselected**。选择器为 `r12 or label_written_again or placeholder_alone or ominous_omen`，文件为 `tests/pipeline/test_runner_dream.py` 与 `tests/pipeline/test_runner_name.py`；全量测试结果以合并前 CI 为据。

## 结果

| 组别 | 已提交 | 工程检查通过 | 质量评分通过 | 评委已评分 | 修复 / 降级 | 最大调用数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dream-single | 13/18 | 1/18 | 12/18 | 18/18 | 0 / 0 | 10 |
| Dream-pipeline | 18/18 | 18/18 | 18/18 | 18/18 | 3 / 0 | 3 |
| Name-single | 11/18 | 4/18 | 15/18 | 18/18 | 0 / 0 | 6 |
| Name-pipeline | 18/18 | 18/18 | 18/18 | 18/18 | 12 / 0 | 3 |
| Daily-single | 18/18 | 4/18 | 8/18 | 18/18 | 0 / 0 | 12 |
| Daily-pipeline | 18/18 | 18/18 | 17/18 | 18/18 | 0 / 0 | 1 |

质量评分单独评价返回文本，不代表保存或体系校验成功，因此 Name-single 的质量通过数可能高于已提交数。详细指标见 [comparison.md](comparison.md)。

三个流水线均成功提交 18/18，无降级、无工程检查失败，最大调用数均 ≤ 3。评委的 `no_fabricated_facts` 在三个流水线的 54 条中全部为 true；该结果是模型评分，尚未完成全部事实的人工复核。relay 定价表未提供核实费率，费用保持未知。

Daily-pipeline 唯一质量失败是 `daily_today_family`，`repeat=1`（第二轮），`time_consistent=false`、`supported_conclusion=false`，`no_fabricated_facts=true`。该条一次生成、无修复、无降级。评委理由涉及分段边界和“整体平稳”的支撑强度，理由中同时承认部分边界标注正确，需结合原始计算事实复核。原始评分照录，未改判。

本次完成 r13 执行与完整性核对。代码冻结仍需复核上述评分及规则检查；未运行 `p2-final`。

## 完整性与证据

[integrity.json](integrity.json) 已验证：六组各 18 条，题号/轮次无重复，每轮 6 条，108 条均已评分且 trace 文件存在；六组源码哈希逐文件相同；发布的 source-hashes 与原始记录相同；[raw-manifest.json](raw-manifest.json) 中六个报告 SHA256 全部匹配。结束后源码未变化（配置按预定恢复），campaign 锁已释放。

完整答案、逐条评分理由、trace 和运行日志保留本机 `D:\知命\reports\p2-r13`。本地 `run-metadata.json` 记录命令、时间、提交和配置恢复状态。入库材料包括六组摘要、源码哈希、对照表、失败统计、配对结果、原始报告哈希清单、完整性核对和本运行记录；原始答案、trace、本机配置及配置备份不入库。
