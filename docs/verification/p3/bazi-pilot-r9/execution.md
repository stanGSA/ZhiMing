# r9 执行记录

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r9 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r9
```

被测提交：`475adf2f6cf8c9e78941a5b6325bd7ec54e96ad2`；PR #68合并后修复版本。

北京时间：2026-11-11 00:49:25–2026-11-11 01:07:47；1102.2秒。

源码指纹：`7f065d465cbb08d8f8501825b49b2b7eb2ae1d24290c7ad44a5ecb414bc73063`（183项）；实验配置：`3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`。

本机原配置已按原字节恢复：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。

campaign退出码：0；子进程退出1代表存在工程或质量断言失败，不会因此重跑。

- Bazi-single：run_id `20261110T164927-6ccee585`，退出码 1；`reports/p3-bazi-r9/Bazi-single/20261110T164927-6ccee585/live.json`。
- Bazi-pipeline：run_id `20261110T170242-fd72c4b4`，退出码 1；`reports/p3-bazi-r9/Bazi-pipeline/20261110T170242-fd72c4b4/live.json`。

包装器reports/run_bazi_pilot_r9.py在运行前保存配置、核验源码逐文件匹配提交；finally恢复本机配置。两组源码哈希与预检相同，原始报告和36条trace哈希均已核对。

后处理使用scripts.quality_reasons、scripts.pipeline_problems及reports下的extract/audit/build_bazi_pilot_r9.py，只读已保存结果，不请求模型。
