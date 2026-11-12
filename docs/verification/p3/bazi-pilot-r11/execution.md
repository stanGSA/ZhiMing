# r11 执行记录

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r11 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r11
```

被测提交：`3a99b46426d8af4ff8769fec978d153a975f5298`；PR #70 合并后版本（含 b896451 的顺逆排检查修正）。

北京时间：2026-11-12 19:13:49–2026-11-12 19:33:24；1174.7秒。

源码指纹：`987feed842c4faacedfd9733e569ed2b2dedf2e33bcade3c9857a4e180579266`（183项）；实验配置：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。

配置来源：`reports/p3-bazi-r9/config.experiment.yaml`；SHA256：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。评委实际设置：`thinking=disabled`，`reasoning_effort` 未设置，模型 `deepseek-v4.1-flash`，`max_tokens=8192`。运行器使用该配置构建评委，两组工作区保存相同配置字节。

本机原配置已按原字节恢复：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。

campaign退出码：0；子进程退出1代表存在工程或质量断言失败，不会因此重跑。

- Bazi-single：run_id `20261112T111352-2e134e65`，退出码 1；`reports/p3-bazi-r11/Bazi-single/20261112T111352-2e134e65/live.json`。
- Bazi-pipeline：run_id `20261112T112722-bb1d479e`，退出码 1；`reports/p3-bazi-r11/Bazi-pipeline/20261112T112722-bb1d479e/live.json`。

包装器reports/run_bazi_pilot_r11.py在运行前保存配置、核验源码逐文件匹配提交；finally恢复本机配置。两组源码哈希与预检相同，原始报告和36条trace哈希均已核对。

后处理使用scripts.quality_reasons、scripts.pipeline_problems及reports下的extract/audit/build_bazi_pilot_r11.py，只读已保存结果，不请求模型。


数据依赖在调用模型前按 scripts/data_manifest.yaml 的7个SHA256逐一核验；缺失文件从本机 reports/pr65-review-jzw9clae/data 的既有副本补齐，未改代码。包装器另保存 reports/config.personal.before-r11.yaml；两份个人配置备份与恢复后的 config.yaml 字节相同。

评委请求参数离线按同一路径构造：extra_body.thinking.type=disabled，max_tokens=8192，未传reasoning_effort，见judge-request-options.json。这证明客户端设置；服务端内部是否遵循无法独立观测。本轮pipeline三条在运行器既有的二次解析流程中成功返回完整分数，不是事后补评。

后处理命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r11/Bazi-single reports/p3-bazi-r11/Bazi-pipeline --answers --output reports/p3-bazi-r11/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r11/Bazi-single reports/p3-bazi-r11/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r11/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r11/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r11/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r11/pipeline-problems-raw.md
```

quality-reasons.md为命令原始输出（失败条目的回答与理由）；发布的quality-reasons-with-answers.md进一步包含全部36份回答及完整原评分。repair-evidence.json保留每个检查稿，repair-quotes.json保留修复事件。分类由Codex离线完成，非独立人工校准；评委误读按约定归叙述类，原分全部保留。

本轮仅完成r11调参实验及离线证据发布；未冻结八字代码，未运行p3-bazi-final，未修改被测代码。r10另补充既有回答、理由与修复证据供复核，未重跑。
