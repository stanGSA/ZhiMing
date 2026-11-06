# P2 r9 执行与复核

被测提交 `eed36596f9ce8a58a9804fb3be69a0087acd5966`。实验配置、样本范围、B 标准和执行前决定见 [decisions.md](decisions.md)。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r9 --snapshot . --baseline . --publish docs/verification/p2/pilot-r9
```

实际由本机 `reports/p2-r9-setup/run_campaign.py` 包装执行，并设置 `PYTHONUTF8=1`。包装器核对配置哈希、既有工作区修改和输出目录，按字节备份本机配置，临时切换为沿用 r8 的实验配置，在 `finally` 中恢复原文件。如果运行中出现外部配置编辑，保留外部修改并记录未恢复。

执行时间2026-11-06 02:30:21–03:14:41（Asia/Shanghai），退出码0；108条完成并全部有四维评分。本机配置已按字节恢复。详见 [execution.json](execution.json) 与 [integrity.json](integrity.json)。各组内部的质量失败返回码保留，campaign在报告完整时继续后组，campaign退出码0不代表质量全部通过。

六组串行，每组 6 题 × 3 次，共 108 条。全部原始失败与未评分样本保留，不替换或补跑，不改原评分。运行和 pro 评委均使用 `deepseek-v4.1-flash`，thinking 和 policy_judge 关闭；同模型评分不是独立评审。费用未知，见 [pricing.yaml](pricing.yaml)。不执行 p2-final，不查看留出题目。

执行完成后由本机 `reports/p2-r9-setup/postprocess.py` 调用 `scripts.pipeline_problems` 与 `scripts.quality_reasons` 生成离线证据。助手复核原始回答、评委理由、拒绝稿和实际计算事实，将分类及异议与原始评分分开报告。辅助脚本只存在本机忽略目录，不修改被测产品源码，不调用模型。

本机 `replay_dream.py` 回放4份解梦拒绝稿；`replay_bazi_false_positive.py`、`replay_name_false_positive.py`、`replay_name_collective.py`、`extra_single_review.py` 分别核对普通中文干支、中文数字词、集体指代和算式结果归属。`replay_daily.py` 保留15个确定性/稳赚对照，`fact_review.py` 摘录全部36条每日回答的真实日期、UTC/本地边界与相位。`write_attribution.py` 验证25条异常/修复记录均有归因，`audit.py` 核对108行唯一键、成对覆盖、评分分类、六组源码哈希及原始清单，`verify_publication.py` 核对发布文件哈希、链接、配置恢复及配置中密钥未泄漏。所有步骤0模型调用。

本机原配置 SHA256 为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`，实验配置为 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。原始 live、trace、数据库、配置和辅助脚本保留本机忽略目录。试验执行阶段没有自动提交或推送结果；负责人随后要求提交并推送本轮结果，归档范围为本目录内的报告及合成测试证据，配置和密钥不纳入提交。
