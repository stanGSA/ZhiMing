# 第四周验收报告：多 Agent 编排

> 合并后更新（2026-10-14）：本文保留 PR 开发阶段的环境与测试结论。PR #2 已合并；后续三项状态恢复修复的真实专家专项 7/7，相同源码单、多模式各 20 题工程检查为 17/20、15/20，专家最终报告合规率 83.33%，整体关口未通过。当前结果、原始失败和评审复测见[真实模型测试](week4-真实模型测试.md)。下文“未验证/未完成”描述原 PR 阶段，不代表尚未执行这些后续测试。

日期：2026-10-13。基线为远程 main 的 `893c189`（v2_update）。在分支 `claude/wonderful-goldberg-a5h6rp` 上开发，未推送 main。首版提交 `ea35679`；之后按 PR #2 评审意见修复 7 项边界问题，见下文“PR #2 评审整改”。

## 结论

- **工程实现完成，离线验证通过。** 编排者 + 3 位体系专家、并行 `consult_specialist`、专家权限与知识分区、失败隔离、追问上抛、共享预算、嵌套 trace 均已实现。评审指出的 7 项边界问题已修复，每项都有回归测试，并用变异检查确认测试能抓到回退。全量 288 项测试中 276 项通过；其余 12 项都依赖 JPL DE440s 星历，本环境网络策略禁止下载，与 main 在同一环境中的结果相同（评审者在有星历的机器上首版为 275/275 通过）。多 Agent 测试共 31 项（首版 17 项 + 评审回归 14 项），全部通过。
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
| 失败隔离 | 超时、异常、步数或预算用尽都返回 `status=failed`；`submit_reading` 要求 `systems_used` 排除失败体系，`confidence.reason` 写明缺少哪个体系。同一体系重试失败时保留先前有效报告；画像版本变化时撤销旧结果 | `test_failed_specialist_is_isolated_and_disclosed`、`test_specialist_timeout_is_a_failed_report`、`test_failed_retry_keeps_earlier_valid_report`、`test_profile_correction_revokes_then_replaces_atomically` |
| 预算 | `harness/budget.py`：一次请求一个预算，编排者与专家共享；多 Agent 模式调用前按估算预占（准入控制），专家不能占用编排者保留额度；软上限语义见下文 | `test_budget_propagates_reserve_and_deadline`、`test_concurrent_specialists_cannot_spend_orchestrator_reserve`、`test_single_mode_keeps_week1_3_budget_semantics` |
| 请求墙钟 | 多 Agent 模式 `request_timeout_s` 约束整次请求：模型调用等待、专家执行与排队、异步工具执行；到期后返回的响应不执行工具 | `test_request_deadline_*`（3 项）、`test_response_after_deadline_runs_no_tools`、`test_cancelled_request_closes_queued_and_running_specialists` |
| 嵌套 trace | trace 增加 `parent_call_id`；子会话创建即记 `session_started`，结束（含超时、取消）记 `session_finished`；父会话记录 `specialist_queued/started/finished`；`scripts/trace_tree.py` 重建调用树并检查完整性 | 全链路测试中调用树无问题；首次响应前超时、请求取消时调用树仍完整 |
| 单 Agent 对照基线 | `mode: single` 时代码路径与前三周一致 | 原有 257 项测试在本环境的结果与 main 相同 |
| 审核 trajectory.yaml | 已做结构一致性审核，结果见下文；**人工审核未完成** | 0 处结构不一致 |

## 关键设计

1. **子问题不当作用户原话。** 编排者写的子问题只进入子会话的模型上下文。用户原话从父会话复制，只供出生资料、性别和口径的核验使用（`run_turn(..., as_evidence=False)`）。测试中编排者在子问题里编造出生时间，专家排盘被核验拒绝。把这一条改回"计入原话"后，该测试失败。
2. **追问上抛，合并成一次。** 专家没有 `ask_user`。子会话内任何工具返回 `needs_input`，harness 立即结束该子会话，报告 `status=needs_input`，由编排者合并成一次追问。`needs_input` 报告从不缓存；成功报告的缓存键包含用户消息条数和画像版本，所以用户补充资料后会重新咨询。
3. **结果并回父记录，业务库只由编排者写。** 成功专家的信号、引用、计算结果、chart_id、bazi_id、牌面和时间范围，按调用顺序并入父记录，并检查时间范围是否冲突。因此前三周的提交校验、事实校验、`save_reading` 和读取原记录的追问都没改。业务记录和 `specialist_reports` 在同一事务里写入；报告只存信号引用编号，信号本身仍在 `readings.signals_json`。
4. **塔罗每个记录只抽一次。** 塔罗报告有效后，同一记录内再次咨询直接返回该报告；抽牌种子仍由父记录提供。抽牌一旦成功，牌面、牌阵和“已抽牌”标记立即留在父记录（`specialist_facts`），与报告是否成功无关；重试时专家从 `existing_results` 拿到已抽的牌，不能再抽，也不能换牌阵。
5. **同一步内的冲突。** 同一步重复咨询同一体系，返回 `duplicate_consult`。各专家时间范围不一致，返回 `timeframe_conflict`。时间范围还要经过和前三周相同的用户原话区间检查。
6. **追问不咨询专家。** 读取原记录进入追问模式后，`consult_specialist` 会被拒绝，追问用原记录和 `lookup_meaning` 回答。

## 与计划的差异

| 差异 | 原因与处理 |
|---|---|
| 专家 3 位而非 5 位 | 姓名、解梦插件在第 6 周；插件没有专家定义时启动即报错，加入时 harness 不需要改 |
| 专家会写排盘缓存表（charts、bazi_charts） | 这是按输入哈希的计算缓存，不是业务记录。所有写操作都在同一个事件循环线程、同一个 SQLite 连接里串行执行，没有写锁冲突。readings 和 specialist_reports 只由编排者写 |
| 默认模式仍是 single | 真实模型对照没有数据，暂不切换；`--mode multi` 或 `config.yaml` 可以开启 |
| 预算没有照搬计划（6 万 token、专家 30 秒） | 沿用前三周实测后的 180000 总预算；新增：每位专家 40000 token、120 秒、最多 6 步，编排者保留 30000 token，最多 3 位专家并发；多 Agent 模式整次请求墙钟上限 300 秒（单 Agent 模式不加墙钟上限，保持前三周行为）。这些是初值，需要真实运行后重新标定 |
| 预算是软上限 | 调用前只能按估算预占，模型实际用量要返回后才知道。估算 = 输入估计（首次按字符数/2，之后用上次实际输入 + 新增消息字符数/2）+ 2048 输出额度。实际超过估算的部分记 `budget_overrun` 事件，只有这部分超额可能挤占编排者保留额度；超额后不再执行该响应的工具。不能声称保留额度在任何情况下都绝对不被动用 |
| 审校 | 第 5 周；`reviewer.enabled` 仍必须为 false |

## 实际测试结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 全量 pytest（评审整改后） | 288 项：276 通过，1 失败，11 错误 | 12 项都需要 `data/ephe/de440s.bsp`：doctor 必需项 1 项、Skyfield 独立对照 11 项。本环境拒绝连接 ssd.jpl.nasa.gov；main `893c189` 在同一环境下也是这 12 项。远程 CI 会下载该文件 |
| 多 Agent 测试 | 31/31 | `tests/test_multi_agent.py` 17 项；`tests/test_multi_agent_review.py` 14 项（评审回归） |
| 原有测试 | 245 项在本环境可运行的全部通过 | 单 Agent 路径未回退 |
| 变异检查 | 12/12 被测试抓到 | 逐项回退评审修复，确认对应测试失败，见下文 |
| Ruff check / format | 通过 | |
| 离线 week1 流程（demo 模型） | single 12/12，multi 12/12；离线专家集合 F1 = 1.000 | 只是流程回放，不代表真实模型的路由能力 |
| 三体系标注路线回放（single） | 50/50，跳过 30 | 与前三周相同 |
| CLI | `cli.py draw --mode multi --provider demo` 正常提交，`scripts.trace_tree` 输出调用树、无问题 | |
| 真实模型 | **未验证** | 原因见上 |

脱敏证据在 [verification/week4](verification/week4/README.md)：`pytest.json` 列出每项测试状态和环境原因，`offline.json` 是离线评估汇总。

## PR #2 评审整改（第二轮）

评审针对 `ea35679` 提出 7 项 P2 边界问题，评审者均用合成资料和脚本化模型复现。逐项处理如下：

| # | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| 1 | 失败重试覆盖有效报告，但旧信号留在父记录，最终提交两种写法都被拒 | `agents/consult.py`：区分有效报告与咨询尝试（`specialist_attempts` 记录每次尝试）。重试失败时，若先前报告有效且画像版本未变，保留先前报告并标记 `retained_previous`；画像已更正则按体系撤销旧的信号、引用、计算事实和 chart/bazi/牌面。成功报告先撤销再并入，按体系原子替换（`specialist_contrib` 记录每个体系贡献了哪些状态）。`read_reading` 用该记录保存的专家报告重建状态，不带入当前记录的任何状态 | `test_failed_retry_keeps_earlier_valid_report`（先成功后失败仍能提交）、`test_profile_correction_revokes_then_replaces_atomically`（资料更正后失败撤销、成功替换）、`test_read_reading_restores_that_readings_specialist_state` |
| 2 | 并发预算无预占，专家耗掉编排者保留额度 | `harness/budget.py` 增加 `hold/release/admit/settle`：调用前按估算在各级预占，`remaining()` 扣除在途预占和祖先的保留额度；返回后按实际用量结算。软上限语义见“与计划的差异”。只在多 Agent 模式启用，单 Agent 模式与前三周相同 | `test_concurrent_specialists_cannot_spend_orchestrator_reserve`：评审参数（总 200、保留 60、专家 100、一步，专家实际各 80）下只准入 1 位专家，另 2 位 `budget_denied`；总用量 125 ≤ 200，编排者完成收尾轮。`test_single_mode_keeps_week1_3_budget_semantics` |
| 3 | `request_timeout_s` 只在轮间检查 | 模型调用用剩余时限包裹（`Budget.time_left()` 取整条预算链的最早截止）；响应到达时已过期则不执行工具，返回 `timeout`；`Runtime.turn` 在多 Agent 模式用 `asyncio.wait_for` 包住整次请求，覆盖专家排队和工具执行。并行调用改用 `asyncio.TaskGroup`，取消时等所有子调用收尾后才返回 | `test_request_deadline_stops_a_waiting_orchestrator`、`test_request_deadline_bounds_running_specialists`、`test_request_deadline_bounds_tool_execution`、`test_response_after_deadline_runs_no_tools`、`test_cancelled_request_closes_queued_and_running_specialists` |
| 4 | 抽牌成功但报告失败时丢失牌面，重试可换牌阵 | 子会话结束时无论报告是否成功，都把已完成的计算事实（牌面、牌阵、`tarot_drawn`、chart/bazi id）留在父记录 `specialist_facts`；重试时预置进新子会话，并在子问题 `existing_results` 中给出。已抽牌后换牌阵直接拒绝 | `test_draw_survives_a_failed_report_and_spread_stays_fixed`：同一记录只有 1 次 `draw_tarot`，改 three_card 被拒 |
| 5 | 首次响应前超时，调用树缺少子会话 | 子会话创建时即写 `session_started`；超时写子会话 `timeout`，结束（含取消）写 `session_finished`。`trace_tree` 检查每个子会话都有开始和结束事件；`live_week23` 多 Agent 模式把调用树完整性列为逐题检查和汇总指标 | `test_timeout_before_first_response_keeps_the_call_tree` |
| 6 | 最大并发数把排队算成执行 | 父会话分别记录 `specialist_queued`（排队）和 `specialist_started`（获得并发许可后）；并发度只统计 started→finished 区间，排队时间单独报告为 `queue_ms` | `test_queueing_is_not_counted_as_concurrency`：并发上限 1 时指标为 1，最后一位排队 ≥150 ms |
| 7 | 首次通过率实际是提交尝试通过率 | 按子会话取第一次 `submit_report`；另报修正后通过率和提交尝试通过率，口径见下 | `test_first_pass_rate_uses_each_consults_first_submission`：拒、拒、过 → 首次通过率 0%，修正后 100%，尝试通过率 1/3 |

### 多 Agent 指标口径（`scripts/trace_tree.specialist_metrics`）

- **报告合规率 `report_compliance_rate`（第 4 周 ≥98% 关口采用此口径）**：最终得到有效报告的咨询数 ÷（实际运行的咨询数 − `needs_input` 咨询数）。被请求取消的咨询不计入；`needs_input` 是正当的补充资料请求，不计入分母；失败咨询（包括从未提交报告的）计入分母、不计入分子。
- **首次通过率 `report_first_pass_rate`**：第一次 `submit_report` 即通过校验的咨询数 ÷ 至少提交过一次的咨询数。
- **修正后通过率 `report_corrected_pass_rate`**：至少有一次提交通过的咨询数 ÷ 至少提交过一次的咨询数。
- **提交尝试通过率 `submit_attempt_pass_rate`**：通过的提交次数 ÷ 全部提交次数。
- 从未提交报告的咨询单独计为 `consults_without_submission`，只影响合规率。
- **实际并发 `max_concurrent_specialists`**：只统计获得并发许可后的执行区间；排队时间列在 `queue_ms`。

## 首次失败与修复记录

- **新增多 Agent 测试首次运行：17/17 通过。** 为排除"测试太弱所以通过"，做了两项变异检查，检查后已恢复原代码：
  - 把子问题改为计入用户原话：`test_brief_is_context_not_user_evidence` 失败；
  - 把专家并发上限改为 1（串行）：`test_parallel_consult_merges_persists_and_traces` 失败。
- **首次全量回归**：262 通过，12 项失败或错误，全部是 JPL 文件缺失，与 main 在同一环境的结果一致，不是产品缺陷。
- **提交前复查发现的问题**：新增的整次请求墙钟上限（300 秒）原本也作用于单 Agent 模式。前三周有单 Agent 回答接近这个时长，会改变已验收的行为。已改为只在多 Agent 模式生效，并新增第 18 项测试 `test_single_mode_has_no_wall_clock_deadline`；修正后全量复测为 275 项中 263 项通过，其余 12 项仍是 JPL 文件缺失。
- **开发中自查后修改的问题**（都在首次测试运行前，所以没有失败记录可保留）：
  - 并行结果原先按调用 id 对应，模型给出重复 id 时会串位，已改成按位置对应；
  - demo 模型重构时有一处收尾语法错误，运行前已修正。
- **评审整改轮（第二轮）**：
  - 新增 11 项评审回归测试和原 17 项多 Agent 测试首次运行 28/28 通过。
  - 首次全量回归：原测试 `test_reserve_keeps_budget_for_orchestrator` 失败。它用极小预算（几十 token）验证保留额度，假定预算在返回后才扣减；准入控制下首次调用的估算就超过这个预算，调用被拒。该测试验证的正是评审第 2 项指出的旧语义，已删除，由按评审参数构造的 `test_concurrent_specialists_cannot_spend_orchestrator_reserve` 替代（用固定估算隔离估算函数）。
  - 第一轮变异检查 9 项中 1 项未被抓到：去掉 `Runtime.turn` 的整次请求 `wait_for` 后，两项墙钟测试仍通过，因为循环内的剩余时限已覆盖模型调用。补充 `test_request_deadline_bounds_tool_execution`（工具执行超过时限），之后该变异被抓到。
  - 复查发现：准入估算原本对单 Agent 模式也生效，会让接近预算的第一至三周回答提前停止，改变已验收行为。改为只在多 Agent 模式生效，补充 `test_single_mode_keeps_week1_3_budget_semantics`；两项相关变异均被抓到。
  - 新增 `test_cancelled_request_closes_queued_and_running_specialists` 首次运行失败：取消请求后只记录到 2 个 `specialist_finished`。原因是 `asyncio.gather` 在第一个子任务被取消时就结束，不等其它子任务收尾，正在运行的专家在请求返回后才写结束事件。改用 `asyncio.TaskGroup` 后通过；所有时限相关测试连续 5 次运行稳定。
  - 变异检查（检查后均已恢复）共 12 项，全部被对应测试抓到：保留先前报告、画像版本撤销、多 Agent 准入、专家准入、单 Agent 不估算、整次请求 `wait_for`、到期响应不执行工具、保留抽牌事实、子会话开始事件、按排队统计并发、按尝试统计首次通过率，以及 `gather` 替代 `TaskGroup`（即上一条的首次失败）。
- **真实模型首次尝试**：`scripts.check_model` 和 `scripts.live_week23 --mode multi --cases bazi_trait --no-judge` 都因缺少 `OPENAI_API_KEY` 退出。没有发出请求，也没有产生用量。

## 真实模型测试（未验证，需在有密钥的环境运行）

```powershell
$env:PYTHONUTF8 = '1'
uv run python -m scripts.check_model
uv run python -m scripts.live_v2_review --suite baseline --mode single --output reports/week4/live-single
uv run python -m scripts.live_v2_review --suite baseline --mode multi --output reports/week4/live-multi
```

- 两次运行使用同一套 20 题和评分标准，串行执行。
- 多 Agent 模式的结果额外包含 `multi_agent` 指标：专家越权尝试数与比例、报告合规率、首次通过率、修正后通过率、提交尝试通过率、成功/追问/失败/取消报告数、实际最大并发专家数、调用树完整性（口径见上文）。
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

1. 真实模型的单、多 Agent 20 题对照（同一源码提交、同一套题，保留逐题质量、严格通过率、时延、全部角色 token 和原始失败），以及真实时延与 token 数据。
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
| 多 Agent 20 题全部执行，零越权，报告合规率 ≥ 98%，调用树完整 | 离线满足；口径已固定（见“多 Agent 指标口径”）；真实模型未验证 |
| PR #2 评审 7 项边界问题 | 已修复，均有回归测试和变异检查；待评审复核 |
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
