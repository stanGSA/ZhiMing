# P2 r5 执行与复核

被测提交 `a609baaa74ef31e7cb98090578fb7bf2743a0ffe`；实验配置 SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。2026-11-03 执行 p2 六组，每组 18 条、每题三次重复，共 108 条；全部有四维评分。请求与评委返回模型均为 `deepseek-v4.1-flash`，评委与运行模型相同。费用未知，最终验收集未运行。

campaign 命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r5 --snapshot . --baseline . --publish docs/verification/p2/pilot-r5
```

运行前通过 `reports/p2-r5-setup/check_endpoint.py` 检查接口。外层 `run_campaign.py` 校验提交、实验配置与原始本机配置，临时切换配置并在退出时恢复。实验结束 `original_local_config_restored=true`；本机原配置哈希恢复为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。实验配置另存为 `reports/p2-r5-setup/experiment-config.yaml`，没有提交本机 `config.yaml`。

离线复核命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r5/Dream-pipeline reports/p2-r5/Name-pipeline reports/p2-r5/Daily-pipeline --output reports/p2-r5/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r5/Dream-pipeline reports/p2-r5/Name-pipeline reports/p2-r5/Daily-pipeline --tally --output docs/verification/p2/pilot-r5/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r5/Dream-single reports/p2-r5/Dream-pipeline reports/p2-r5/Name-single reports/p2-r5/Name-pipeline reports/p2-r5/Daily-single reports/p2-r5/Daily-pipeline --answers --output reports/p2-r5/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r5/Dream-single reports/p2-r5/Dream-pipeline reports/p2-r5/Name-single reports/p2-r5/Name-pipeline reports/p2-r5/Daily-single reports/p2-r5/Daily-pipeline --counts-only --reviewed reports/p2-r5/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r5/fabrication-counts.md
```

完整性审计验证 108 个唯一题目/重复编号、每题重复 0/1/2、single/pipeline 配对、原始报告与发布摘要哈希、六组 source hashes、分类 key 覆盖以及本机配置恢复。B 标准未满足：解梦 pipeline 的修复记录包含可定位误拒；因此不冻结、不运行 `p2-final`。详细结果见 [assessment.md](assessment.md)。
