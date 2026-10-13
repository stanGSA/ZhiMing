# 第四周验收报告：多 Agent 编排

日期：2026-10-13。基线为远程 main 的 `893c189`（v2_update）。在分支 `claude/wonderful-goldberg-a5h6rp` 上开发，未推送 main。

## 结论

- **工程实现完成，离线验证通过。** 编排者 + 3 位体系专家、并行 `consult_specialist`、专家权限与知识分区、失败隔离、追问上抛、共享预算、嵌套 trace 均已实现。275 项测试中 263 项通过；其余 12 项都依赖 JPL DE440s 星历，本环境网络策略禁止下载，与 main 在同一环境中的结果相同。新增 18 项多 Agent 测试全部通过，并做了两项变异检查，确认关键测试能抓到回退。
- **真实模型测试未验证。** 本环境没有 `.env`，也没有 `OPENAI_API_KEY`，`scripts.check_model` 和 `scripts.live_week23 --mode multi` 都在创建模型时报"未设置 OPENAI_API_KEY"。单、多 Agent 的 20 题对照、真实路由 F1 和真实时延/token 都没有数据，这里不写任何真实模型通过结果。
- **第 4 周关口"单、多两种模式都跑通"只在离线条件下满足**（脚本化模型与 demo 模型）。真实模型下的关口尚未验证，不能宣布通过。默认配置因此仍为 `mode: single`。

## 实施范围与计划对照

| 计划要求 | 实现位置 | 验证 |
|---|---|---|
| 编排者 | `agents/orchestrator.py` 新增 `MULTI_SYSTEM_PROMPT`；多 Agent 模式下编排者工具表只有画像、地点、记录、`lookup_meaning`（追问）、`consult_specialist`、`ask_user`、`submit_reading` | `test_multi_mode_tool_tables` |
| 5 位专家 | **本周 3 位**：占星、八字、塔罗（`agents/specialists.py`）。姓名、解梦插件第 6 周才有，专家按插件生成，插件缺专家定义会直接报错 | 同上 |
| 并行 consult_specialist | `harness/loop.py`：同一步内连续的 `parallel_safe` 调用并发执行，结果按模型发出的顺序提交并写回 | `test_parallel_consult_merges_persists_and_traces`（三专家互相等待的屏障；改为串行时该测试失败） |
| 专家权限 | 每位专家一个独立工具表：本插件工具 + `lookup_meaning` + `submit_report`；guard 的角色与分区检查仍在 | `test_specialist_cannot_cross_tools_or_partitions`：越权调用返回 `unknown_tool`，跨分区查询返回 `partition_denied` |
| 上下文隔离 | 子会话只含专家提示词、日历基准、本体系画像字段和子问题 JSON；看不到其它专家和完整对话 | 同上；画像里不含姓名 |
| 失败隔离 | 超时、异常、步数或预算用尽都返回 `status=failed`；`submit_reading` 要求 `systems_used` 排除失败体系，`confidence.reason` 写明缺少哪个体系 | `test_failed_specialist_is_isolated_and_disclosed`、`test_specialist_timeout_is_a_failed_report` |
| 预算 | `harness/budget.py`：一次请求一个预算，编排者与专家共享；专家受单独上限约束，且给编排者保留收尾额度 | `test_reserve_keeps_budget_for_orchestrator`、`test_budget_propagates_reserve_and_deadline` |
| 嵌套 trace | trace 增加 `parent_call_id`；父会话记录 `specialist_started/finished`；`scripts/trace_tree.py` 重建调用树并检查完整性 | 全链路测试中调用树无问题，3 个子会话分别对应 3 次咨询调用 |
| 单 Agent 对照基线 | `mode: single` 时代码路径与前三周一致 | 原有 257 项测试在本环境的结果与 main 相同 |
| 审核 trajectory.yaml | 已做结构一致性审核，结果见下文；**人工审核未完成** | 0 处结构不一致 |

## 关键设计

1. **子问题不当作用户原话。** 编排者写的子问题只进入子会话的模型上下文。用户原话从父会话复制，只供出生资料、性别和口径的核验使用（`run_turn(..., as_evidence=False)`）。测试中编排者在子问题里编造出生时间，专家排盘被核验拒绝。把这一条改回"计入原话"后，该测试失败。
2. **追问上抛，合并成一次。** 专家没有 `ask_user`。子会话内任何工具返回 `needs_input`，harness 立即结束该子会话，报告 `status=needs_input`，由编排者合并成一次追问。`needs_input` 报告从不缓存；成功报告的缓存键包含用户消息条数和画像版本，所以用户补充资料后会重新咨询。
3. **结果并回父记录，业务库只由编排者写。** 成功专家的信号、引用、计算结果、chart_id、bazi_id、牌面和时间范围，按调用顺序并入父记录，并检查时间范围是否冲突。因此前三周的提交校验、事实校验、`save_reading` 和读取原记录的追问都没改。业务记录和 `specialist_reports` 在同一事务里写入；报告只存信号引用编号，信号本身仍在 `readings.signals_json`。
4. **塔罗每个记录只抽一次。** 塔罗报告有效后，同一记录内再次咨询直接返回该报告；抽牌种子仍由父记录提供。
5. **同一步内的冲突。** 同一步重复咨询同一体系，返回 `duplicate_consult`。各专家时间范围不一致，返回 `timeframe_conflict`。时间范围还要经过和前三周相同的用户原话区间检查。
6. **追问不咨询专家。** 读取原记录进入追问模式后，`consult_specialist` 会被拒绝，追问用原记录和 `lookup_meaning` 回答。

## 与计划的差异

| 差异 | 原因与处理 |
|---|---|
| 专家 3 位而非 5 位 | 姓名、解梦插件在第 6 周；插件没有专家定义时启动即报错，加入时 harness 不需要改 |
| 专家会写排盘缓存表（charts、bazi_charts） | 这是按输入哈希的计算缓存，不是业务记录。所有写操作都在同一个事件循环线程、同一个 SQLite 连接里串行执行，没有写锁冲突。readings 和 specialist_reports 只由编排者写 |
| 默认模式仍是 single | 真实模型对照没有数据，暂不切换；`--mode multi` 或 `config.yaml` 可以开启 |
| 预算没有照搬计划（6 万 token、专家 30 秒） | 沿用前三周实测后的 180000 总预算；新增：每位专家 40000 token、120 秒、最多 6 步，编排者保留 30000 token，最多 3 位专家并发；多 Agent 模式整次请求墙钟上限 300 秒（单 Agent 模式不加墙钟上限，保持前三周行为）。这些是初值，需要真实运行后重新标定 |
| 审校 | 第 5 周；`reviewer.enabled` 仍必须为 false |

## 实际测试结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 全量 pytest | 275 项：263 通过，1 失败，11 错误 | 12 项都需要 `data/ephe/de440s.bsp`：doctor 必需项 1 项、Skyfield 独立对照 11 项。本环境拒绝连接 ssd.jpl.nasa.gov；main `893c189` 在同一环境下也是这 12 项。远程 CI 会下载该文件 |
| 新增多 Agent 测试 | 18/18 | `tests/test_multi_agent.py` |
| 原有测试 | 245 项在本环境可运行的全部通过 | 单 Agent 路径未回退 |
| Ruff check / format | 通过 | |
| 离线 week1 流程（demo 模型） | single 12/12，multi 12/12；离线专家集合 F1 = 1.000 | 只是流程回放，不代表真实模型的路由能力 |
| 三体系标注路线回放（single） | 50/50，跳过 30 | 与前三周相同 |
| CLI | `cli.py draw --mode multi --provider demo` 正常提交，`scripts.trace_tree` 输出调用树、无问题 | |
| 真实模型 | **未验证** | 原因见上 |

脱敏证据在 [verification/week4](verification/week4/README.md)：`pytest.json` 列出每项测试状态和环境原因，`offline.json` 是离线评估汇总。

## 首次失败与修复记录

- **新增多 Agent 测试首次运行：17/17 通过。** 为排除"测试太弱所以通过"，做了两项变异检查，检查后已恢复原代码：
  - 把子问题改为计入用户原话：`test_brief_is_context_not_user_evidence` 失败；
  - 把专家并发上限改为 1（串行）：`test_parallel_consult_merges_persists_and_traces` 失败。
- **首次全量回归**：262 通过，12 项失败或错误，全部是 JPL 文件缺失，与 main 在同一环境的结果一致，不是产品缺陷。
- **提交前复查发现的问题**：新增的整次请求墙钟上限（300 秒）原本也作用于单 Agent 模式。前三周有单 Agent 回答接近这个时长，会改变已验收的行为。已改为只在多 Agent 模式生效，并新增第 18 项测试 `test_single_mode_has_no_wall_clock_deadline`；修正后全量复测为 275 项中 263 项通过，其余 12 项仍是 JPL 文件缺失。
- **开发中自查后修改的问题**（都在首次测试运行前，所以没有失败记录可保留）：
  - 并行结果原先按调用 id 对应，模型给出重复 id 时会串位，已改成按位置对应；
  - demo 模型重构时有一处收尾语法错误，运行前已修正。
- **真实模型首次尝试**：`scripts.check_model` 和 `scripts.live_week23 --mode multi --cases bazi_trait --no-judge` 都因缺少 `OPENAI_API_KEY` 退出。没有发出请求，也没有产生用量。

## 真实模型测试（未验证，需在有密钥的环境运行）

```powershell
$env:PYTHONUTF8 = '1'
uv run python -m scripts.check_model
uv run python -m scripts.live_v2_review --suite baseline --mode single --output reports/week4/live-single
uv run python -m scripts.live_v2_review --suite baseline --mode multi --output reports/week4/live-multi
```

- 两次运行使用同一套 20 题和评分标准，串行执行。
- 多 Agent 模式的结果额外包含 `multi_agent` 指标：专家越权尝试数与比例、`submit_report` 首次提交通过率、成功/追问/失败报告数、最大并发专家数。
- 专家会话的工具错误同样计入"零工具错误"断言。
- 还缺两项真实评估：
  - `trajectory.yaml` 适用题的真实路由 F1。目前的回放脚本只适用于单 Agent 标注路线，`evals.run --suite trajectory --mode multi` 会明确拒绝运行。
  - 故障注入（把专家超时调小后看真实模型如何收尾）。

## trajectory.yaml 审核（结构一致性，非人工审核）

用脚本检查了 80 道题的 `expected` 字段：
- 每题专家集合与单 Agent 计算工具所属体系一致；
- 禁用工具与期望工具、可选工具没有交集；
- 有行运必有本命盘，有流期必有原局；
- 有专家时编排者工具都包含 `consult_specialist`。

**结果：0 处不一致。** 8 类各 10 题。不涉及姓名、解梦、每日运势的有 53 题。

逐类阅读的观察：
- 追问类有 3 题期望咨询专家（traj-074 重抽、traj-075 换新问题、traj-080 下下个月），都标注 `new_reading: true`，和"新问题才开新记录并咨询"的实现一致。另有 2 道追问题把流期或行运计算列为可选工具；多 Agent 模式下追问不再咨询专家，可选项不扣分，两者不冲突。
- traj-040"这周运势"按时机类处理（占星 + 八字），不是 `daily_fortune` 单日场景。
- traj-064"只看星盘：下个月财运"需要财务主题信号，但占星条目的 finance 倾向值目前全为 0（D5），回答只能是中性的。

数据集状态仍是 `draft_needs_review`，人工审核需由项目负责人完成。本次没有修改数据集。

## 未完成事项

1. 真实模型的单、多 Agent 20 题对照，以及真实时延与 token 数据。
2. 真实路由 F1 与体系越界率（trajectory 适用题）；真实故障注入。
3. `trajectory.yaml` 人工审核。
4. 姓名、解梦专家（第 6 周）；审校和跨体系合并（第 5 周）。
5. 根据真实数据重新标定预算和超时。
6. 前三周遗留问题：知识条目人工审核率 0%；D5 信号内容（感情、财务主题和占星本命倾向为 0）；D6 持续容许度窗口；D13 独立评审与人工校准；D14 万年历抽查。

## 验收判断

| 关口条目 | 状态 |
|---|---|
| CI 双平台通过，新增测试通过，单 Agent 原有测试不变 | 本地满足（受 JPL 限制的 12 项除外）；远程 CI 以本分支的 Actions 结果为准 |
| 单 Agent 20 题不低于 week3-final 基线 | 未验证 |
| 多 Agent 20 题全部执行，零越权，报告合规率 ≥ 98%，调用树完整 | 离线满足；真实模型未验证 |
| 单、多 Agent 对照表 | 未验证 |
| trajectory.yaml 人工审核与第一版真实路由 F1 | 结构审核完成；人工审核和真实 F1 未完成 |

**判断：代码层面已具备第 4 周能力，可以进入真实模型验收；第 4 周关口本身尚未通过。** 有密钥的环境跑完上面的命令、并拿到单、多 Agent 对照数据后，再决定是否切换默认模式、是否进入第 5 周。

## 复现（离线）

```powershell
$env:PYTHONUTF8 = '1'
uv sync --locked --extra llm
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run pytest -q
uv run python -m evals.run --suite week1 --mode single --output reports/week4/offline
uv run python -m evals.run --suite week1 --mode multi --output reports/week4/offline
uv run python -m evals.run --suite trajectory --output reports/week4/trajectory
uv run python cli.py draw --question "A 公司还是 B 公司？" --spread decision --seed 42 --mode multi --provider demo
uv run python -m scripts.trace_tree --user local --reading <reading_id>
```
