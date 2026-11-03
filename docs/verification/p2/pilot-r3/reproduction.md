# P2 r3 执行与复核

实验在仓库根目录使用`.venv\Scripts\python.exe`执行。被测提交为`b38eb2a`，实验配置SHA256为`d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。原始报告和trace保留在本机`reports/p2-r3/`。

## 已执行的模型实验

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r3 --snapshot . --baseline . --publish docs/verification/p2/pilot-r3
```

外层本机runner先检查并备份现有配置，写入与r2逐字节相同的指定实验配置，再执行上面的命令，最终恢复本机原配置。它不改变被测脚本，不增加失败样本复跑。`campaign.json`中的各组退出码1表示完成后有断言失败，全部六组仍有完整18条`live.json`；外层campaign退出0。

`--snapshot .`参数本身不会创建冻结副本，故额外逐组核对了`source-hashes.json`，六组源码指纹和配置哈希完全一致，结束后还逐文件对照了被测代码与实验配置副本。未执行`p2-final`。

## 已执行的离线报告命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r3/Dream-pipeline reports/p2-r3/Name-pipeline reports/p2-r3/Daily-pipeline --output reports/p2-r3/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r3/Dream-pipeline reports/p2-r3/Name-pipeline reports/p2-r3/Daily-pipeline --tally --output docs/verification/p2/pilot-r3/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r3/Dream-single reports/p2-r3/Dream-pipeline reports/p2-r3/Name-single reports/p2-r3/Name-pipeline reports/p2-r3/Daily-single reports/p2-r3/Daily-pipeline --answers --output reports/p2-r3/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r3/Dream-single reports/p2-r3/Dream-pipeline reports/p2-r3/Name-single reports/p2-r3/Name-pipeline reports/p2-r3/Daily-single reports/p2-r3/Daily-pipeline --counts-only --reviewed reports/p2-r3/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r3/fabrication-counts.md
```

随后用同一`--reviewed`文件加`--answers`再渲染一份带分类的详细报告；发布到`quality-reasons-with-answers.md`时增加来源说明，并统一LF换行、移除Markdown空引用行的尾随空格；理由与回答文字不变。`pipeline-problems-raw.md`同样在不加`--tally`的输出前增加来源说明，并规范Markdown空白。判定YAML及逐条依据一并发布。

## 离线误拒重放

在保留原始实验数据的本机仓库根目录运行：

```powershell
.venv\Scripts\python.exe -X utf8 docs/verification/p2/pilot-r3/replay_false_rejections.py
```

脚本以SQLite只读模式加载本轮KB，用原报告中的实际命中和misses重放三个单句：两处误拒及一条同词候选句的正常接受路径。不会访问模型，只写本机`reports/p2-r3/false-rejection-replay.json`。

完整报告SHA256见`raw-manifest.json`，额外发布的证据文件SHA256见`evidence-manifest.json`。完整性验证还核对了108条四维布尔评分、每题三次、模式间配对、分类key恰好覆盖全部编造失败、原始报告与摘要一致，以及本机配置已恢复。人工复核部分实际由助手执行，原始分数保持不变。
