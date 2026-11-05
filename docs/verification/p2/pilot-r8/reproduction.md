# P2 r8 执行与复核

负责人要求按截图执行下列调参命令。被测提交为 `e01a0083f01b30383db73eae4f1a92ce8937361d`，包括 PR #50 合并及相位别名／反向角色漏检修复。实验配置沿用 r7，SHA256 为 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，执行前记录见 [decisions.md](decisions.md)。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r8 --snapshot . --baseline . --publish docs/verification/p2/pilot-r8
```

实际由本机 `reports/p2-r8-setup/run_campaign.py` 包装执行该命令，并设置 `PYTHONUTF8=1` 使子进程沿用 UTF-8。包装器在启动时检查除本机配置外工作区干净、输出目录没有既有实验、配置哈希吻合；准备阶段核对被测提交。运行前备份本机配置，临时切换实验配置，结束后在 `finally` 中按字节恢复原文件。若运行中检测到配置被外部修改，保留该修改并记录未恢复，避免覆盖外部编辑。

执行时间为 2026-11-05 22:08:18–23:02:03（Asia/Shanghai），退出码0，本机原配置已按字节恢复。108条运行完成，107条完整四维评分，Daily-pipeline / daily_unknown_birth_time#3 在评委两次解析后仍失败，保留未评分，不补跑。执行元数据见 [execution.json](execution.json)。接口独立预检返回 HTTP 200 与 `deepseek-v4.1-flash`，不计入正式样本。

六组串行，每组 6 题 × 3 次，共 108 条；single 与 pipeline 使用同批题目及重复编号。运行和 pro 配置评委均请求 `deepseek-v4.1-flash`，thinking 关闭，policy_judge 关闭；同模型评分不是独立评审。费用未知，见 [pricing.yaml](pricing.yaml)。不替换、剔除或补跑失败样本，不改原评分，运行中不改产品源码和提示词，不运行 p2-final 留出集。

模型执行完成后使用以下离线命令生成复核材料（不调用模型）：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r8/Dream-pipeline reports/p2-r8/Name-pipeline reports/p2-r8/Daily-pipeline --output reports/p2-r8/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r8/Dream-pipeline reports/p2-r8/Name-pipeline reports/p2-r8/Daily-pipeline --tally --output docs/verification/p2/pilot-r8/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r8/Dream-single reports/p2-r8/Dream-pipeline reports/p2-r8/Name-single reports/p2-r8/Name-pipeline reports/p2-r8/Daily-single reports/p2-r8/Daily-pipeline --answers --output reports/p2-r8/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r8/Dream-single reports/p2-r8/Dream-pipeline reports/p2-r8/Name-single reports/p2-r8/Name-pipeline reports/p2-r8/Daily-single reports/p2-r8/Daily-pipeline --counts-only --reviewed reports/p2-r8/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r8/fabrication-counts.md
```

助手对照原始回答、评委理由、拒绝稿和实际计算事实复核分类及缺陷，不称为独立人工校准。原始 `no_fabricated_facts=false` 计数与另查出的漏判分开报告，不通过重新打分把争议条目改为通过。

本机辅助脚本位于 `reports/p2-r8-setup/`：`postprocess.py` 生成摘录，`replay_dream.py` 回放实际解梦拒绝稿及最小对照，`replay_daily.py` 回放每日拒绝稿作者文本的共用确定性／安全谓词（保留占位符，不执行完整提交事务），`fact_review.py` 摘取评分异议相关实际事实，`audit.py` 核对108个题目／重复编号、成对覆盖、评分完整性、原始报告哈希、六组源码哈希、分类覆盖及配置恢复，`verify_publication.py` 核对发布摘录、链接和密钥泄漏。离线回放均0模型调用。源码指纹、完整指标与 B 判定见 [integrity.json](integrity.json) 和 [assessment.md](assessment.md)。

复核没有把未知评分补成通过；全部已知编造失败键已覆盖，但1条未评分使统计仍不完整，`pipeline_fact_fabrication_zero` 因完整性要求未通过。B同时受已定位校验误拒阻止，不冻结、不执行p2-final。负责人随后要求将实验结果提交并推送；归档范围为本目录内的报告与证据，原始数据、配置和密钥仍保留本机。

本机原配置 SHA256 为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。原始 live、trace、数据库、配置备份及辅助脚本保存在本机忽略目录；发布材料只包含合成测试证据，不包含配置与密钥。
