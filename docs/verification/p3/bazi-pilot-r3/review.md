# P3 八字调参集 r3 复核：不满足 B，r4 修复后重跑

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot-r3 结果（`e2eadeb`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[comparison.md](comparison.md)、[integrity.json](integrity.json)、[acceptance.json](acceptance.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)、[known-escape-probe.json](known-escape-probe.json)、[title-checks.json](title-checks.json)、[temporal-evidence.json](temporal-evidence.json)、[fallback-probe.json](fallback-probe.json)、[unscored-reviews.json](unscored-reviews.json)、[pr62-followup.md](pr62-followup.md) |
| 被测代码 | `a6a1c80bf7ec13eb8f5868e256bbe810e390b09d`，即 PR #62 合并（`75e1c60`）后加负责人修复；源码指纹 `7fa842a76a4172146fa25d2055032936a0c9bdfc3f7606b089033109f5363d90` |
| 实验配置 | `3dfa2e81…`，八字约定配置 |
| 方法 | 离线：重算指纹，逐文件对照 `a6a1c80`；核对模型、raw_sha256、evidence-manifest 和评分；归因用原句在 `a6a1c80` 的独立 git worktree 里复现。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-09 |

## 1. 结论

**流水线满足 P1 四条，已提交质量 16/18（88.9%）高于同批 single 的 9/15（60.0%）。但按 B 不冻结**，原因是同一条回答：

- 文字出生 #2 把首步大运辛巳写成“这个大运阶段”，用在 2026 年下半年；这段时间所在的大运是癸未。这是事实类编造 1 条；
- 这句话通过了全部现有检查，是已知放过。

两组 36 条全部评分，计数表都“完整”。r1、r2 修过的问题本轮都没有再现。r4 修这处放过，并补上本轮发现的“正文留下字面编号”，配了离线测试。

| B 条件 | r3 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；18 条工程检查全过；最多 2 次，共 22 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 两组都“完整”（36/36 评分，没有未评分行）。流水线事实类 1 条：文字出生 #2 的大运错置（§3.3） |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 4 次修复共 10 个问题，都是真实的重复标签（§3.1）；0 降级 |
| 没有已知放过 | **不满足** | 上面那句原句在 `a6a1c80` 上返回空问题列表；“目前走的是辛巳大运”也放行（§3.4） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 16/18（88.9%）对 9/15（60.0%） |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | **1** | 1 |
| 叙述编造（不高于 single，争取 ≤ 10%） | 0/18（0.0%），满足 | 5/15（33.3%） |
| 每题输入 token（≤ 20,000） | 约 5,621（101,171/18） | 约 41,135 |
| P95 耗时（≤ 90 秒） | 18.4 秒 | 51.8 秒 |
| `time_consistent` 失败 | 2/18 | 3/15（已提交） |

- 只计 [fabrication-counts.md](fabrication-counts.md) 中“结果”为“完整”的数字。两组都是“完整”。
- 统计只作参考；6 题各重复 3 次，不是 18 个独立样本。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，183 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `7fa842a7…`，与 execution.md、两份 summary、integrity.json 一致 |
| 覆盖范围 | 183 项全部在 `a6a1c80` 的 worktree 中存在。除 `scripts/live_test.py` 的 8 个目录外，还含 `app.py`、`uv.lock` 和 `evals/cases/*.yaml`（`p1_campaign` 的取样规则），worktree 中没有多出的同类文件 |
| 被测提交 | 除 config.yaml 外 182 个文件与 `a6a1c80` 逐文件一致；`a6a1c80..e2eadeb` 在这些目录下没有改动（只多了 docs/） |
| 配置 | source-hashes 中 config.yaml 为 `3dfa2e81…`；run-metadata 记录 base `248e6db0…`、运行后按原字节恢复本机配置 |
| pricing.yaml | `d6d6cb2c…`，与 r2 逐字节相同；没有模型费率，费用未知 |
| 模型 | 两组的请求和运行返回都是 `deepseek-v4.1-flash`；36 条评分的 requested/returned 也都是 `deepseek-v4.1-flash`。`judge_name: pro` 是配置角色名 |
| raw 与发布文件 | 两份 summary 的 raw_sha256 与 raw-manifest 一致；evidence-manifest 列出的 33 个文件逐字节一致，目录里只有 evidence-manifest.json 自身不在清单中 |
| 评分完整性 | 两组 18/18 评分；[unscored-reviews.json](unscored-reviews.json) 为空，没有 APIConnectionError，没有补评。single 有 1 条评分解析了 2 次（parse_attempts=2），是评委输出格式重试，不是补评 |
| 追问 | 海外题 3 次都只问 1 次真太阳时；文字出生题 3 次都没有追问，画像为女、1995-04-28 07:15、深圳 |

原始 live.json 和 trace 只在负责人本机，我核对的是发布文件之间的一致性，没有重算原始报告的哈希。

## 3. 归因

### 3.1 四次修复

| 样本 | 首稿问题 | 归因 |
| --- | --- | --- |
| 大运 #1 | 日柱日柱、月柱月柱、年柱年柱、时柱时柱 | 真错误，原句如“月柱月柱乙卯（天干乙为比肩）”；一次修好，质量通过 |
| 事业 #1 | 日主日主 | 真错误，“日主日主丁火只作关系标签的基准”；一次修好，质量通过 |
| 大运 #2 | 年柱年柱、月柱月柱、时柱时柱 | 真错误，“年柱年柱戊辰（天干戊为正财）”；一次修好，质量通过 |
| 投资 #2 | 月柱月柱、时柱时柱 | 真错误，“原局月柱月柱庚子……时柱时柱辛亥”；一次修好，质量通过 |

- 10 个问题在 [repair-quotes.json](repair-quotes.json) 里都有原句，原句里都有重复的标签。
- [pipeline-problems-raw.md](pipeline-problems-raw.md) 只有这 10 条，没有展开后超长或其他检查。
- 没有误拒。重复标签占了 4/18 的第二次调用，是成本，不是失败。

### 3.2 质量失败（流水线 2 条）

| 样本 | 维度 | 归因 |
| --- | --- | --- |
| 文字出生 #1 | time、supported | 我同意负责人的判断。time 理由称 2026 年是“戊午年”，又把流年丙午的范围切片（7 月 1 日至次年 1 月 1 日，右开）读成范围错误，与约定口径不符，原分保留。supported 理由指六合推出“联结感”、冲刑推出“不宜重大关系决定”，属撰写的支撑尺度问题 |
| 文字出生 #2 | time、supported、fabricated | fabricated 理由原文：“回答将首步大运当作当前阶段引用，属对用户大运阶段的事实错置”，与原句、计算一致（§3.3）。time 布尔值为 false，理由却写“判 true 可接受”，自相矛盾，原分保留。supported 指“整体平稳”“年底回暖”是综合断语 |

### 3.3 编造分类

| 样本 | 类别 | 核对 |
| --- | --- | --- |
| 流水线文字出生 #2 | 事实类 | 原句“但1997年12月28日起运，首步大运辛巳（1997年交运）这个大运阶段需要你留意自身节奏，别把所有精力都投在关系里。”。[temporal-evidence.json](temporal-evidence.json) 记录这三次运行的起运日都是 1997-12-28，大运依次为辛巳、壬午、癸未、甲申，current_candidates 为癸未，范围是 Asia/Shanghai 的 2026-07-01 至 2026-12-31。辛巳的 1997–2007 年与范围不相交。干支和起运日都对，错在它在时间上的位置，同意归为事实类 |
| single 5 条 | 事实类 1、叙述类 5 | [fabrication-attribution.md](fabrication-attribution.md) 引的原句都能在对应回答中找到。single 文字出生 #2 的事实类（“这个月偏印当令”）我没有按 single 的计算重新核对 |

### 3.4 已知放过：在 `a6a1c80` 上复现

我在 `a6a1c80` 的独立 worktree 里，用与本轮相同的大运序列（起运 1997-12-28；辛巳 1997、壬午 2007、癸未 2017、甲申 2027；current_candidates 为癸未）调用 `Bazi.dayun_problems`：

| 原文 | `a6a1c80` 的结果 |
| --- | --- |
| 上面的原句 | `[]` |
| 目前走的是辛巳大运。 | `[]` |
| 当前大运辛巳。 | 拒：“按今年算所在的大运是癸未，正文写成了辛巳” |
| 目前走的是癸未大运。 | `[]`（正确） |

与 [known-escape-probe.json](known-escape-probe.json) 一致。原因有两层：

1. **事实表。** 时机题的事实表里，可以引用的大运事实只有一条：“起运，首步大运辛巳（1997年交运）”。`plugins/bazi/tools.py` 的 `chart_atoms` 只在大运概览题里附上各步大运。当前的癸未只出现在上下文的一行说明里，不能引用。写作者想引一条大运依据时，能引的只有首步大运。
2. **校验。** `CURRENT_DAYUN` 只认“当前大运X”“正在走X大运”等写法，不认“目前走的是X大运”“当前处于X大运”。“X……这个大运阶段”这种回指没有任何检查。

## 4. r1、r2 已修问题是否再现

| 问题 | r3 | 依据 |
| --- | --- | --- |
| 分段标题的时间（r1） | 未再现 | [title-checks.json](title-checks.json)：12 条时机题、32 个标题，没有问题；r1 的“先甜后磨的上半年尾巴”在被测代码上仍被拒 |
| 引号里的否定（r1） | 未再现 | “这不是‘必然发财’”被接受（title-checks.json 的 regression） |
| 展开后超长（r2） | 未再现 | 没有长度问题，也没有提交时的 schema 错误；18 条全部提交 |
| 降级稿的配对关键词和截断（r2） | 本轮没有走到 | 0 降级，[fallback-probe.json](fallback-probe.json) 为空，真实模型没有走到这条分支 |

`tests/pipeline/test_bazi_title_regressions.py`、`test_bazi_pilot_r2.py`、`test_bazi_pilot_r3.py`、`test_bazi_fallback_capacity.py` 在 `a6a1c80` 的 worktree 中 85 passed。它们用 r1 的标题原文、r2 的投资题原稿回放，可以离线证明降级链已修，但不能替代真实降级的现场验证。

## 5. 其他观察（不阻止冻结）

| 现象 | 样本 | 处理 |
| --- | --- | --- |
| 正文留下字面编号：三层正文末尾写着“引用：R7 R8 R4 R5”之类。写作者把引用写在正文里，没有用【引用】行；`compose.parse` 把这一行当成正文 | 文字出生 #3（质量通过） | r4 在八字的 `problems` 里拒绝渲染后仍留下的 `R数字`（§6） |
| 投资题按流期给仓位、交易频率的建议，例如“操作上宜降低频率”“是适合复盘预算、控制仓位的时段”。PR #62 后的提示词明确禁止，但没有对应的检查 | 投资 #2、#3（质量通过） | 加检查是新增拒绝语义，**请负责人决定**是否在 r4 之后加（§8） |
| 本命五行计数被写成“这个月”的分布 | 海外 #1（质量通过） | 撰写问题，先看再现率 |

## 6. r4 的改动（本 PR）

| 改动 | 内容 | 测试 |
| --- | --- | --- |
| 大运被写成“这个阶段”（`Bazi.stage_here_problems`） | 时机题里，一步大运后面紧跟“这个大运阶段 / 这步大运 / 这一步 / 此运”等指代，而这步大运的十年与所问范围不相交时，要求修复。提示文字：“这次看的是2026-07-01至2026-12-31，所在大运是癸未；辛巳是1997至2007年的大运，不能当成这段时间的大运阶段”。只在问题类型是时机、有流期范围时生效；交运年两步都算覆盖 | r3 原句、去掉括号、括号后加逗号 |
| 豁免 | 紧跟在后的“早已过去 / 走完 / 之后 / 以前”，或紧挨在前的“早在 / 当年 / 回看 / 下一步 / 将来”；明确否定（“现在不是首步大运辛巳这个阶段”）。否定从标签前读起 | 豁免只认紧邻的位置。同一分句其他位置的“过去”（“别重复过去的模式”）、前一分句的“回看过去”都不豁免 |
| 当前大运的写法（`CURRENT_DAYUN`） | 补上“目前走的是X大运”“当前处于X大运”“如今正行X运”“现在所处的大运是X”“目前走的大运是X”；后两类可以带否定。“运势”“运气”不算 | 新写法写错要拒，写对（含“不是辛巳，而是癸未”）放行 |
| 事实表和上下文 | 首步大运的事实文字加上“2007年换下一步”。时机题在首步大运不覆盖范围时，上下文加一行：“这段时间所在的大运是癸未（2017年交运）；事实表里的首步大运辛巳只说明何时起运，不是这段时间的大运，不要把它写成‘这个大运阶段’。” | 端到端：事实表和上下文中出现这两段文字 |
| 字面编号（`LITERAL_ALIAS`） | 渲染后的文字里仍有 `R数字`（不在 `{{}}` 中，前后不是字母或数字），要求修复：“正文里直接写了R加数字的编号……要引用就写成{{编号}}由程序换成文字，或把编号写在【引用】行”。问题文字固定，修复请求能逐句引出触发句 | r3 原行、“依据见R12”“（R3、R4）”拒；“R&B”“QR2”放行 |

**仍须拒的守卫**（都在 `tests/pipeline/test_bazi_pilot_r4.py`，用计算出的盘，不手填）：

| 类别 | 例句（都要拒） |
| --- | --- |
| 同句其他意象 | 流年丙午主学习，首步大运辛巳这个大运阶段也要留意节奏。 |
| 先否定后肯定（转折后重新肯定） | 现在不是辛巳这个大运阶段，但其实还是辛巳这个大运阶段。 |
| 外层否定 | 不能说现在不是首步大运辛巳这个阶段。 |
| 程度词插入 | 现在不完全是首步大运辛巳这个阶段。 |
| 双重否定 | 现在不是不在辛巳这个大运阶段。 |
| 新的当前写法 | 目前走的是辛巳大运。／当前处于辛巳大运。／目前走的不是癸未大运。 |

**仍放行**：

- 本范围的大运：“癸未这个大运阶段需要你留意……”“当前处于癸未大运”；
- 其他时间：“……早已过去”“……这一步之后，又走了壬午和癸未”“早在……”“下一步甲申这个大运阶段从2027年开始”；
- 明确否定；
- 流年的“这个阶段”；
- 非时机的大运概览题：同一句“首步大运X这个大运阶段需要你留意”不拒。

**端到端**：

- 脚本写作者照 r3 的写法引用大运事实，再写“这个大运阶段需要你留意……”：修复 1 次，调用 2 次，不降级。修复请求的“出问题的句子”就是这句展开后的原文。
- 脚本写作者把“引用：R…”写进正文：修复 1 次，最终正文没有字面编号。

**在评审版本上失败、在修订版上通过**：把 `test_bazi_pilot_r4.py` 放进 `a6a1c80` 的独立 worktree 运行，7 个行为测试失败，都是断言失败（不是导入错误）；2 个“仍放行”测试两边都通过。修订版 9 passed。

新文件与 r3 原文的一致性：

- 用 r4 的模式扫描 r3 全部 36 份回答，“这个阶段”类只命中文字出生 #2 这一句。另外三处命中在大运概览题里（“目前正处在第4步大运己未（…）这一步”等），写的是正确的当前大运，而且这类题不启用这项检查。
- 当前写法只命中 single 大运 #2 的“现在走的是己未大运”，写对了，不拒。

两份题集、rubric、评委配置和 `*_final.yaml` 都没有改。

## 7. r4 重跑（负责人本机）

在 r4 合并后的 `claude_modify_model` 上运行，配置仍用 `3dfa2e81…`。`docs/verification/p3/bazi-pilot-r4/pricing.yaml` 已放好，与 r3 逐字节相同（`d6d6cb2c…`）：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r4 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r4
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r4/Bazi-single reports/p3-bazi-r4/Bazi-pipeline --answers --output reports/p3-bazi-r4/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r4/Bazi-single reports/p3-bazi-r4/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r4/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r4/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r4/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r4/pipeline-problems-raw.md
```

如果评委连接出错，请照约定保留，不补评。只要有未评分，B 的“两组完整”就不满足。

## 8. 请负责人决定

| 问题 | 背景 | 我的建议 |
| --- | --- | --- |
| 投资题从流期推出仓位、交易频率，是否加检查 | 投资 #2、#3 违反 PR #62 新加的提示词，评委判通过。加检查就是新增一类拒绝，属于改校验语义 | 先看 r4 的再现率。如果还出现，再加八字专用检查，只拒“流期/某月 + 仓位/买卖时点/交易频率/加仓减仓”的组合，并配守卫 |
| 字面编号的检查是否扩到共用的 `compose.parse` | r4 只在八字里拒。星盘、每日运势的写作者也可能这样写；改 `compose.parse` 会动已冻结的星盘和 P2 体系 | 主集前和共用的文字出生资料一起重新核对时再决定 |

## 9. 已知局限

| 局限 | 现象 | 处理 |
| --- | --- | --- |
| “这个阶段”的识别靠紧邻位置 | “辛巳那十年你要留意节奏”这类不带指代词的写法，或指代词和大运隔了一整句，仍不会被拒 | 正则只能逐类覆盖；r4 同时从事实表和上下文消除诱因 |
| 豁免词是有限列表 | 像“辛巳这个阶段在你小时候”这种其他写法的过去时间仍可能被拒 | 会消耗一次修复；修复后仍触发时会降级，不能保证不会降级。PR #63 合并后补上了年份正确且直接限定该大运的历史回顾，并收紧“过去”的豁免，避免把“已过去一半／三年”当作整步大运结束；同时补查对实际大运阶段的错误否定，交运年保留两种候选 |
| 时机题仍不能引用当前大运的事实 | 当前大运只在上下文里说明。在时机题里附上当前大运，要改共用的 `chart_atoms`，会影响 agent 路径 | 本轮不改；如需要，单独提 |
| 评分载荷不含运行日、出生钟表口径 | time 理由多次与约定口径冲突（文字出生 #1、#2） | 评委配置不改，原分保留 |
| 降级链没有真实运行覆盖 | r3 是 0 降级 | 离线回放已覆盖；最终验收集出现降级时再核对 |

## 10. PR #63 合并后的边界修复

- “已过去一半／三年”不再被视为整步大运结束；“已经过去了。”“早已结束，”等完整结束表述仍放行。
- 年份直接限定某步大运，且落在该步计算出的年份标记内时，允许历史或未来回顾；错误年份、跨出该步的年份范围、其他分句的无关年份不能豁免。合法历史句子端到端一次提交，无修复、无降级。
- 补查“现在不是癸未这个大运阶段”这类否认实际大运的表述；保留明确否定错误大运、否定推论、外层否定及交运年两种候选。错误断言端到端修复一次，修复请求引用触发句。
- 验证使用独立副本的仓库默认配置，本机 config.yaml 原字节保留。八字流水线与校验 175 项通过，`tests/validation/test_accept_paths_generated.py` 58 项通过，共 233 项；另有审查阶段的 5 个诊断探针通过。全目录 Ruff 检查、格式检查和 `git diff --check` 通过。
- 以上为离线验证，没有执行 r4 真实模型调参实验，不改变 r3 的“不满足 B、不冻结”结论。
