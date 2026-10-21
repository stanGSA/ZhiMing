# 阶段 1 执行与验收（B1、B2、B3）

日期：2026-10-20（Asia/Shanghai）。基线：main `7d43641`（含阶段0 `753ac8f`、复核修复 `f8d52d2`、时区证据修复 `7d99c8d`）。任务编号与验收口径取自《项目完善计划书》第四节与 5.4；架构约束参照[《占卜Agent项目计划书》](../../占卜Agent项目计划书.md)。

**本次只完成第1、2步（B2 基础代码与审核脚本），不花钱、不改变条目内容。** 1171 条全部仍为 `draft`，人工审核率 0%，模型交叉审核率 0%；解读继续强制低置信度。第3–7步（塔罗试点、B1、B3、其余体系全量审核、关口汇总）依赖待确认的决策，尚未开始。

三个关口分开陈述：

| 关口 | 状态 |
| --- | --- |
| 代码满足阶段1 | 部分：B2 的状态字段、置信度映射、账本、代码检查、审核脚本与离线测试已完成；B1、B3 未开始 |
| 4.8 知识库关口 | **未运行，未通过**（没有任何真实审核批次） |
| 真实模型发布关口 | 不属于阶段1，仍未通过（阶段0：single、multi 严格综合各 2/20） |

## 任务来源

计划书正文按用户说明使用分支 `claude/dreamy-babbage-3s6h4x` 的 `docs/项目完善计划书.md`（提交 `6ca037d`）。本次在云端容器内执行，看不到 Windows 工作目录里未跟踪的根目录《项目完善计划书.md》，**无法确认两版是否有差异**；如本地版本不同，请以本地为准并告知差异。

## 逐项改动与验收（第1步：B2 基础代码）

| 编号 | 改动 | 位置 | 验收 |
| --- | --- | --- | --- |
| B2-1 | 条目审核三态 `review_status: draft / model_reviewed / human_reviewed`。源文件只写 `reviewed`（仍只表示人工审核），三态由构建推导；`Entry` 校验 `reviewed == (review_status == "human_reviewed")`，`model_reviewed` 必须带审核记录。源文件写 `review_status`/`model_review` 时构建失败 | `knowledge/schema.py`、`knowledge/review.py`、`knowledge/build.py` | `test_reviewed_means_human_review_only`、`test_sources_cannot_author_review_state` |
| B2-2 | 独立账本 `knowledge/reviews/<体系>.yaml`：每条记录按条目 id 与条目内容 SHA256（含 `theme_map` 数值）绑定，内容一改即回到 draft；记录须两家不同厂商、都判 `pass`。账本文件与条目 schema 标记参与版本摘要 | `knowledge/review.py`、`knowledge/build.py`、`knowledge/reviews/README.md` | `test_ledger_approval_gives_model_reviewed_and_human_rate_stays_zero`、`test_editing_an_entry_voids_its_approval`、`test_ledger_needs_two_vendors_that_both_pass` |
| B2-3 | `scripts/draft_*.py` 只写 `knowledge/sources`，不碰账本。`draft_week6.py`、`draft_week23.py` 重新生成的五个体系与现有源文件内容哈希逐条一致（daily 9、name 220、dream 358、astro 280、bazi 141），重跑不会冲掉审核记录；`draft_tarot.py` 在源文件已存在时拒绝覆盖 | — | `test_regenerated_drafts_keep_approvals`（daily）；其余四个体系为本次一次性逐条比对 |
| B2-4 | 旧版本快照兼容：`KnowledgeBase.lookup` 与解梦匹配器读到没有 `review_status` 的旧条目时按 `reviewed` 推导 | `knowledge/kb.py`、`plugins/dream/match.py` | `test_old_edition_without_review_fields_reads_as_draft` |
| B2-5 | `Signal.reviewed: bool` 改为 `review_status`，像 `legacy_horizon` 一样读取旧值（`reviewed: false → draft`，`true → human_reviewed`）；`readings.signals_json`、每日运势缓存与专家事实里的旧信号都能读 | `plugins/base.py` | `test_signal_reads_legacy_reviewed_values`、`test_saved_reading_with_legacy_signals_still_follows_up`、`test_daily_cache_from_before_stage1_is_reused` |
| B2-6 | 合并 `side()` 与 `fold()` 取最低级别（原为 `all(reviewed)`） | `signals/merge.py` | `test_merge_side_takes_the_lowest_level` |
| B2-7 | 置信度映射：draft → low，“释义未经审核”；model_reviewed → 上限 medium（**决策2待确认**，改一处常量），“释义经模型交叉审核，未经人工审核”；human_reviewed 不设上限。原逻辑是“reason 含‘审核’二字就不补说明”，会保留模型写的错误说法（如“释义已经人工审核”）；现在与级别不符的审核分句被删除并补上说明，与级别相符的原话保持不变 | `common/output_policy.py` | `test_confidence_cap_by_lowest_review_level`（9 例）、`test_model_reviewed_tarot_reading_states_model_review` |
| B2-8 | 各插件把条目级别传入释义与信号，复合条目取组件最低级别；工具结果保留 `reviewed`，新增 `review_status` | `plugins/context.py`、`plugins/*/tools.py`、`common/tools.py` | 同上，端到端使用演示模型与真实插件 |
| B2-9 | 覆盖率报告按体系统计三态数量与比例；`reviewed_rate`（人工审核率）只统计 `human_reviewed`；另报账本记录的 current/stale/orphan 数 | `knowledge/build.py`、`evals/run.py`、`evals/week6.py` | `test_build_coverage_and_repeatability`（原有）及上述账本测试 |
| B2-10 | 4.4 第1步代码检查：确定性说法（先去掉“不代表事件必然发生”“不表示现实事件必然发生”等否定式免责声明，再用回答层同一套否定判断）、塔罗正逆位同号；结果写入 `data/kb.checks.json`，不使构建失败。数值范围、id/key/同义词唯一性仍是构建硬错误 | `knowledge/checks.py`、`knowledge/build.py` | `test_code_checks_skip_negated_disclaimers_and_flag_claims`、`test_build_reports_checks_without_failing` |

现有 166 处“必然”全部是否定式免责声明。只用回答层的判断会误报 10 条（行星组件条目的“不表示现实事件必然发生”），加上免责声明模板后误报为 0。塔罗正逆位同主题都非零的 178 组中 17 组同号（7 张牌：倒吊人、死神、高塔各 3 个主题，权杖五、圣杯八、宝剑二、宝剑五各 2 个主题），列入检查报告。

## 逐项改动与验收（第2步：审核脚本，只用离线 Mock 测试）

| 编号 | 改动 | 验收 |
| --- | --- | --- |
| B2-11 | 角色模型配置 `RoleModelSpec`：厂商、协议（openai 兼容 / anthropic）、模型名、密钥环境变量名、base_url、temperature、max_tokens。`OpenAIModel`、`AnthropicModel` 增加对应的仅关键字参数，默认行为不变；Anthropic 无工具时不再发送空 `tools`。返回的模型名逐次记录（阶段2 C5 可复用） | `test_role_adapters_use_their_own_key_and_endpoint`；原有适配器与 DeepSeek 测试 |
| B2-12 | `config.yaml` 新增 `kb_review.roles`（reviewer_a、reviewer_b、reviser），**全部为 null，待决策1填写**；校验两家不同厂商、都不是运行时厂商（`llm.provider`），修改方不能与审核方同厂商 | `test_vendor_rules` |
| B2-13 | `scripts/model_review_kb.py`：`plan`（不调用模型、不写文件）、`run`、`merge`、`revise`、`apply`、`ledger` 六个子命令 | 见下 |
| B2-14 | 分批：按体系与条目类型，每批约10条；固定 JSON 输出；每次调用的结果原子写入运行目录，续跑跳过已完成调用 | `test_run_resumes_logs_errors_and_records_identity`、`test_interrupted_run_resumes_without_repeating_calls` |
| B2-15 | 盲审：每次调用只看到一个批次；请求里没有条目 id、版本号、审核状态、另一家结论或埋错标记；埋错副本与原条目从不同批；塔罗牌带另一方向释义作对照，牌位条目带牌阵定义 | `test_full_tarot_plan_is_blind_balanced_and_deterministic`、上一行测试检查请求体 |
| B2-16 | 埋错约10%（每个体系至少5条，否则 daily 只有1条无法算检出率），改法按 4.6：反转 `theme_map` 符号、交换正逆位文字、插入宿命化句子、插入医疗诊断式说法、换成另一条目的文字、解梦误命中同义词、十神/五行（占星为行星/星座）写错；按每条可用的改法均衡分配，种子固定 | 同上、`test_mutations_for_other_systems` |
| B2-17 | 指标：双模型通过率、埋错检出率（单家与合并，按改法分列）、同一模型两轮一致率、未改动条目上的 Cohen's kappa 与观察一致率；阈值固定在脚本里（95%、90%/80%、90%、0.6） | `test_cohen_kappa`、`test_merge_metrics_and_queue`、`test_metrics_rules_on_hand_written_verdicts` |
| B2-18 | 合并：两家在所有轮次都判 `pass` 且没有阻断性代码检查（确定性说法）才算通过；任一方 `revise`/`reject` 或缺任一轮结论都进入修改队列或“未完成”。塔罗同号不阻断，交给看得到对照的审核模型判断（见“需要决定”） | 同上 |
| B2-19 | 修改：第三方模型调用给出修改建议，校验主题与数值范围、确定性说法；`apply` 写回源文件（版本号加1，`reviewed` 保持 false），不写账本，必须新开批次让两家重审 | `test_revisions_are_proposals_that_need_a_new_review` |
| B2-20 | 账本：只有校准达标（埋错、重跑、kappa）的批次能写入；借用其他批次校准（`--calibrated-by`）的复审批次另须检出本批全部埋错（见 R4）；条目内容在批次之后变化的不写（记为 stale）；记录两家厂商、请求与返回的模型名、日期、报告路径 | `test_ledger_needs_calibration_and_current_content` |
| B2-21 | 存档到 `docs/verification/kb-model-review/<批次目录>/`：manifest（源文件 SHA256、条目内容哈希、知识库版本、git 提交与是否有未提交改动、脚本与 rubric 哈希、审核方设置但不含密钥与单价、种子）、输入、埋错清单、每次调用原始输出与 token/耗时/返回模型、合并结论、修改队列、`report.md`。服务错误、JSON 解析错误、中断与重试写入 `errors.jsonl`，不计入结论；SDK 错误只记类别与状态码。目录与 manifest 绑定，换计划必须换新目录 | `test_run_directory_is_bound_to_its_plan` 及上述测试 |

测试中的两家“服务”是 `httpx.MockTransport`：reviewer_a 走 OpenAI 兼容协议，reviewer_b 走 Anthropic 协议，返回与请求不同的模型名以验证身份记录；覆盖 JSON 解析失败后重试、HTTP 400 后续跑只补缺失调用、中途取消后不重复已完成调用。

## 复核修复（PR #15 审查 R1–R3，自查 R4–R5）

项目负责人审查 `a26741d` 时离线复现了三个 P2 问题，均在审核脚本内修复，各有回归测试：

| 编号 | 问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| R1 | `revise` 把校验失败的修改建议也存起来，续跑只看 id 是否存在，无效建议永远不会重新生成，`apply` 又排除它们，流程卡住 | 续跑只跳过有效建议；无效建议重新请求，旧的无效稿保留在 `previous_invalid` 里（含 token 记录） | `test_rerun_of_revise_asks_again_for_invalid_proposals_only` |
| R2 | `parse_verdicts` 接受 `verdict="pass"` 但 `issues` 非空的矛盾回复，合并只看结论，已报告问题的条目仍会写入账本 | 这种回复按解析失败处理并重试，不计入结论；一直矛盾时该调用保持未完成，批次不完整就不能写账本 | `test_pass_with_listed_issues_is_a_parse_error`、`test_a_reported_problem_never_becomes_an_approval` |
| R3 | `--only-ids` 只选一两条（或同类少量）条目时只有一批，排除原条目所在批次后没有可放埋错副本的批次，`min()` 抛 `ValueError` | 没有可放的批次时为埋错副本新建独立批次，仍保证副本不与原条目同批 | `test_small_re_review_gives_planted_copies_their_own_batch`（1、2、6 条） |

父提交对照：在 `a26741d` 的独立工作树中放入新测试文件，这 6 项全部失败（R3：`ValueError: min() arg is an empty sequence` ×3；R2：`DID NOT RAISE ValueError`，以及账本照常写入；R1：续跑没有发起任何修改调用）；修复后全部通过。

按同类问题自查后，又在 `cce95f3` 上复现两个问题，按项目负责人的决定（借用校准的批次须检出本批全部埋错）修复：

| 编号 | 问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| R4 | `--calibrated-by` 的复审批次完全借用主批次的校准，不看本批自己的埋错结果：两家漏掉本批全部埋错（检出率 0%）时仍写入了 2 条审核记录 | 借用校准时，本批每条埋错副本都要有两家结论，且至少一家没有判 pass（即本批没有任何埋错会被放行）；否则拒绝写账本。本批太少、不能单独校准，所以只要求全部检出，不套检出率阈值 | `test_borrowed_calibration_needs_every_planted_copy_flagged`（两家都检出、只一家检出：允许；两家都漏同一条、全部漏：拒绝） |
| R5 | 借用校准的批次一次调用都没完成时，`ledger` 取日期时对空列表调用 `min()` 崩溃；没有可批准条目时也会写出空账本文件，使知识库版本无谓变化 | 空批次在 R4 的检查里被明确拒绝；没有可批准条目的批次直接跳过，不写账本 | `test_ledger_refuses_an_empty_run_and_skips_one_with_nothing_approved` |

父提交对照：在 `cce95f3` 的独立工作树中运行这 5 项，3 项失败（R4 两例 `DID NOT RAISE ValueError`；R5 抛的是 `min() arg is an empty sequence` 而不是拒绝说明），另 2 项是允许写入的对照，在父提交上也通过；修复后 5 项全部通过。

## 对模型可见内容的影响

- 各插件工具结果的 `interpretations[].meaning`、`draw_tarot` 的 `cards[].meaning`、`lookup_meaning` 的 `entry` 新增 `review_status`（当前全部为 `"draft"`），保留 `reviewed: false`。`lookup_meaning` 不返回 `model_review`（审核方信息不给模型）。
- `Signal` 字段改名不进入模型上下文：塔罗与每日运势的工具结果原本就去掉 `signals`。
- `confidence.reason`：模型没写审核说明时，补充文字由“释义为未经人工审核的草稿”改为“释义未经审核”；模型写了与级别相符的说明（如提示词要求的“释义未人工审核”）时原样保留。
- **提示词未改。** 编排者提示词仍写“confidence写low，reason保存释义未人工审核这一事实”。条目变为 `model_reviewed` 之前（第3步之后）需要同步修改，否则 medium 上限不会生效、说明也会被代码替换；这一改动放进第二个 PR，并单列影响。

## 版本与兼容

- 知识库版本由 `v1-7c1ca12f408903ef`（main `7d43641`）变为 `v1-bad60f05683733cf`。源文件与规则字节均未改，变化只来自版本摘要中新增的条目 schema 标记 `entry-schema:2`：旧代码建出的同内容归档缺新字段，不能被新代码复用。`knowledge/reviews/` 目前只有 README（不参与摘要）。
- 旧 reading 继续按其保存的版本读取旧快照；旧快照、旧信号、旧每日缓存缺审核级别时都读作 draft。每日结果仍按日缓存、不随知识库版本重算。
- `build()` 新增可选参数 `reviews_dir`（默认 `knowledge/reviews`）；`tests/conftest.py`、`tests/test_kb.py`、`scripts/compare_layers.py` 复制并传入账本目录。`scripts/live_week5_postmerge.py` 的合成信号仍写 `reviewed=False`，经兼容读取为 draft，未修改。

## 更新的原有测试（逐个说明）

| 测试 | 改动 | 原因 |
| --- | --- | --- |
| `tests/test_tarot.py::test_signals_come_from_kb_and_are_immutable` | `s.reviewed is False` → `s.review_status == "draft"` | 字段改为三级 |
| `tests/test_week5.py::test_folded_windows_aggregate_numbers_by_duration` | `sides["astro"]["reviewed"] is False` → `review_status == "draft"` | 合并结果字段改为三级；该测试的合成信号仍用旧 `reviewed`，同时验证旧值兼容 |
| `tests/conftest.py`、`tests/test_kb.py` 的 `rebuild` | 复制并传入 `reviews` 目录 | 测试工程使用自己的账本副本，不读写仓库账本 |

没有因数值改变而更新的测试（本次不改条目数值）。

## 验证

命令均在 Linux、Python 3.11.17、`uv sync --locked --extra llm --extra web` 环境中运行。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 新增定向测试 | `uv run pytest -q tests/test_stage1_review.py tests/test_model_review_kb.py` | 29 + 25 = 54 通过（复核修复前为 29 + 14） |
| 相关原有测试 | `uv run pytest -q tests/test_kb.py tests/test_tarot.py tests/test_expression_policy.py tests/test_week5.py` | 98 通过 |
| 全量（单次） | `uv run --extra web pytest -q -p no:cacheprovider -rfE` | 738 项：726 通过，12 项缺 de440s.bsp |
| Lint | `uv run ruff check harness agents common plugins knowledge memory signals scripts tests app.py cli.py web.py evals` | 通过 |
| 格式 | `uv run ruff format --check`（范围同上） | 138 个文件已格式化 |
| 空白 | `git diff --check` | 通过 |
| 构建 | `uv run python -m knowledge.build` | 见下表 |
| 审核计划 | `uv run python -m scripts.model_review_kb plan --system tarot` | 见“塔罗试点计划” |

**全量单次运行**（`uv run --extra web pytest -q -p no:cacheprovider -rfE`，在含复核修复 R1–R5 的最终文件上运行）：收集 738 项，**726 通过、1 失败、11 错误**。这 12 项全部因为缺少 `de440s.bsp`（见“失败与限制”），其余全部通过；其中新增 54 项（`test_stage1_review.py` 29、`test_model_review_kb.py` 25）。之前的单次全量：`a26741d` 为 727 项、715 通过，`cce95f3` 为 733 项、721 通过，均同样 12 项缺数据；GitHub Actions 在 `a26741d` 与 `cce95f3` 上（含 de440s.bsp）Ubuntu 与 Windows 均通过。以上均为单次全量运行，不是多次运行去重合并。

**父提交对照。** 在 `7d43641` 的独立工作树中放入两份新测试文件：两份都在收集阶段失败（`ModuleNotFoundError: No module named 'knowledge.review'`），即新功能在父提交上不存在。B2-7 修正的错误说法保留问题在父提交上直接复现：`mark_unreviewed` 收到 `level=medium, reason="牌面清楚，释义已经人工审核，可以参考。"` 与草稿信号时，父提交输出 `low / 牌面清楚，释义已经人工审核，可以参考。`（错误说法保留）；修复后输出 `low / 牌面清楚，可以参考；释义未经审核。`。

### 构建覆盖率（三态）

`uv run python -m knowledge.build`，版本 `v1-bad60f05683733cf`：

| 体系 | 条目 | draft | model_reviewed | human_reviewed | 人工审核率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 塔罗 | 163 | 163 | 0 | 0 | 0% |
| 占星 | 280 | 280 | 0 | 0 | 0% |
| 八字 | 141 | 141 | 0 | 0 | 0% |
| 姓名 | 220 | 220 | 0 | 0 | 0% |
| 解梦 | 358 | 358 | 0 | 0 | 0% |
| 每日 | 9 | 9 | 0 | 0 | 0% |
| 合计 | 1171 | 1171 | 0 | 0 | 0% |

账本记录 current 0、stale 0、orphan 0；代码检查 17 条（全部为塔罗正逆位同号），确定性说法 0 条。

## 塔罗试点计划（第3步，未运行，等确认）

`plan --system tarot`（默认种子1、每批10条、埋错10%、两轮）：163 条 + 16 条埋错 = 179 项，17 批（卡牌16批、牌位1批）；每家 34 次调用。埋错：交换正逆位 4、反转符号 3、宿命化 3、医疗 3、换文字 3。粗估每家输入约 9.9 万 token、输出约 4.3 万 token（每个汉字约 1 token、每条输出约 120 token；以小批次实测为准）。其余体系粗估（每家，两轮）：

| 体系 | 条目 | 埋错 | 批次 | 调用/家 | 输入 token/家 | 输出 token/家 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 塔罗 | 163 | 16 | 17 | 34 | 98,822 | 42,960 |
| 占星 | 280 | 28 | 31 | 62 | 131,922 | 73,920 |
| 八字 | 141 | 14 | 17 | 34 | 69,356 | 37,200 |
| 姓名 | 220 | 22 | 25 | 50 | 130,772 | 58,080 |
| 解梦 | 358 | 36 | 37 | 74 | 184,752 | 94,560 |
| 每日 | 9 | 5 | 2 | 4 | 6,566 | 3,360 |

占星、八字、每日的数字是 B1、B3 改动前的估计，定稿后会变化。全部体系两家合计约 186 万 token，与计划书 4.9 的“一两百万”一致；修改与复审另计。

## 失败与限制

- **JPL `de440s.bsp` 被本环境网络策略拦截**（`ssd.jpl.nasa.gov` 与 `naif.jpl.nasa.gov` 均返回 403），与计划书 2.1 记录的情况相同。受影响的是 `tests/test_week23_calculations.py::test_independent_skyfield_all_planets` 的 11 个参考盘（收集为 ERROR）和 `tests/test_scripts.py::test_doctor_week1_required_checks`（doctor 把该文件列为必需）。这 12 项与本次改动无关，没有用跳过代替；GitHub Actions 会下载该文件，结果以 CI 为准。其余数据由 `scripts.fetch_data` 按清单核验 SHA256 后使用。
- **kappa 在通过率极高时不稳定。** 若两家对几乎所有未改动条目都判 `pass`，期望一致率接近 1，kappa 会很低或无法计算（脚本记为“无法计算”，关口按未达标处理），即使两家实际高度一致。报告同时给出观察一致率。是否调整口径需要项目负责人决定，脚本不擅自放宽。
- 模型只能审方向与相对大小，不能证明条目“正确”；结论只写“经模型交叉审核，未经人工审核”。
- `apply` 把修改写回 YAML 后，再运行对应的 `scripts/draft_*.py` 会还原文字；内容一变，审核记录自动失效（回到 draft），不会误留“已审核”。
- 本次没有在 Windows 上运行；仓库 CI 同时覆盖 Ubuntu 与 Windows。
