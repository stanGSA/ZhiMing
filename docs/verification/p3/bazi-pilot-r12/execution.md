# r12 执行记录

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r12 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r12
```

被测提交：`15b4b1bcec901591060bba82797cbb811943d9e2`；PR #71 合并后版本（含审阅发现的4处回归修正）。

北京时间：2026-11-12 22:11:37–2026-11-12 22:31:30；1193.0秒。

源码指纹：`61c901d54664b211aebe65a4d7d78cb60881557c1e3d451510f0d8da91c33930`（183项）；实验配置：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。

配置来源：`reports/p3-bazi-r9/config.experiment.yaml`；SHA256：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。评委实际设置：`thinking=disabled`，`reasoning_effort` 未设置，模型 `deepseek-v4.1-flash`，`max_tokens=8192`。运行器使用该配置构建评委，两组工作区保存相同配置字节。

本机原配置已按原字节恢复：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。

campaign退出码：0；子进程退出1代表存在工程或质量断言失败，不会因此重跑。

- Bazi-single：run_id `20261112T141139-51310a96`，退出码 1；`reports/p3-bazi-r12/Bazi-single/20261112T141139-51310a96/live.json`。
- Bazi-pipeline：run_id `20261112T142441-32cbbec0`，退出码 1；`reports/p3-bazi-r12/Bazi-pipeline/20261112T142441-32cbbec0/live.json`。

包装器reports/run_bazi_pilot_r12.py在运行前保存配置、核验源码逐文件匹配提交；finally恢复本机配置。两组源码哈希与预检相同，原始报告和36条trace哈希均已核对。

后处理使用scripts.quality_reasons、scripts.pipeline_problems及reports下的extract/audit/build_bazi_pilot_r12.py，只读已保存结果，不请求模型。


运行前按scripts/data_manifest.yaml核验7项数据SHA256；两份个人配置备份与恢复后的config.yaml逐字节一致。评委请求选项见judge-request-options.json，记录客户端设置，不声称独立验证服务端内部行为。

single投资#3在运行器原有解析重试流程中产生第2次评委请求，最终全部36条均有完整四维分数。campaign整体退出0，两组子进程各退出1表示有工程或质量断言失败，不以此触发重跑。离线包装器预检出现一次未await close的RuntimeWarning，未发模型请求、不改变被测执行和原结果。

后处理命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r12/Bazi-single reports/p3-bazi-r12/Bazi-pipeline --answers --output reports/p3-bazi-r12/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r12/Bazi-single reports/p3-bazi-r12/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r12/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r12/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r12/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r12/pipeline-problems-raw.md
```

quality-reasons-with-answers.md包含36份原回答及评分，repair-evidence/repair-quotes保留全部被检稿和事件。Codex离线分类，非独立人工校准；误读按约定纳入叙述类，原分全部保留。38项原报告与trace在后处理前后逐项校验一致。实验证据提交范围仅限本目录；个人config.yaml和reports下本机原始文件不包含在提交中。
