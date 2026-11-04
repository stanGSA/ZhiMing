# P2 r6 执行与复核

被测提交 `35233fef6598abe82a8c8c53e57310901ccc5c7e`；配置 SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。2026-11-04 本机串行运行 6 组，各18条（6题×3次），全部108条完成并评分。接口独立探测返回HTTP 200，不计入实验样本。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r6 --snapshot . --baseline . --publish docs/verification/p2/pilot-r6
```

实际经本机 `reports/p2-r6-setup/run_campaign.py` 包装执行以上命令。包装器核对提交、原本机配置及实验配置哈希，临时切换配置，finally 按字节恢复。`original_local_config_restored=true`，原配置 SHA256 恢复为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。模型/评委请求与返回均为 `deepseek-v4.1-flash`，评委profile为pro、thinking关闭；不构成独立评审。

campaign整体退出0，所有六组均有完整 live.json。各子组因质量/工程断言失败可退出1，这是保留的实验结果，不是报告丢失或需要重跑的依据。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r6/Dream-pipeline reports/p2-r6/Name-pipeline reports/p2-r6/Daily-pipeline --output reports/p2-r6/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r6/Dream-pipeline reports/p2-r6/Name-pipeline reports/p2-r6/Daily-pipeline --tally --output docs/verification/p2/pilot-r6/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r6/Dream-single reports/p2-r6/Dream-pipeline reports/p2-r6/Name-single reports/p2-r6/Name-pipeline reports/p2-r6/Daily-single reports/p2-r6/Daily-pipeline --answers --output reports/p2-r6/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r6/Dream-single reports/p2-r6/Dream-pipeline reports/p2-r6/Name-single reports/p2-r6/Name-pipeline reports/p2-r6/Daily-single reports/p2-r6/Daily-pipeline --counts-only --reviewed reports/p2-r6/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r6/fabrication-counts.md
```

本机 `postprocess.py` 生成问题/质量摘录，`replay_validation.py` 使用本轮计算事实离线复核拒绝片段，`audit.py` 检查配对、重复编号、原始报告/发布哈希、全部source hashes、分类key与原配置恢复，`verify_publication.py` 核对发布文本、链接与配置密钥泄漏。原始数据与辅助脚本保留在本机 reports；密钥、配置、原数据库不发布。

本轮只执行p2调参集。未查看最终验收题目内容，未运行p2-final。B未通过，不冻结，详见 [assessment.md](assessment.md)。
