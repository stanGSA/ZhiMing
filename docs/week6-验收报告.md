# 第六周验收报告：姓名、解梦与每日运势

日期：2026-10-14（Asia/Shanghai）。基线为 main 的 `8a7d864`（合并 PR #4，第五周边界修复）。在分支 `claude/sharp-davinci-2edlt6` 上开发。

## 结论

- **计划中的两个关口离线通过。**
  - 笔画全对：`name_strokes.yaml` 200 字的默认写法和康熙笔画 200/200 一致，37 个公认姓氏笔画 37/37 一致。
  - 同日结果不变：同一用户同一天跨 10 个会话调用 `daily_fortune`，10 次结果逐字节相同（第 2 至 10 次读 `daily` 缓存）；同 seed 抽牌 100 次一致；不经缓存纯函数重算，结果与缓存相同。
- **工程实现完成，离线验证通过。**
  - 姓名五格插件：康熙笔画、五格与 81 数理、三才、复姓、写法歧义、八字五行对照。
  - 解梦插件：355 条意象及其同义词，匹配顺序为同义词 → 包含 → BM25；信号只进入 psyche。
  - 每日运势插件：在代码里组合占星、八字和塔罗，结果写入 `daily` 缓存。
  - 多 Agent 新增姓名、解梦两位专家；每日运势由编排者直接调用。
  - 知识库 1171 条，6 个分区覆盖率都是 100%。
  - 第六周数据集任务已处理：`name_strokes.yaml` 的 19 个歧义字已定稿，`dream_annotations.yaml` 已做结构审核（不是人工审核）。
- **测试结果。**
  - 全量 376 项测试中 364 项通过。其余 12 项都依赖 JPL DE440s 星历，本环境网络策略拦截了下载，与改动前基线在同一环境的结果相同（基线是 334 项通过，失败的也是这 12 项）。
  - 第六周新增 30 项测试，全部通过。
  - 变异检查：逐个改坏 20 处关键代码，每一处都会让测试失败。
  - 标注路线回放从 50 题（30 题跳过）扩展到全部 80 题，80/80 通过；week1 流程回归 single 12/12、multi 12/12。
- **以下没有验证：**
  - 真实模型的解梦意象抽取（计划目标：准确率 ≥ 0.85，召回率 ≥ 0.8）。
  - 姓名、解梦、每日运势题的真实工具选择和回答质量。
  - 本环境没有 `.env` 和 API 密钥，没有发出任何模型请求。
- **人工审核率仍为 0%。** 新增 587 条释义全部是自写草稿，`reviewed: false`，解读强制使用低置信度。
- 默认配置仍为 `mode: single`。

## 实施范围与计划对照

| 计划要求 | 实现位置 | 验证 |
|---|---|---|
| 笔画规则：繁体字形 + 部首还原 + 余笔，数字按数值 | `plugins/name/strokes.py`，读取 `data/unihan/` 下 Unihan 18.0 的 `kRSUnicode`、`kTraditionalVariant`、`kTotalStrokes` | `test_all_200_dataset_strokes_and_default_forms`、`test_radical_restoration_and_numerals` |
| 姓氏繁体惯例（钟→鍾、叶→葉、范不转範等） | `SURNAME_FORMS`，与数据集生成器同一规则 | 同上 |
| 查不到的字返回给用户确认，不猜 | `analyze_name` 返回 needs_input（`unknown_name_char`） | `test_unknown_char_asks_user`、`test_unknown_character_is_never_guessed` |
| 复姓按复姓规则 | `wuge.py`：复姓天格取两字之和；常见复姓表；单姓拆复姓会被 guard 拒绝 | `test_five_grids_single_and_compound_surnames`、`test_analyze_name_provenance_and_compound_split` |
| 五格与 81 数理、125 种三才条目 | `knowledge/sources/name/entries.yaml`：81 数理 + 125 三才 + 5 格 + 5 五行 + 4 约定 = 220 条 | `test_kb_partitions_and_rules`、`test_missing_name_entry_fails_build` |
| 有 bazi_id 时名字五行与原局五行计数对照 | `bazi_comparison` 只并列计数；bazi_id 必须是本记录计算的 | `test_name_bazi_comparison_uses_reading_bazi_only` |
| 姓名只产出 trait 信号，强度上限低于八字和本命盘 | `knowledge/rules/name.yaml`：`max_strength` 0.35（八字柱位十神 0.6、本命落座 0.6） | `test_profile_name_two_names_and_validator` |
| 300 条解梦意象，每条带同义词 | `plugins/dream/symbols.py` → `knowledge/sources/dream/entries.yaml`：355 条意象 + 3 条约定；89 个种子意象全部收录 | `test_dream_kb_covers_seed_vocabulary_and_excludes_probes` |
| 同义词表 → BM25 → 向量检索；低于阈值记为未命中 | `plugins/dream/match.py`：同义词 → 包含 → FTS5 BM25（字二元组）+ Dice 阈值 0.75；**向量检索未启用** | `test_dream_matching_methods` |
| 解梦只进入 psyche，不参与时机判断 | `knowledge/rules/dream.yaml`：`horizon: psyche` | `test_dream_tool_hits_misses_and_psyche_only`、`test_dream_signals_never_cancel_timing` |
| 解梦无依据解读率为 0 | `plugins/dream/validation.py`：未命中的意象只能说明未收录；引号中的意象必须是本次命中的；不能说成预兆 | `test_dream_tool_hits_misses_and_psyche_only` |
| 每日运势：月亮与快行星相位、流日干支与日主、每日一牌，不经 LLM | `plugins/daily/tools.py` 在代码里组合三个插件的计算器与释义 | `test_daily_reading_validates_card_pillar_and_aspects` |
| seed = hash(user_id, 日期) | `daily_seed`：SHA256(`daily-sha256-v1`, 用户编号, 日期) 的前 8 字节，不用 Python 内建 `hash()` | `test_daily_seed_is_stable_and_date_specific` |
| 同一用户同一天读 `daily` 缓存 | `Store.get_daily` / `save_daily`，主键 (user_id, date) | `test_daily_same_day_unchanged_across_sessions_and_cache`、`test_daily_pure_recompute_is_identical` |
| 每日运势不设专家，编排者直接调用 | `daily_fortune` 只对 orchestrator 角色开放，单、多两种模式都注册 | `test_name_specialist_inherits_reading_bazi`、`test_multi_mode_tool_tables` |
| 新增姓名、解梦专家 | `agents/specialists.py`：`NAME_PROMPT`、`DREAM_PROMPT`，受限工具表 | `test_multi_mode_tool_tables` |
| 第 6 周定稿 19 个歧义字与 `dream_annotations.yaml` | `scripts/review_week6_datasets.py` → `docs/verification/week6/datasets.json` | 见下文 |

## 关键设计

**笔画规则与数据集同源。** `plugins/name/strokes.py` 实现的规则与 `evals/generators/gen_names.py` 完全相同：繁体字形、多部首时优先取还原部首、部首原字笔画加余笔、数字按数值。因此 200 字的金标就是实现的契约，这次没有改动数据集答案。Unihan 由 `scripts/fetch_data.py` 下载，固定 unicodetools 提交 `00f0361` 并校验 SHA256。unicode.org 被本环境网络策略拦截，所以下载地址用 GitHub 上 unicode-org 官方仓库的原始文件。

**写法歧义不静默处理。** 有真实备选写法的字，工具返回默认写法和备选笔画，并标记 `needs_confirmation`。这时 `submit_reading` 的检查要求正文提到写法或请用户确认。用户确认写法后，模型通过 `forms` 传入，`forms` 里的字必须出现在用户原话中。

**外格用一条公式。** 外格 = 天格 + 地格 − 人格。单姓单名为 2，单姓双名为名末字 + 1，复姓单名为姓首字 + 1，复姓双名为姓首字 + 名末字，都由这一条公式得出，不需要分情况写。

**三才条目由生克规则生成。** 125 种三才按“天格→人格”“人格→地格”两段五行生克写成白话，整体分为“较顺 / 需要协调 / 张力较多”三档。条目中注明这是按生克规则生成的，不是照录传统三才吉凶表。81 数理的吉 / 半吉 / 凶归类是民间约定，各家对少数数字有分歧，条目中也写明了。

**解梦匹配可解释。** 每个命中都记录匹配方式（key、synonym、contains、bm25）和分数。包含匹配要求已知意象位于短语末尾，因为中文的中心词在后：“大狗”匹配到狗，“地铁闸机”说的是闸机，不算地铁。BM25 只负责找候选，候选与原短语的字二元组 Dice 相似度达到 0.75 才接受。计划里的向量兜底需要 embedding 模型，本周没有安装，相似度不够的直接记为未命中。

**每日运势的缓存键与结果分开。** 缓存行主键是 (user_id, date)，行里保存出生资料、口径和时区的指纹。同一天重复询问时，即使代码或知识库已更新，结果也不变，并沿用当时的知识库版本。只有出生资料被更正、指纹变化时才重新计算。

**每日运势的事实复用已有检查。** 每日一牌加入事实表，由塔罗检查核对；流日干支加入八字检查的干支集合；当日相位加入占星检查的事件表。每日运势插件没有另写一套事实检查。

## 与计划的差异

- **解梦意象 355 条，多于计划的 300 条。** 这是按类别整理后的实际数量。删除了两条：“自己”太泛，“失火”与“火”重复。
- **向量检索未实现。** 计划为“同义词 → BM25 → 向量”；本周实现了前两级和包含匹配，向量兜底留到安装 embedding 模型后再做（第 7 周 RAG 也依赖它）。
- **BM25 不用 jieba。** 计划写的是 jieba 分词。解梦查询都是短意象词，字二元组足够，也不需要新增依赖；jieba 留到第 7 周的参考文本检索。
- **每日运势不排大运。** 每日运势只需要日主，传入 `gender=None`，避免真太阳时跨节气时出现与本题无关的起运追问。海外出生仍需确认真太阳时口径，与八字插件一致。
- **合婚、起名仍不支持**（计划列为第二阶段）。

## 实际测试结果

| 项目 | 结果 |
|---|---|
| 笔画 `name_strokes.yaml` | 200/200（关口：全对） |
| 37 个公认姓氏笔画 | 37/37 |
| 五格公式手算样例 | 7/7 |
| 同日运势跨会话一致 | 10 次调用 1 种结果；缓存复用 9/9；同 seed 抽牌 100 次一致 |
| 知识库覆盖 | 姓名 220/220、解梦 358/358、每日运势 9/9；总计 1171 条 |
| 解梦种子意象 / 同义词示例 | 89/89；13/13 |
| 词典外意象（14 个） | 13 个记为未命中。“扫码付款”按末尾的“付款”映射到“钱”，这正是该条标注的金标意象 |
| 解梦**离线词典扫描基线**（非 LLM） | precision 0.796，recall 0.914，100 条中 69 条完全一致 |
| 标注路线回放 | 80/80（第五周为 50/50，跳过 30） |
| week1 流程回归 | single 12/12，multi 12/12 |
| pytest | 376 项，364 通过；12 项依赖 DE440s（环境原因，与基线相同） |
| 第六周测试 / 变异检查 | 30/30；20/20 被抓到 |

**解梦基线的说明。** 扫描基线不经过模型，只把描述里出现的知识库意象和同义词按最长不重叠的方式找出来，用来验证词典覆盖和评估流水线，不能代表计划中“LLM 抽取”的指标。写同义词时能看到数据集文本，所以这个数字也不是留出集结果。主要误差来自扫描基线不理解语境，例如“光着脚”扫出“脚”，“在医院排队”除了金标的“医院”还扫出“排队”。

## 19 个待定稿字的处理

默认写法和笔画都等于数据集答案。区别在于是否存在需要用户选择的另一种写法：

| 处理 | 字 | 说明 |
|---|---|---|
| 返回默认写法与备选笔画，要求确认 | 肖（肖 9 / 蕭 18）、钟（鍾 17 / 鐘 20）、万（萬 15 / 万 3）、丽（麗 19 / 丽 7）、强（強 11 / 强 12）、艳（艷 24 / 豔 28）、杰（傑 12 / 杰 8）、郁（郁 13 / 鬱 29）、胜（勝 12 / 胜 11） | 回答必须提到写法，或请用户按证件写法确认 |
| 按姓氏惯例直接定稿 | 朱、胡、于、余、叶（葉 15）、苏（蘇 22）、沈、姜、范、向 | 只是不随通用简繁转换，没有需要用户选择的另一种写法 |

几处与数据集备注不同，按同一套规则计算后列在这里，供人工审核时对照：

- 数据集备注写“蕭 20 画”。按部首还原规则，蕭 = 艸 6 + 余笔 12 = 18 画。
- 数据集备注写“胜”本字 9 画。9 是现代笔画；按肉部还原，胜 = 肉 6 + 余笔 5 = 11 画。

这两个备选值都是规则计算的结果，上线前仍建议对照康熙字典人工抽查。

## `dream_annotations.yaml` 结构审核（非人工审核）

`scripts/review_week6_datasets.py` 的检查结果为 0 处问题：

- 金标意象集合与 `vocabulary_used` 一致（89 个）。
- 知识库没有缺少任何种子意象。
- 14 个词典外意象都没有被收录为条目或同义词。

另有两项记录：

- 5 个只出现在可接受替代里的标签不是知识库条目：失控、寻找、捡到东西、破碎、车。抽取器永远产不出这些标签，这几条替代也就无法完全匹配，建议审核时决定是否改成知识库意象。
- 5 条备注对措辞有要求（医院不暗示健康问题、葬礼不暗示有人去世、中奖不建议买彩票等）。代码检查只覆盖“不说成预兆”；温和语气需要第 7 周的 LLM 评审。

第五周推迟到本周的 3 段多轮脚本（mt-05、mt-10 需要 `daily_fortune`，mt-12 需要解梦专家），所需工具和专家现在都已注册。这 3 段还没有用真实模型跑过。

## 未完成事项

- 用真实模型运行：解梦意象抽取（关口 ≥ 0.85 / ≥ 0.8）、姓名 / 解梦 / 每日运势轨迹题、多轮脚本 mt-05、mt-10、mt-12。
- 新增 587 条释义的人工审核（发布标准 ≥ 95%），以及 19 个字对照康熙字典的人工抽查。
- 解梦向量兜底（需要 embedding 模型）。
- 远程 CI：本次新增 Unihan 下载并扩展了数据缓存路径，结果以 GitHub Actions 为准。

## 复现（离线）

```powershell
$env:PYTHONUTF8 = '1'
uv sync --locked --extra llm
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run pytest -q
uv run python -m evals.run --suite week6 --output reports/week6
uv run python -m evals.run --suite trajectory --output reports/week6
uv run python -m evals.run --suite week1 --mode single --output reports/week6
uv run python -m evals.run --suite week1 --mode multi --output reports/week6
uv run python -m scripts.review_week6_datasets --output docs/verification/week6/datasets.json
uv run python -m scripts.draft_week6   # 重新生成姓名、解梦、每日运势的释义草稿
```
