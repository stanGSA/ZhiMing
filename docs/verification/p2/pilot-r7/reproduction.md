# P2 r7 执行与复核

被测提交 `da447c41bbff650bb953c260157357de99872f6c`，包括PR #49合并、三类审查回归修复及负责人批准的否定“稳赚”放行；“奔跑→被追”保持现有范围，见 [decisions.md](decisions.md)。实验配置沿用r6，SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r7 --snapshot . --baseline . --publish docs/verification/p2/pilot-r7
```

实际经本机 `reports/p2-r7-setup/run_campaign.py` 包装执行以上截图命令。包装器开跑前核对提交及配置哈希，临时切换为实验配置，结束后在finally中按字节恢复本机原配置。本机私有配置、密钥、数据库均不发布。接口预检返回HTTP 200与 `deepseek-v4.1-flash`，独立于正式样本。

六组串行，各6题×3次；所有失败、修复、降级和评分均保留，没有替换、剔除或补跑。运行与pro评委均请求同一模型 `deepseek-v4.1-flash`，thinking关闭、policy_judge关闭；同模型评分不构成独立评审。中转费率未经核实，费用未知，见 [pricing.yaml](pricing.yaml)。

执行前在隔离副本中以仓库配置和本机缓存的公开计算数据验证：`tests/validation`（不含耗时 `test_accept_paths_generated.py`）、`tests/pipeline`、`tests/test_p1.py`、`tests/tooling/test_tarot_campaign.py` 合计 **737 passed、6 xfailed**，716.16秒；CI范围Ruff check与format --check通过，251文件。未声称全量pytest通过。

完成后的离线证据命令（不调用模型）：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r7/Dream-pipeline reports/p2-r7/Name-pipeline reports/p2-r7/Daily-pipeline --output reports/p2-r7/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r7/Dream-pipeline reports/p2-r7/Name-pipeline reports/p2-r7/Daily-pipeline --tally --output docs/verification/p2/pilot-r7/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r7/Dream-single reports/p2-r7/Dream-pipeline reports/p2-r7/Name-single reports/p2-r7/Name-pipeline reports/p2-r7/Daily-single reports/p2-r7/Daily-pipeline --answers --output reports/p2-r7/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r7/Dream-single reports/p2-r7/Dream-pipeline reports/p2-r7/Name-single reports/p2-r7/Name-pipeline reports/p2-r7/Daily-single reports/p2-r7/Daily-pipeline --counts-only --reviewed reports/p2-r7/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r7/fabrication-counts.md
```

本机 `postprocess.py` 生成上述摘录和分类汇总，`replay_validation.py` 用实际计算事实逐份回放10份解梦拒绝稿，并重放6份每日运势拒绝稿的共用安全规则、10个最小检查，不生成新回答也不改分。`publish_fact_review.py` 发布有争议每日评分的合成日期、相位与引用摘录。`audit.py` 核对108条唯一题目/重复编号、每题0/1/2、成对覆盖、原始与发布哈希、六组源码哈希、分类key及本机配置恢复。`verify_publication.py` 核对发布摘录、链接、配置密钥泄漏及发布文件哈希。原始live、trace、数据库和辅助脚本保留在本机 `reports/p2-r7/` 与 `reports/p2-r7-setup/`。

运行时间2026-11-05 18:53:39–19:41:54（Asia/Shanghai）；campaign整体退出0，各子组因质量或工程断言失败退出1仍保留完整live.json，不是重跑依据。全部108条评分完整。六组源码指纹一致：`362d6a8edd2bb86b33368193041674a54d34c35b94c6616a63cfa22822e29eaf`。本机原配置按字节恢复，SHA256 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`；未提交该本机配置。

本轮只运行p2调参集，运行中不修改产品源码与提示词。B不通过，不冻结，未运行p2-final，见 [assessment.md](assessment.md)。
