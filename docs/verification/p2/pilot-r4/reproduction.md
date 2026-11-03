# P2 r4 执行与复核

被测提交 `0357a99c85ec5b49a43df2ba1a78cbc0a94ec30f`；仓库根目录执行，使用`.venv\Scripts\python.exe`。实验配置SHA256为`d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，与r3逐字节相同。

## 模型实验（已结束）

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r4 --snapshot . --baseline . --publish docs/verification/p2/pilot-r4
```

首次服务不可用中断，保留历史目录；09:16:48 UTC最小预检成功后，用本机`reports/p2-r4-setup/run_campaign.py --resume`启动以上命令。外层runner验证提交和配置备份，写入r3实验配置，退出后恢复原本机配置。六组各18条运行记录，106条有效四维评分。没有额外重跑已完成失败、没有补评缺失分数、没有执行最终验收集。原始数据在本机`reports/p2-r4/`。

`--snapshot .`本身不会冻结代码，因此另核对六组source-hashes完全相同、逐文件匹配实际被测内容。配置对比使用实验副本，原本机配置另验已恢复。完整性JSON记录真实未评分和未达标项，不以campaign外层退出0代替实验通过。

## 离线命令（已执行）

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r4/Dream-pipeline reports/p2-r4/Name-pipeline reports/p2-r4/Daily-pipeline --output reports/p2-r4/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r4/Dream-pipeline reports/p2-r4/Name-pipeline reports/p2-r4/Daily-pipeline --tally --output docs/verification/p2/pilot-r4/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r4/Dream-single reports/p2-r4/Dream-pipeline reports/p2-r4/Name-single reports/p2-r4/Name-pipeline reports/p2-r4/Daily-single reports/p2-r4/Daily-pipeline --answers --output reports/p2-r4/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r4/Dream-single reports/p2-r4/Dream-pipeline reports/p2-r4/Name-single reports/p2-r4/Name-pipeline reports/p2-r4/Daily-single reports/p2-r4/Daily-pipeline --counts-only --reviewed reports/p2-r4/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r4/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r4/Dream-single reports/p2-r4/Dream-pipeline reports/p2-r4/Name-single reports/p2-r4/Name-pipeline reports/p2-r4/Daily-single reports/p2-r4/Daily-pipeline --answers --reviewed reports/p2-r4/fabrication-reviewed.yaml --output reports/p2-r4/quality-reasons-reviewed.md
```

将原问题报告和带分类的质量报告分别发布为`pipeline-problems-raw.md`、`quality-reasons-with-answers.md`；只增加来源说明、统一LF和去除行尾空白，不改理由、回答或草稿文字。候选原句并不保证全部触发校验，逐次修复以原草稿、事实表和重放为依据。分类由助手在用户要求下复核，不代表新增人工校准。只分类原已提交no_fabricated_facts=false，判定key精确覆盖全部7条失败；未提交错误提示不混入计数。

## 离线重放（无模型调用）

在保留本轮原始报告、trace和KB的机器上，从被测提交检出根目录运行：

```powershell
.venv\Scripts\python.exe -X utf8 docs/verification/p2/pilot-r4/replay_false_rejections.py
.venv\Scripts\python.exe -X utf8 docs/verification/p2/pilot-r4/replay_name_claims.py
.venv\Scripts\python.exe -X utf8 docs/verification/p2/pilot-r4/replay_certainty.py
.venv\Scripts\python.exe -X utf8 docs/verification/p2/pilot-r4/replay_daily_context.py
```

解梦脚本以SQLite只读连接加载本轮KB；其他脚本仅读取实际事实表或trace。输出写到本机reports/p2-r4下，不修改原live.json，不补评分。重放输出分别为`false-rejection-replay.json`、`name-false-rejection-replay.json`、`certainty-false-rejection-replay.json`、`daily-context-replay.json`，发布副本统一为LF，内容与原输出一致。全部发布文件使用LF，发布字节的SHA256见`evidence-manifest.json`；`raw-manifest.json`保留本机原始报告字节的哈希。

完整性审计核对108条唯一题目/重复编号、每题三次、模式配对、有效布尔评分106条及两条缺口、原始报告/摘要/source-hashes、判定key与配置恢复。审计只验证结构和来源，不能独立证明评委判断可靠。B标准未满足，最终验收集未运行。
