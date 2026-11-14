# PR #78 合并前边界修复（2026-11-15）

本次修复离线复核中发现的两个问题，不代表 r17 实验已完成或满足冻结条件。

- 相邻大运与相邻十年共用参照解析。句中明确指定历史大运时，从该步核对前后十年；显式“当前大运”仍按当前步核对。并列的前后步继续共享原参照，避免把前一项的答案误当作后一项的参照。
- 被引用的“稳赚”只有在劝阻框架成立时才放行。“保持距离是不必要的”“保持距离没有意义”等后置否定不再被误读为风险提醒。后续分句、换行中的否定及双重否定不撤销真正的提醒。

回归用例覆盖正确与错误的历史参照、显式当前参照、两类相邻表述混用，以及共享 `hard_claim`、流水线 `safety_rules` 和 single 模式的校验（含开启语义评委的路径）。

验证：

- `tests/pipeline/test_bazi_pilot_r12.py`、`test_bazi_pilot_r16.py`、`test_bazi_pilot_r17.py` 与 `tests/validation/test_gain_policy.py`：共 237 项通过。最后补充换行边界后，重新运行共享规则测试，90 项通过。
- 修改的 Python 文件通过 `ruff check`、`ruff format --check`；`git diff --check` 通过。
- 修复前 PR 提交 `74f542f` 的既有 [Ubuntu CI](https://github.com/stanGSA/ZhiMing/actions/runs/43634764283/job/132569030076)：3239 passed、3 failed、6 xfailed。三个失败均在 `tests/knowledge/test_live_review_regressions.py`，涉及入库配置已切换为官方 DeepSeek 后的旧双厂商审核断言，与本次两处修改无关。

r17 的真实模型实验仍按 r16 复核文档 §7 执行；实验配置、评分口径及负责人发布的 r16 证据文件未作修改。
