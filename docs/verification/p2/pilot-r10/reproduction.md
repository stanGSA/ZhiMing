# P2 r10 执行与复核

被测提交 `2fc44b59a6de7759dcfeb48172803978f4c05662`，为 PR #52 的合并提交。范围、配置和双口径判定见 [decisions.md](decisions.md)。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r10 --snapshot . --baseline . --publish docs/verification/p2/pilot-r10
```

本机由 `reports/p2-r10-setup/run_campaign.py` 包装执行，设置 `PYTHONUTF8=1`，核对配置哈希和启动前工作区状态，按字节备份并临时替换本机配置，在 `finally` 中恢复原文件；若配置被外部编辑则保留编辑并报告。实验于 2026-11-06 19:18:11（Asia/Shanghai）开始。

实验于20:08:15结束，退出码0，全部108条运行完成，有效评分107条。Name-pipeline一条在评委两次JSON解析失败后保持未评分；没有额外补评。原本机配置已按字节恢复，六组原始报告和源码哈希一致，见 [execution.json](execution.json) 和 [integrity.json](integrity.json)。campaign退出码0表示报告完整，不代表质量或冻结条件通过。

启动前，使用实验配置运行 `tests/pipeline/test_runner_dream.py`、`tests/pipeline/test_runner_name.py` 和 `tests/plugins/test_bazi_validation.py`，结果为 **366 passed in 448.25s**。本次 PR 修改的七个 Python 文件通过 Ruff lint 和 format 检查。初次使用本机原配置时，测试无法进入未启用的 Dream/Name 流程，因此中止并在实验配置下重测；两个配置的内容不发布。

六组串行，每组 6 题 × 3 次，共 108 条。运行和 pro 评委均使用 `deepseek-v4.1-flash`，thinking 与 policy_judge 关闭。保留全部原始失败与评分，不替换、补跑或重评分。费用未知，同模型评分不是独立校准。不执行 p2-final，不查看留出题目。

后续离线证据由 `scripts.pipeline_problems`、`scripts.quality_reasons` 及本机忽略目录的辅助脚本生成；这些步骤不调用模型。复核原始回答、评委理由、拒绝稿与计算事实，记录分类及异议，保持原分。完整性审计核对每组18条唯一 `(id, repeat)`、每题重复0/1/2、两模式成对覆盖、六组源码哈希和原始报告清单。发布验证核对链接、文件哈希、配置恢复及配置密钥未泄漏。

解梦与姓名各用本轮计算事实回放实际拒绝稿；Daily安全问题仅回放同一确定性谓词，不冒充完整事务。single的Astro回放以实际daily引用顺序还原别名；普通中文“上升”的最小对照不涉及引用推断。36条每日请求均有事实索引，其中1条没有daily_result但使用了单项行运与八字期间工具。全部26条质量/修复/非提交异常完成离线归因，新旧B口径均不通过，见 [assessment.md](assessment.md)。

原始 live、trace、数据库、配置及辅助脚本留在本机忽略目录。公开材料仅含实验报告、合成样本证据和离线归因。
