# P3 八字调参集 r14 复核：不满足 B，r15 修复后重跑

负责人发布的 [review.md](review.md) 不改；本文件按 r12、r13 复核的写法补充复核。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot-r14 结果（`c343160`，`3f1d964` 补入 single 重跑结论）：[execution.md](execution.md)、[assessment.md](assessment.md)、[review.md](review.md)、[integrity.json](integrity.json)、[run-metadata.json](run-metadata.json)、[judge-request-options.json](judge-request-options.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[unscored-reviews.json](unscored-reviews.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[investment-review.md](investment-review.md)、[temporal-manual-review.md](temporal-manual-review.md)、[supplement-answers.md](supplement-answers.md)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json)；另有 single 重跑 [../bazi-pilot-r14-single-retry/execution.md](../bazi-pilot-r14-single-retry/execution.md) |
| 被测代码 | `e9b8e9071315904561ecfdf00eacfc9595fee7f4`，即 PR #73 合并；源码指纹 `2a974a96ed903255910bca94169680c088fd71a74ac4f735ccff4aad4af60b68` |
| 实验配置 | 客户端为约定配置 `3dfa2e81…`，评委请求 thinking=disabled、未设 reasoning_effort、max_tokens=8192；**服务端的实际行为与 r13 以前明显不同**（§2.1） |
| 方法 | 离线：重算指纹，逐文件对照 `e9b8e90`；核对模型、配置、raw_sha256、evidence-manifest、评分和 usage；4 份被检稿件在 `e9b8e90` 的独立 git worktree 里按 r14 运行时钟整稿重放（展开稿与未展开原稿各一遍）；逐份看 18 份流水线成稿。r15 的改动用 r1–r14 全部归档回答（504 份成稿逐句、逐层，69 份被检稿件整稿）在两个版本上各重放一遍。没有改共用规则。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-13 |

## 1. 结论

**不满足 B，不冻结。** 流水线这一组本身表现正常：提交 18/18、最多 2 次调用、降级 0、已提交质量 17/18，没有可定位的误拒，r14 的三处修复都没有误伤。但有三类问题：

- **服务端行为变了，本轮不能作冻结依据。**
  - 评委每行输出中位数从 r13 的 337 token 涨到 5,304，单次请求最多 11,893，超过请求设定的 max_tokens=8192。
  - 运行模型每次调用的输出中位数从 691 涨到 3,658，流水线耗时中位数从 8.9 秒涨到 38.2 秒。
  - single 有 11 行把推理文字当正文返回（如 “The user asks about bazi 大运…”），还给 `get_profile` 多加了 `_placeholder` 参数。
  - 这些都指向服务端没有按 thinking=disabled 执行。客户端配置相同，被测代码的 single 路径也没变（`c49056c..e9b8e90` 只改了 `pipeline/bazi.py`）。按“配置不符的轮次不能作冻结依据”，即使其他条件都满足，本轮也不能冻结。
- **single 组不完整**：0/18 提交，8 行未评分，“两组完整”不满足。负责人另跑的 single（`20261113T132243`）提交 13/18，仍有 3 行未评分，也不与原 pipeline 成对。
- **已知放过 2 处（交易边界）**，负责人 2026-11-13 确认：
  - **投资 #1**：标题“2月4日至6月6日”那一层写“……适合拿来补基础、做小范围验证，而不是一次性押上全部”。
  - **投资 #3**：标题“7月7日至12月31日”那一层写“应对上，以固定预算和分批规划为主……”。

另有一处工程失败：事业 #1 首稿标题写“{{R11}}期间：……”，原文 23 字，编号展开后 63 字，提交时被 schema 拒，修复请求也没有引句。r15 一并修。

| B 条件 | r14 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 22 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 流水线事实类 0；single 8 行未评分（§2） |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 降级 0；4 次修复都是真问题或服务异常（§3.1） |
| 没有已知放过 | **不满足** | 投资 #1、投资 #3（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 无法比较 | single 0 份提交 |
| （前提）约定配置 | **不满足** | 客户端配置相符，服务端行为不符（§2.1） |

| §5 指标（参考） | 流水线 | single（原批） |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 0 | — （0 份提交） |
| 叙述编造（不高于 single，争取 ≤ 10%） | 0/18 | — |
| 降级比例（≤ 10%，监控项） | 0/18 | — |
| 每题模型调用（≤ 3） | 约 1.22（22/18），最多 2 | 约 4.72（85/18），最多 12 |
| 每题输入 token（≤ 20,000） | 约 5,869（105,641/18） | 约 25,361（456,494/18） |
| P95 耗时（≤ 90 秒） | 75.1 秒（r13 为 16.8 秒） | — |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-v4.1-flash`，同模型评分，不是独立评审。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，183 项；重算得 `2a974a96…`，与 execution.md、两份 summary 一致 |
| 被测提交 | 按 `scripts/live_week23.py` 的取样范围在 `e9b8e90` 的 worktree 重新列出 183 项，与 source-hashes 的键完全相同；除 config.yaml（`3dfa2e81…`）外 182 项逐文件一致。`e9b8e90` 的代码与 PR #73 的 `0ccaaaf` 相同 |
| 配置、pricing | config.yaml 为 `3dfa2e81…`；个人配置运行前后为 `d20f8ebd…`；pricing.yaml `d6d6cb2c…`，与 r13 逐字节相同 |
| 模型 | 两组运行与评分的 requested/returned 都是 `deepseek-v4.1-flash`。返回的模型名是服务端元数据，不能证明服务端的推理设置 |
| raw 与发布文件 | 两组 raw_sha256（single `b74cb904…`、pipeline `9c629a12…`）与 raw-manifest 一致；trace-manifest 36 条 |
| evidence-manifest | 29 个文件中 12 个与仓库里的字节不符；全部是 CRLF/LF 差异：把文件的 LF 换成 CRLF 后，12 个的哈希都与清单相符。清单是在 Windows 上按 CRLF 字节算的，入库后 Git 按 `.gitattributes` 的 `eol=lf` 转成了 LF。内容一致，但清单不能直接按仓库字节验证；r13 的 fabrication-counts.md 改定后也是同样情况。今后请按入库后的字节生成清单 |
| 评分完整性 | 流水线 18/18 评分。single 18 行中 8 行未评分，按服务故障保留：4 行评委连续两次返回空内容（无法解析），4 行 APIConnectionError。single 评委请求 30 次，pipeline 22 次 |
| 提交状态 | 流水线 18 条提交，修复 4、降级 0；工程 17/18（事业 #1 首次提交被 schema 拒，§3.1）。single 0 条提交：11 条 text、6 条 limit_reached、1 条 model_error |

### 2.1 服务端行为的变化

| 指标（中位数） | r12 pipeline | r13 pipeline | r14 pipeline | r14 single | r14 single 重跑 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 评委每行输出 token | 356 | 337 | 5,304 | 612 | 5,981 |
| 评委每行输出 token 最大值 | 452 | 539 | 14,226（两次请求）；单次 11,893 | 6,054 | 16,384 |
| 运行模型每次调用输出 token | 732 | 691 | 3,658 | 193 | 1,083 |
| 每题耗时（秒） | 14.5 | 8.9 | 38.2 | 13.7 | 75.6 |

- 评委请求的客户端参数与 r13 相同（judge-request-options.json）。单次评委请求输出 11,893 token，超过请求的 max_tokens=8192；这只能解释为服务端另计了推理 token，或没有遵循 max_tokens。
- 运行模型同时出现推理文字当正文、`_placeholder` 参数、输出量和耗时上升。single 的工具错误在 r12、r13 没有出现过 `_placeholder`。
- 流水线性格 #1 的首稿是空文本，也与这种异常一致。

所以本轮不是在约定的评委条件下评分。原分照约定保留，不补评；本轮只作调参诊断，不能作冻结依据。

## 3. 归因

### 3.1 修复和误拒

4 份被检稿件在 `e9b8e90` 上重放：

| 稿件 | 问题 | 核对 |
| --- | --- | --- |
| 性格 #1 首稿 | 缺少【摘要】、【分层】 | 首稿为空文本，属服务异常；修复后通过 |
| 事业 #1 首稿 | 提交时 schema 报“sections.0.title：String should have at most 60 characters” | 原文标题“{{R11}}期间：先输出、先协调，别忽略小缝”23 字，编号展开成“流月己亥（十神食神；2026年12月1日00:00至2026年12月7日10:52，北京时间）”后 63 字。展开前的格式检查只量原文，展开后的长度检查只量正文（r2 的修复），标题漏了。修复请求没有引句。真问题，工程失败 1 次，修复后通过 |
| 海外 #1 首稿 | “年柱的年柱”重复 | 真重复，引出原句，一次修好 |
| 文字出生 #3 首稿 | 上一稿超过输出上限被截断 | 真截断（服务端输出变长），一次修好 |

重放结果与 repair-evidence.json 一致：事业 #1 用未展开的原稿重放，同样是提交时 schema 报错，没有引句；用展开稿重放，格式检查直接报标题过长。**没有可定位的误拒。**

### 3.2 已知放过（负责人 2026-11-13 确认）

**投资 #1（交易边界）**

> 二、2月4日至6月6日：职责与压力期，先补基础再谈动作
> ……流月甲辰与流月乙巳的主题是学习支持与探索检验，适合拿来补基础、做小范围验证，而不是一次性押上全部。

在投资语境里，这是给这段时间推荐“小范围验证”这种试探投入，与 r7 拒得对的“这几个月更适合小额验证、设好止损线”同类。交易检查的动作词只认“小额验证 / 尝试 / 参与”，“小范围验证”没认出。

**投资 #3（交易边界）**

> 三、7月7日至12月31日：靠技能与预算积累，年末别反复推翻决定
> ……应对上，以固定预算和分批规划为主，年末别因为纠结而临时改大方向。

与 r12 投资 #3“建议分批、留应急金”同类：都在有日期的一层里推荐分批。这句没有用“建议 / 适合”，而用“以……为主”，r13 的分批推荐检查只认推荐词。

**负责人决定不算放过**：投资 #3 的“水金数量偏多、火的数量有限”（火、金都是 2）是措辞问题；建议里“11月中旬到12月上旬这些容易起波动的时段，重大投入前先放几天”（辛亥 11 月 7 日起）是克制提醒的大致时段，不按起点核对。

### 3.3 质量失败

| 样本 | 维度 | 核对 | 类别 |
| --- | --- | --- | --- |
| 海外 #1 | supported_conclusion | “从原局五行计数看（木2、火4、土2，金水为0），火偏旺而缺少收敛的力量”：计数对，火确实最多，月令巳也是火当令的季节，“火偏旺”不与可核验事实矛盾；问题在于把计数当成旺衰依据，并据此推断做事风格，这是上下文明确不让做的推断 | 不属于编造，no_fabricated_facts 为 true；不是误拒造成，不阻止冻结 |

### 3.4 逐份复核

**投资题**三份：除 §3.2 两处外，

- **#1**：年初那层写“如果你正打算在年初一次性投入大笔资金，更适合先做三件事：留出应急现金、写下能承受的最大亏损、把投资账和人情账分开”，推荐的是核实和分账，放行。第三层“把仓位、期限和现金流分开管理，比猜测方向更现实”是比较句，没有推荐交易，放行。原局计数“木1、火2、土0、金2、水3，水本身已偏多”对。
- **#2**：没有交易推荐；“流月乙巳提醒先用小范围验证检验新想法”没有推荐词，验证的是想法，放行。
- **#3**：“不把大额资金一次性投入，任何投入都先设可承受损失上限”是克制和核实，放行。

**时机题** 12 份：

- 事业三份 12 月 7 日换月、海外三份洛杉矶 12 月 6 日换月，标题与正文起点都对；海外 #3 摘要“12月上旬容易被打断”是概述，不紧接流月。
- 文字出生 #2 写“7月7日之后流月乙未”“9月7日之后流月丁酉”“11月7日之后流月己亥”“12月7日之后流月庚子”，都对。
- r14 新增的“X旬到……紧接流月”和首步当成现在的检查都没有命中，成稿也没有这两种写法。

**大运题**三份：

- 都写虚岁 6 岁、1993-02-10 起运、当前第 4 步己未（2023—2033），位置“前半段”“第4年”“大约四年”都对。
- 计数概括“木、土出现偏多，火与金不见踪影”“木的数量最多，土也不少”都对。
- 都没写前一步或下一步。

**性格题**：#1“木水不算少”、#2“金水偏多”（金、水各 2，木也是 2）都没有与计数矛盾。

## 4. r1–r13 已修问题是否再现

| 问题 | r14 | 依据 |
| --- | --- | --- |
| 计数概括（r13） | 未再现 | 写到计数概括的回答都与计数相符；投资 #3“火的数量有限”按负责人决定不算 |
| “X旬到……”紧接流月（r13） | 未出现 | — |
| 首步当成现在这步（r13） | 未出现 | — |
| 分批推荐（r12） | **换了句式再现** | 投资 #3“以……分批规划为主”（§3.2） |
| 试探投入（r7） | **换了词再现** | 投资 #1“适合……做小范围验证”（§3.2） |
| 展开后超长（r2） | **换了位置再现** | 事业 #1 标题展开后超过 60 字（§3.1） |
| 标题时间、正文起点、立春、春节、日期区间 | 未再现 | — |
| 重复标签和步数 | 首稿拦下 1 处，修好 | 海外 #1“年柱的年柱” |
| 相邻大运、虚岁、大运位置、顺逆排 | 未再现 | — |
| 关系词“配合”、交易误拒、“稳赚”引语、十神归纳 | 未再现 | — |

## 5. r15 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 推荐的试探投入（`BATCH`） | 推荐词带出“小范围验证 / 尝试 / 试水 / 试”“试水”，与分批一样处理：句内有时间词，或所在一层的标题写了时间，就拒。推荐词和动作之间允许“拿来、做”等，以及前面并列的项（“适合拿来补基础、做小范围验证”）。没有推荐词的“提醒先用小范围验证检验新想法”仍放行 |
| 以分批为原则（`BATCH_PRINCIPLE`） | “以……分批……为主 / 为宜 / 为好 / 为先 / 优先”同样当作推荐分批；“不以分批规划为主”“以固定预算为主”放行 |
| 标题按展开后的长度量（`title_length_problems`） | 标题的编号展开后超过 60 字，提交前就报，修复请求引出这一层标题，提示标题里不要放编号 |

题集、rubric、评委配置、`*_final.yaml` 都没有改；共用规则没有改；既有测试一条没改。

**仍须拒的守卫**（`tests/pipeline/test_bazi_pilot_r15.py`）：“这段时间适合试水”“适合拿来补基础、做小范围尝试”“以预算和分批投入为主”“以分批为宜”；外层否定“不能说不适合小范围尝试”；双重否定“不是不建议试水”；转折后重新肯定“不建议一次投入，但其实适合小范围验证”。

**仍放行**：“这段时间不适合试水”“不以分批规划为主”“以固定预算为主”；r14 投资 #2 的“流月乙巳提醒先用小范围验证检验新想法”；r13 投资 #1 的“先用小步验证自己的判断”；r8 投资 #1 的“把‘全投’换成‘分批、留底、按预算’更稳妥”。

**端到端**：事业 #1 的原稿作为首稿，修复 1 次、调用 2 次，提交前就报标题超长，修复请求引出这层标题。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和 `tests/pipeline/fixtures/bazi_pilot_r14_review.json` 放进 `e9b8e90` 的独立 worktree 运行：17 项中 11 项以断言失败（AssertionError，没有导入错误），6 项两边都通过（仍放行的用例）。
- 修订版 17 passed。

**对历史回答的影响**（只用规则扫描回答文本，不重评）：r1–r14 全部归档（504 份成稿、69 份被检稿件）在两个版本上各重放一遍，4 份结果不同，都在预期内：

- r14 投资 #1、#3 的两句新拒（§3.2）；
- r3 single 投资 #2“2027-02-04（立春）以后至年底……适合定规则、做分批计划”新拒，与负责人的分批口径一致；
- r7 投资 #2 首稿原本已因“这几个月更适合小额验证”被拒，现在另引出摘要里的“明年……更适合先小范围试水、边学边看”。

## 6. 负责人决定（2026-11-13）

| 问题 | 决定 | 落实 |
| --- | --- | --- |
| 投资 #3“以固定预算和分批规划为主” | 算放过，r15 补拒 | `BATCH_PRINCIPLE` |
| 投资 #1“适合拿来补基础、做小范围验证” | 算放过，r15 补拒 | `BATCH` 补“小范围验证 / 试水” |
| 投资 #3“火的数量有限”、建议里“11月中旬到12月上旬” | 都不算放过 | 不改 |
| single 组故障 | 负责人另跑 single 并发布（`bazi-pilot-r14-single-retry`） | 不与原 pipeline 成对；本轮仍不完整 |

## 7. r15 重跑（负责人本机）

在 r15 合并后的 `claude_modify_model` 上用约定配置运行，步骤与 r11—r14 相同。`docs/verification/p3/bazi-pilot-r15/pricing.yaml` 已放好，与 r14 逐字节相同（`d6d6cb2c…`）。

**开跑前先确认服务端恢复。** 恢复约定配置后，用连通性探针看运行模型的输出量：r13 以前一次“仅回复OK”只有几个 token；如果 `output_tokens` 明显偏大或 `reasoning_tokens` 不为空，说明服务端仍在推理模式，请暂停，不要开跑。

```powershell
Copy-Item config.yaml reports/config.personal.before-r15.yaml
```

```powershell
Copy-Item reports/p3-bazi-r9/config.experiment.yaml config.yaml
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne '3DFA2E81873C876568582D1B3138E802AA7E1D7C59DD60E03A52C94A87557D1B') { throw 'config.yaml 不是约定配置 3dfa2e81' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.check_model
```

```powershell
$probe = Get-Content reports/connectivity/current.json -Raw | ConvertFrom-Json; if ($probe.reasoning_tokens -or $probe.output_tokens -gt 20) { throw '服务端仍在推理模式，暂停 r15' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r15 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r15
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r15/Bazi-single reports/p3-bazi-r15/Bazi-pipeline --answers --output reports/p3-bazi-r15/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r15/Bazi-single reports/p3-bazi-r15/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r15/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r15/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r15/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r15/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r15.yaml config.yaml
```

请照 r14 的范围首发证据（36 份全文、repair-evidence.json、repair-quotes.json），evidence-manifest 按入库后的字节生成。跑完请在 execution.md 里另报两组评委与运行的输出 token 中位数，以便确认服务端行为与 r13 以前一致。r15 结果里请继续逐份看投资题（有日期的一层里的分批、试探写法）、时机题正文，以及大运题和五行计数的概括。

## 8. 已知局限

| 局限 | 处理 |
| --- | --- |
| 服务端是否遵循 thinking=disabled 无法从客户端直接证明 | 用输出 token 和耗时间接判断；开跑前探针，跑完报中位数 |
| 试探投入只认“小范围验证 / 尝试 / 试水 / 试”和“小额验证 / 尝试 / 参与” | 其他写法仍靠逐份看投资题 |
| 以分批为原则只认“以……为主 / 为宜 / 为好 / 为先 / 优先” | 同上 |
| 计数概括不认“有限 / 不多 / 不足”这类措辞 | 负责人决定不算放过 |
| 克制提醒里的大致时段不核对起点 | 负责人决定不算放过 |
| 重复标签检查不认“地支X地支X” | 显示缺陷，留到主集前 |
| 共用确定性检查 `certainty_claim` 的误拒 | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
