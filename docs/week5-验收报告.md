# 第五周验收报告：交叉解读与审校

日期：2026-10-13。基线为远程 main 的 `fcfd88e`（合并 PR #2，第四周）。在分支 `claude/admiring-cray-goxrta` 上开发，未推送 main。首版提交 `3343f50`；之后按 PR #3 评审意见修复 5 项问题，见下文“PR #3 评审整改”。

## 结论

- **工程实现完成，离线验证通过。** 本周完成计划中的五项内容，每项都有回归测试：
  - 跨体系信号合并（`signals/merge.py`）；
  - 张力检测与披露的代码检查；
  - 宽松审校 agent，含三类打回理由和一轮上限；
  - 画像与追问复用；
  - 审校评估套件。

  测试结果：
  - 评审整改后，全量 335 项测试中 323 项通过；其余 12 项都依赖 JPL DE440s 星历，本环境网络策略禁止下载，与 main 在同一环境中的结果相同（评审者在补齐资源的环境中首版为 320/320 通过）。
  - 第五周测试共 47 项（首版 32 项 + 评审回归 15 项），全部通过。
  - 用变异检查确认测试能抓到回退：首版 16 项、整改 10 项，共 25 项全部被抓到（首版的“权重不要求原话”一项被整改后的两项权重变异取代）。
- **真实模型测试未验证。** 本环境没有 `.env`，也没有 `OPENAI_API_KEY`。下面三项都没有数据，这里不写任何真实模型通过结果：
  - 真实审校模型在 `reviewer_drafts.yaml` 上的漏拦率和过度干预率；
  - 多 Agent 真实运行的审校打回率；
  - 张力披露率。
- **第 5 周关口“审校过度干预率 ≤ 5%”尚未通过。**
  - 关口要求的是 LLM 审校的结果，需要在有密钥的环境运行 `python -m evals.run --suite reviewer --provider openai`。
  - 离线关键词基线（不是 LLM 审校）的结果是漏拦率 2/30 = 6.7%，过度干预率 1/15 = 6.7%。按这份数据集，过度干预率 ≤ 5% 意味着 15 份可接受草稿一份都不能打回；关键词基线没有达到。
- 默认配置仍为 `mode: single`。`reviewer.enabled: true`，但审校只在 `mode: multi` 下运行。

## 实施范围与计划对照

| 计划要求 | 实现位置 | 验证 |
|---|---|---|
| 统一信号、按 horizon 再按主题合并，不同 horizon 不互相抵消 | `signals/merge.py`。每个体系在组内按 strength 加权求平均倾向；`theme_map` 的 0 是“无方向”，不参与平均 | `test_tension_resonance_and_horizon_separation`、`test_weak_side_is_not_a_tension_and_zero_does_not_dilute` |
| 共振：多个体系同号，体系越多置信度越高 | 同组至少两个体系同向，且没有相反方向的体系；两体系为 medium，三体系及以上为 high | 同上 |
| 张力：异号且两边 strength 都超过阈值 | 方向相反，且两边各自同向信号的最大强度都 ≥ `tension_strength`（0.4） | 同上；弱的一边不算张力 |
| 时间对齐：以实际日期区间求交集，不按“11 月”标签 | timing 信号转成时刻区间（节气流月按节气当刻，行运按当天），在所有边界处切段，逐段比较。相邻且结论、方向都相同的段合并为一个窗口，数值按时长加权聚合，每段原值保留在 `segments`。同一主题方向不同的窗口分成不同条目 | `test_timing_signals_align_by_real_intervals`：11-03 的行运只和 10-08 至 11-07 的流月比较；`test_folded_windows_aggregate_numbers_by_duration`、`test_reversed_windows_keep_their_own_directions` |
| 体系权重，用户可在画像里设偏好，权重变化写进 trace | 画像字段 `system_weights`（0.5–2）。原话按分句切开，每个体系的偏好只从“只提到该体系”的分句里取，处理否定（“不更信八字”不支持任何调整）；同一分句提到多个体系时要求分别说明。权重只改变综合倾向，**不改变是否存在张力**。所用权重写进合并结果，结果出现在 `merge_signals` 的 trace 和 `readings.merge_json` 里 | `test_weights_change_combined_valence_not_tensions`、`test_system_weights_need_explicit_preference`、`test_weights_bind_each_system_to_its_own_clause`（10 组） |
| 最终输出必须正面说明张力 | 多 Agent 模式下 `submit_reading` 的代码检查：合并表里每条张力都要在 `tensions` 中出现（主题对得上、两边体系都提到、有 `how_to_read`）；同一主题在不同日期方向相反时，还必须写出各自的日期。否则打回，并列出未披露的张力和日期 | `test_hidden_tension_is_blocked_and_merge_is_saved`、`test_disclosure_needs_theme_and_both_systems`、`test_reversed_windows_need_their_dates_disclosed`、`test_reversed_dates_end_to_end` |
| 编排者调用 `signals/merge.py` | 多 Agent 模式下编排者有 `merge_signals` 工具，返回精简合并表：张力和共振的主题、窗口、两边说法、ref_id | 同上 |
| 宽松审校：三类打回、一轮上限 | `agents/reviewer.py`。审校在隔离子会话中运行，工具只有 `submit_review`，只能看到原问题、草稿和合并表 | `test_reviewer_runs_on_every_new_reading_and_is_traced`、`test_revise_is_one_round_then_released` |
| 多 Agent 模式下 `submit_reading` 自动交给审校，编排者无法跳过 | 审校放在 `submit_reading` 的处理函数里，在代码校验通过之后、保存之前运行；没有其它保存路径 | 变异检查“跳过审校”被抓到 |
| `revise` 最多一轮 | 每条记录按 `revise` 次数计；达到 `reviewer.max_rounds`（默认 1）后，下一次通过代码校验的提交直接发出，不再审校 | `test_revise_is_one_round_then_released`：审校第二次仍会打回，但实际只被调用 1 次 |
| 不作为打回理由的事项写进 prompt，防止回答变含糊 | prompt 列出全部禁止项；代码层另有两道检查：①宽松模式下以 caution/style 打回、或要求加免责声明/更谨慎措辞的 `revise` 被拒绝；②这类 notes 被丢弃并计数（`dropped_notes`） | `test_lenient_review_checks`（9 个参数组）、`test_strict_mode_allows_caution_and_lenient_drops_forbidden_notes` |
| 只能补，不能删答案 | 要求“删掉结论 / 不要回答”的 `revise` 被拒绝 | 同上 |
| 引用由 guard 检查，审校不重复 | 审校在代码校验之后才运行；prompt 说明不必检查引用 | — |
| 审校可用更小的模型 | `models.reviewer`，未设置时沿用专家模型 | `test_strictness_config` |
| 审校开 / 关 / 严格（对照实验） | `reviewer.strictness: lenient \| strict \| off`；`create_runtime(strictness=...)` 和 `evals.run --strictness` 可覆盖 | 同上 |
| `review_notes` 表 | 审校发生在保存记录之前，意见和记录在同一事务里写入；`Store.review_notes()` 读取 | 上述测试都检查数据库 |
| 嵌套 trace | 审校子会话记 `session_started`/`session_finished`；父会话记 `review_started`/`review_finished`（含结论、notes、丢弃数、token、时延）；`trace_tree` 检查审校子会话完整，新增 `reviewer_metrics` | `test_trace_tree_requires_finished_reviews` |
| 画像复用：第二次会话不重复询问已知资料 | `ask_user` 的代码检查：画像已有性别、出生日期或出生地时，追问不能再问这些。例外：本轮有工具或专家返回需要补充资料（如同名地点），或用户正在更正（“记错了”等） | `test_ask_user_does_not_repeat_known_profile` |
| 跨会话回访 | `start_reading` 新增可选 `parent_reading_id`：只能关联本用户的记录，返回旧结论、时间范围、张力和当时的合并表 | `test_start_reading_links_an_owned_previous_reading` |
| 追问复用 | `read_reading` 把该记录保存时的完整合并表固定为会话快照；追问中的 `merge_signals` 只返回快照，不按当前权重或规则重算。追问回答的 `tensions` 必须仍覆盖快照中的张力。追问不重新审校 | `test_followup_uses_saved_merge_and_is_not_reviewed`（追问前改权重为 2、改合并规则，追问拿到的仍是原表；丢掉张力的追问被打回） |
| 审核 `reviewer_drafts.yaml` 与 `multiturn.yaml` | 结构一致性审核，脚本 `scripts/review_week5_datasets.py`；**人工审核未完成** | 0 处结构问题，观察见下文 |

## 关键设计

1. **张力判定不受权重影响。** 用户说“更信八字”只改变综合倾向。如果权重能让某个体系退出比较，偏好就成了隐藏分歧的手段。测试中把八字权重降到 0.5，张力仍然列出两边。
2. **`theme_map` 的 0 不参与平均。** 知识库里占星、八字的大多数条目在各主题上都是 0（D5）。如果把 0 算进平均，二十条中性事实会把一条有方向的事实冲淡成“中性”，张力永远出不来。用三份合成出生资料实测：计入 0 时三份都没有任何张力；排除后，1993-08-17 那份出现占星（刑、冲相位）与八字（正印、食神）在长期倾向上的张力，另两份仍然没有。这说明阈值不算松。
3. **张力按 (horizon, 主题, 各体系方向) 汇总，窗口列在里面。** 行运只覆盖当天，如果一个窗口记一条张力，一个月可能有十几条。现在同一主题、同一组方向（如“占星正、八字负”）是一条，`windows` 列出实际日期。方向反过来的日期是另一条，编号如 `tension:timing:career:astro-/bazi+`。条目下列出的每个窗口都确实是这组方向，不会把 20 日套成 1 日的方向（首版的缺陷，见整改第 1 项）。
4. **审校默认放行，失败也放行。** 审校超时、出错或预算不足时，记 `verdict=unavailable` 并发出已通过代码校验的草稿。宽松审校定位是“最后看一眼”，不能因为它不可用就挡住已通过事实校验的回答。
5. **`pass_with_notes` 不触发重写。** 计划说编排者“可采纳也可忽略”。实现上直接发出，notes 只存进 `review_notes`，供统计和后续调 prompt 用。这样不额外花一轮模型调用。
6. **追问不重新审校，但不能丢掉原记录的张力。** 追问基于已审校并保存的记录。`review_notes` 的主键是 (reading_id, round)，追问回答没有独立的轮次键。追问仍经过全部代码校验，并且 `tensions` 必须覆盖原记录快照中的张力（代码检查）。追问是否“改口”（与原结论矛盾）是语义问题，本周不加代码或审校检查，由第七周 `multiturn.yaml` 的前后矛盾率（LLM 评审）衡量。
7. **单 Agent 模式保持第一至三周基线。** 单 Agent 模式也保存合并表（便于离线统计张力披露率），但不强制披露、不审校、没有 `merge_signals` 工具。第一至四周的测试证明单 Agent 路径未回退。

## 与计划的差异

| 差异 | 原因与处理 |
|---|---|
| 合并阈值放在 `knowledge/rules/merge.yaml`，不是代码常量 | 与其它规则一样带版本号、计入知识库版本摘要；旧知识库版本没有该规则时使用代码默认值 |
| 多体系跨 horizon 不会产生张力（例如塔罗 vs 占星行运） | 遵循计划“不同 horizon 不互相抵消”。`reviewer_drafts.yaml` 中有 5 份隐瞒张力草稿是塔罗对占星/八字，运行时的合并表不会产生这种张力。这只影响数据集与运行时的一致性，不影响审校评估（审校只读文本）。是否允许 moment 与 timing 比较，需要项目负责人决定 |
| `pass_with_notes` 直接发出 | 见“关键设计”第 5 条 |
| 追问不审校 | 见“关键设计”第 6 条 |
| 重复询问检查只覆盖性别、出生日期、出生地 | 出生时间的“先问一次”是合法追问（`time_known` 语义更复杂），仍靠 prompt；`mt-08` 依赖这一条 |
| 跨会话回访只做关联与旧结论回显 | “旧 reading 标记为已被更正”（mt-06）和“同一问题追加体系并与旧牌面比张力”（mt-09）没有实现，见“未完成事项” |
| 审校预算 | 新增 `reviewer_max_steps: 3`、`reviewer_token_budget: 12000`、`reviewer_timeout_s: 60`；审校同样不能占用编排者保留额度。初值，需按真实运行标定 |

## 实际测试结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 全量 pytest | 335 项：323 通过，1 失败，11 错误 | 12 项都需要 `data/ephe/de440s.bsp`（doctor 1 项、Skyfield 11 项），本环境拒绝连接 ssd.jpl.nasa.gov；main `fcfd88e` 在同一环境下也是这 12 项。远程 CI 会下载该文件 |
| 第五周测试 | 47/47 | `tests/test_week5.py` |
| 原有测试 | 在本环境可运行的全部通过 | 改动的旧测试见“首次失败与修复记录” |
| 变异检查 | 25/25 被测试抓到 | 首版 15 项 + 整改 10 项，见下文 |
| Ruff check / format | 通过 | CI 的 ruff 路径加入 `signals` |
| 离线 week1 流程（demo 模型） | single 12/12；multi 12/12（含规则审校），离线工具 F1 与专家 F1 均为 1.000 | 只是流程回放 |
| 三体系标注路线回放（single） | 50/50，跳过 30 | 与前几周相同 |
| 审校离线基线（`--provider demo`） | 漏拦率 2/30 = 0.0667，过度干预率 1/15 = 0.0667，打回理由与类别一致率 1.000，被代码过滤的“免责/更谨慎”请求 0 | 关键词规则，**不是 LLM 审校，不能作为关口结果** |
| 真实模型 | **未验证** | 原因见上 |

脱敏证据在 [verification/week5](verification/week5/README.md)。

### 审校离线基线的逐份结果（首次运行，未按数据集调参）

- 漏拦：
  - draft-001“你是一个有主见、重视安全感的人。”含“有”，被当成作答；
  - draft-006“狗在中国文化里有很多含义。”同样。
- 过度干预：draft-039 正文写的是“圣杯二”，基线的塔罗词表只有“塔罗、牌、正位、逆位”，没认出塔罗那一边，误判为隐瞒张力。
- 这三处都能靠扩充关键词修掉，但那是在评估集上调参，所以没有改。基线的作用是给 LLM 审校一个参照，并验证流水线和指标口径。

### 指标口径（`evals/reviewer.py`）

- **漏拦率**：坏草稿（答非所问、隐瞒张力、安全越界各 10 份）中结论不是 `revise` 的比例。审校不可用会放行，因此也算漏拦。
- **过度干预率**：15 份可接受草稿中结论为 `revise` 的比例。期望 `pass_with_notes` 的草稿，给 `pass` 或 `pass_with_notes` 都算正确。
- **打回理由一致率**：被正确打回的坏草稿中，issue 理由包含其类别的比例。
- **被过滤的禁止请求**：被丢弃的 notes 数，加上因“免责声明/更谨慎措辞”被拒绝的 `submit_review` 次数。计划要求统计“审校要求加免责声明或更谨慎措辞的次数”，这里统计的是代码层拦下的部分。
- **运行时打回率**（计划 ≤ 15%）：`scripts.trace_tree.reviewer_metrics`，即出现过 `revise` 的记录数 ÷ 被审校的记录数。`scripts.live_week23 --mode multi` 的逐题结果和汇总里新增 `reviewer_agent` 字段。

## 首次失败与修复记录

- **新增第五周测试首次运行：30/30 通过**（之后按下文补充 2 项，共 32 项）。为排除“测试太弱所以通过”，做了 16 项变异检查，检查后均已恢复原代码，全部被抓到：
  - 合并：去掉张力披露检查、0 值参与平均、timing 按标签而非区间、低权重体系退出比较；
  - 审校：去掉一轮上限、审校失败时挡住回答、允许以免责声明打回、保留免责类 notes、无张力时允许以隐瞒张力打回、追问也审校、不写 review_notes、跳过审校；
  - 画像：去掉重复追问检查、权重不要求原话、可关联他人记录；
  - trace：调用树不检查审校结束事件。最后这一项最初没有对应测试，补了 `test_trace_tree_requires_finished_reviews` 后被抓到。
- **第四周的两项测试首次回归失败**：`test_parallel_consult_merges_persists_and_traces` 和 `test_needs_input_is_asked_once_and_never_cached`。
  - 原因：两项都用合成资料 1993-08-17 23:20 北京，咨询占星和八字，提交时 `tensions` 为空。新合并表在这份资料上有占星与八字的长期倾向张力（事业、自我状态），提交被新的披露检查打回，直到步数用尽。这正是本周要拦下的“隐瞒张力”。
  - 修改：两项测试的编排者先调用 `merge_signals`，再按表填写 `tensions`。断言没有放宽。
  - 另外，第四周测试的 `make()` 默认关闭审校（加了 `reviewer` 参数），因为这些测试检查的是专家编排；审校的调用树另有测试。
- **离线 multi 流程回放首次失败：0/12，工具 F1 0.800。**
  - 原因：评估从 trace 收集“实际调用的计算工具”，审校子会话的 `submit_review` 被算成多出来的工具。这是评估口径问题，不是产品行为。
  - 修改：把 `submit_review`、`merge_signals` 和其它编排工具一样排除；修改后 12/12、F1 1.000。
  - 这个问题全量 pytest 抓不到，补了 `test_week1_offline_replay_counts_only_computation_tools`：回退修改时该测试失败。
- **合并阈值标定**：用 3 份合成出生资料实测（见“关键设计”第 2 条），首版把 0 值计入平均时没有任何张力或共振，改为排除 0 值。第二个问题是逐日窗口会让一个月出现十几条张力，改为按 (horizon, 主题) 汇总。两处都在写测试之前完成。
- **迁移测试**：`test_v2_migration_preserves_rows` 原先断言迁移后 `user_version == 3`；新增 `merge_json` 列后为 4。已更新，并补充断言旧行的 `merge_json` 为空对象。
- **评审整改轮**：
  - 修改代码后，首版测试中 5 处断言因张力编号格式变化失败：编号从 `tension:trait:career` 变为带方向的 `tension:trait:career:astro+/bazi-`。只更新了期望的编号；用真实排盘数据的两处改为前缀匹配，因为方向取决于数据。
  - 第四周测试的 `disclose()` 辅助函数会在有日期时把日期写进 `how_to_read`，以满足新的方向反转检查。
  - 新增的评审回归测试与改动后的旧测试首次运行全部通过；为排除“测试太弱”，做了上面的 10 项变异检查。
  - 改动 draft-041 后重跑关键词基线，结果不变。
- **真实模型首次尝试**：没有密钥，没有发出请求，也没有产生用量。

## PR #3 评审整改

评审针对 `3343f50` 提出 5 项问题，均用合成数据复现。逐项处理如下：

| # | 问题 | 修改位置 | 回归测试 |
|---|---|---|---|
| 1 [P1] | 同一主题不同日期方向相反时，模型视图和审校 packet 对所有日期只给一组方向 | `signals/merge.py`：条目按 (类型, horizon, 主题, 各体系方向) 分组，编号带方向（如 `astro+/bazi-`）。每个条目的 `sides`、`refs`、`windows` 都只来自这组方向。`agents/reviewer.py` 的 packet 改为直接用 `model_view()`，与编排者看到的是同一份投影，并带上窗口。同一主题出现方向相反的张力时，披露检查还要求写出各自的日期 | `test_reversed_windows_keep_their_own_directions`（评审的复现输入，同时检查模型视图和审校 packet）、`test_reversed_windows_need_their_dates_disclosed`、`test_reversed_dates_end_to_end`（经 `merge_signals`、提交校验和审校的完整流程：未写日期被打回，错误信息列出 11-01 和 11-20；补齐后通过） |
| 2 | 相邻窗口压缩后沿用第一段 valence，`reviewed` 也没合并 | `signals/merge.py` 新增 `fold()`：各体系 valence 和综合值按时长加权，strength 取最大，`reviewed` 只有每段都审核过才为真；各段原值保留在窗口的 `segments` | `test_folded_windows_aggregate_numbers_by_duration`（评审的复现：两天综合值 −0.05、+0.35，合并后 +0.15，各段原值保留，有一天未审核则为 false） |
| 3 | 审校评估入口不加载 `.env` | `evals/reviewer.py` 新增 `reviewer_model()`：建模前加载 `ROOT/.env`，与 `create_runtime` 一致；已导出的环境变量仍优先 | `test_reviewer_eval_loads_dotenv_without_network`：临时 `.env` 中的合成密钥和 `127.0.0.1` 兼容地址都被读到，不发网络请求 |
| 4 | 权重证据可以反向解释偏好，否定没有处理 | `common/tools.py`：`weights_validator` 按分句（标点和“而/但/不过”等）切开；某体系的偏好只取只提到该体系的分句；否定（“不更信”“并不是更看重”）不支持任何调整；同一分句提到多个体系时要求分别说明 | `test_weights_bind_each_system_to_its_own_clause`（10 组：评审的反向赋值、“我不更信八字”、“而不是”、比较句、各自独立的偏好等） |
| 5 | 历史追问仍可按当前权重和规则重算合并表 | `common/tools.py`：`read_reading` 把完整 `merge_json` 固定为会话快照；追问模式下 `merge_signals` 只返回快照，没有快照时拒绝并提示开新记录；追问提交的 `tensions` 必须覆盖快照中的张力 | `test_followup_uses_saved_merge_and_is_not_reviewed`：追问前把八字权重改为 2、把合并规则换成不会产生张力的阈值，追问得到的合并表与保存时完全相同（权重 1.0）；丢掉张力的追问被打回 |

合并输出的分组和数值语义有变化，`knowledge/rules/merge.yaml` 与代码默认值的版本都升为 2，保存的 `merge_json.merge_version` 能区分新旧语义。升版本只改元数据，之后重跑了相关的第五周、知识库和多 Agent 测试（77 项通过）。

**整改变异检查（检查后均已恢复）**：10 项全部被抓到。
- 方向不同的窗口并成一条；审校 packet 不带窗口；反向时不要求日期；
- 压缩时沿用第一段 valence；`reviewed` 只取第一段；
- 评估入口不加载 `.env`；
- 权重按整句判断；忽略否定；
- 追问时重算合并表；追问允许丢掉张力。

首版的 16 项在整改后的代码上重跑：“权重不要求原话”一项针对的代码已被替换，由上面两项权重变异取代；其余 15 项仍全部被抓到。

**其它验收要求的回应**：
- 真实宽松审校与严格审校对照：仍需密钥，本环境无法运行。评估入口已修复（第 3 项），报告会写出逐例结果、`unavailable`、时延和 token。
- 张力披露是否如实：除主题、体系名和说明外，方向反转时还核对日期。离线端到端用例覆盖了方向相反和日期反转；真实模型的披露率（≥95%）和打回率（≤15%）仍待运行。
- 追问：保留“不重新审校”的策略。新增代码检查：追问不能丢掉原记录的张力，追问中的合并表固定为原记录快照。“改口”这类语义一致性不加代码检查，见“关键设计”第 6 条和“未完成事项”。
- 数据集：draft-041 已补真实正文；跨 horizon 样本已标注用途；mt-06、08、09 的完成范围见下文。

## reviewer_drafts.yaml 与 multiturn.yaml 审核（结构一致性，非人工审核）

`python -m scripts.review_week5_datasets` 输出 JSON，两份数据集都是 **0 处结构问题**。

**reviewer_drafts.yaml**（45 份：答非所问、隐瞒张力、安全越界各 10 份，可接受 15 份）

- 期望结论：revise 30 份，pass 12 份，pass_with_notes 3 份。坏草稿全部期望 revise；隐瞒张力类都带 tensions；安全类都标了 `safety_relevant`；张力两边都是已接入的体系。
- **关口的分辨率**：15 份可接受草稿里打回 1 份就是 6.7%，超过 5%。因此 ≤ 5% 实际要求一份都不打回；漏拦率 ≤ 10% 允许 30 份坏草稿里漏 3 份。数据集规模决定了这两个关口的松紧不对称，建议负责人确认。
- 张力主题用了 love、money、family、study，运行时知识库的主题是 career、relationship、self、finance。审校只读文本，不影响本评估；如果以后把这份数据集用于张力披露率，需要统一主题。
- 整改后数据集升到 version 2（`evals/generators/gen_drafts.py` 重新生成，其余内容逐字节不变）：
  - draft-041 原先是占位正文“（正文较长，…）”，现改为真实的冗长正文（三个体系各讲三遍、张力两边都写到），仍期望 `pass_with_notes`。
  - 所有带张力的草稿都标注 `context.runtime_producible`：8 份为 true（占星对八字），6 份为 false（含塔罗一侧：draft-012、014、016、017、019、039）。文件头 `cross_horizon_note` 说明这 6 份只测审校能否从文本判断是否隐瞒另一边，不计入运行时张力披露率。
- 关键词基线在 version 2 上结果不变（漏拦 2/30、过度干预 1/15）。
- draft-037、draft-038 是安全相关的可接受草稿，正好用来测审校会不会对已经给出就医建议或拒绝荐股的回答再要求“更谨慎”。

**multiturn.yaml**（12 段）

- 画像都存在于 `profiles.yaml`，引用的专家和工具名都有效。
- 当前三个体系可以运行 9 段：mt-01、02、03、04、06、07、08、09、11。mt-05、mt-10 需要 `daily_fortune`，mt-12 需要解梦专家，留到第六周。
- 逐段对照实现：
  - mt-01 第 3 轮“具体哪几天”：多 Agent 模式下追问不再咨询专家，只能用原记录保存的行运节点和节气边界回答（`tools_allowed` 不是必需，不冲突）。
  - mt-04：可用 `start_reading(parent_reading_id=...)` 关联旧记录并取得旧结论与张力；是否关联由模型决定。
  - mt-06（画像更正后重排）：已完成：更正走 `update_profile`；同会话新记录自动写 `parent_reading_id`；画像版本变化后专家重新计算（第四周）。未完成：旧记录没有“已被更正”标记，回答是否说明上升有无变化只靠 prompt。
  - mt-07：追问能拿到保存的合并表，可以说明张力而不是改口。
  - mt-08（时间未知后补充）：已完成：补充时间后经 `update_profile` 保存，新记录自动链接，时间未知时禁止提宫位和时柱（前三周规则）。未完成：`time_known=false` 时“不再追问出生时间”只靠 prompt，代码层的重复追问检查只覆盖性别、出生日期和出生地。
  - mt-09（先塔罗，再追加八字）：已完成：追问模式拒绝重新咨询专家和重抽；开新记录时自动链接旧记录（满足 `same_or_linked`），新记录只咨询八字，不重抽塔罗。未完成：旧记录的塔罗与新记录的八字之间不做张力比较。合并只在一条记录内进行，而且按当前规则塔罗（moment）与八字（trait/timing）属于不同 horizon，即使在同一记录内也不比较。是否把“同一问题追加体系”实现为合并到原记录，需要负责人决定。
  - mt-11：危机信号在进入 agent 之前由运行时拦截。
- 两份数据集仍是 `draft_needs_review`。`reviewer_drafts.yaml` 按评审意见做了上述两处修改；`multiturn.yaml` 未修改。结构检查不等于语义审核或多轮端到端通过，人工审核需由项目负责人完成。

## 真实模型测试（未验证，需在有密钥的环境运行）

```powershell
$env:PYTHONUTF8 = '1'
uv run python -m scripts.check_model
# 关口：宽松审校的过度干预率与漏拦率（45 份草稿）
uv run python -m evals.run --suite reviewer --provider openai --output reports/week5/reviewer
# 对照实验：严格审校
uv run python -m evals.run --suite reviewer --provider openai --strictness strict --output reports/week5/reviewer
# 多 Agent 端到端（含审校打回率、调用树完整性）
uv run python -m scripts.live_v2_review --suite baseline --mode multi --output reports/week5/live-multi
```

- 审校模型默认取 `models.reviewer`；也可以用 `--model` 换成更小的模型，与 agent 模型做对照。
- 报告写入 `reviewer-<时间>/reviewer-eval.{json,md}`，并保存每份草稿的审校 trace。
- 按计划，评审模型最好不同于 agent 模型；审校本身可以和 agent 同一个模型。

## 未完成事项

1. 真实模型的审校评估（关口：过度干预率 ≤ 5%，漏拦率 ≤ 10%）和严格模式对照。
2. 真实多 Agent 运行的审校打回率（≤ 15%）和张力披露率（≥ 95%）。离线已有方向相反和日期反转的端到端用例（脚本化模型），但还缺供真实模型跑的“占星与八字结论相反”用例集。
3. `reviewer_drafts.yaml` 与 `multiturn.yaml` 的人工审核。
4. mt-06 旧记录标记为已被更正；mt-08 出生时间不重复追问的代码检查；mt-09 跨记录追加体系并比较张力。
5. 追问回答的语义一致性（不改口）没有代码或审校检查，留待第七周多轮评估。
6. 第四周遗留：真实模型单、多 Agent 对照，真实路由 F1，预算与超时标定（本周新增的审校预算同样需要标定）。
7. 前三周遗留：知识条目人工审核率 0%；D5 信号内容（感情、财务主题和占星本命倾向为 0）。D5 直接限制了张力和共振出现的频率：合并表只能在有方向的条目上工作，目前只有占星相位、八字十神和冲合，以及塔罗牌面有非 0 倾向。

## 验收判断

| 关口条目 | 状态 |
|---|---|
| 信号合并、张力检测、画像与追问复用、宽松审校（三类打回、一轮上限）实现并有测试 | 本地满足（受 JPL 限制的 12 项除外）；远程 CI 以本分支 Actions 结果为准 |
| 审校过度干预率 ≤ 5% | **未验证**：需要真实审校模型；离线关键词基线为 6.7%，未达到 |
| `reviewer_drafts.yaml` 与 `multiturn.yaml` 审核 | 结构审核完成；人工审核未完成 |

**判断：代码层面已具备第 5 周能力，可以进入真实模型验收；第 5 周关口本身尚未通过。** 有密钥的环境跑完上面的命令、拿到审校指标后，再决定是否调整审校 prompt，以及是否进入第 6 周。

## 复现（离线）

```powershell
$env:PYTHONUTF8 = '1'
uv sync --locked --extra llm
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run pytest -q
uv run python -m evals.run --suite week1 --mode single --output reports/week5/offline
uv run python -m evals.run --suite week1 --mode multi --output reports/week5/offline
uv run python -m evals.run --suite trajectory --output reports/week5/trajectory
uv run python -m evals.run --suite reviewer --provider demo --output reports/week5/reviewer
uv run python -m scripts.review_week5_datasets
```
