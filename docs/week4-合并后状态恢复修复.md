# 第四周：PR #2 合并后的状态恢复修复

2026-10-13。PR #2 已按用户要求合并到 main，合并提交为 `fcfd88eba46cb0da2602b9b7f65bd4ccf9b51f39`。本次在此基础上修复复核发现的三个问题。

## 修复内容

1. **画像更正后旧结果仍能提交。** 专家报告新增由服务填写的 `profile_dependencies` 快照，包含该体系可见的画像字段以及未提供字段。新解读提交前逐项检查，依赖已变更的报告必须重新咨询；只重新咨询八字、留下过期占星报告，也不能提交。无关的姓名变化不使排盘失效。失败重试是否保留旧报告使用相同判断。旧报告没有字段快照时保守回退至画像版本比较；历史记录追问继续使用原事实与知识版本。
2. **取消或请求超时后丢失已抽牌面。** 不可重复计算完成时立即在 reading 所属的当前会话中保存独立事实快照，子会话退出的 finally 再做保留。保存不依赖报告成功或父级批次 commit，因此同批另一专家仍在等待时，即使整个请求被取消，已完成的牌面也能在下一轮继续使用，且禁止换牌阵。
3. **连续报告失败清空计算快照。** 新的工具结果按工具名更新已有投影，重试没有重新执行计算工具时沿用旧结果，避免空列表覆盖已有牌面。快照通过深拷贝隔离；成功报告正常合并后释放暂存快照。

更改位于 `agents/consult.py`、`agents/schemas.py`、`common/validation.py`；没有改变确定性排盘或抽牌算法，也没有增加数据库 schema 迁移。依赖快照随既有专家报告 JSON 保存。

## 回归覆盖

新增 `tests/test_week4_state_recovery.py`，共 7 个参数化场景：

- 更正出生资料后直接提交被拒，重算后可以入库。
- 更正后仅重算一个体系仍被拒；无关画像更改不会误拒，历史追问不被要求重排。
- 抽牌后取消、抽牌后整次请求超时，各自验证原牌恢复、牌阵锁定、一次抽牌、相同 reading_id、入库及调用树完整。
- 专家已完成报告但同批其他专家仍在运行时，取消/超时也保留牌面。
- 前两次报告失败、第三次成功，模型看到的计算结果数量为 `0 → 1 → 1`，全程只抽一次。

新增 7 项在修复前全部失败；修复后与原多 Agent 测试合计 38 项通过。原始本地测试证据在已忽略目录 `reports/pr2-fixes/`，包含修复前、定向及全量 JUnit 结果。

最终本地验证：全量 **295/295 通过（186.46 秒）**；Ruff check 与 format 检查通过（87 个文件）；week1 demo 的 single/multi 各 12/12。本次修复尚未推送，因此不将已合并 PR #2 的远程 CI 结果算作本次修复的 CI 验证。

```powershell
$env:PYTHONUTF8 = '1'
& .\.venv\Scripts\python.exe -m pytest tests/test_week4_state_recovery.py tests/test_multi_agent.py tests/test_multi_agent_review.py -q
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\ruff.exe check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
& .\.venv\Scripts\ruff.exe format --check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
```

后续于 2026-10-13 至 14 日完成真实模型验证：相同源码单、多 Agent 各 20 题工程检查分别为 17/20、15/20；三项修复的真实专家加故障注入专项 **7/7**，包含四种取消/超时场景，以及连续两次报告失败后 `existing_results` 数量 `0 → 1 → 1`。专项编排由脚本控制，专家真实调用模型；自然端到端证据来自完整 40 题对照。完整回答、服务错误与独立复评见[真实模型测试报告](week4-真实模型测试.md)。

第四周整体真实模型关口仍未通过，专家最终报告合规率为 83.33%，低于 98%。预算仍为软上限，同步计算取消仍受原有限制，默认仍为 single。未提交的计算快照只保证同一个 Runtime 会话中的继续操作，不声称支持进程重启后的恢复。
