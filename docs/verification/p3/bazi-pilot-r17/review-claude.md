# P3 八字调参集 r17 复核：不满足 B，r18 修复后重跑

负责人发布的文件不改；本文件按 r12 复核和 r13–r16 的 review-claude.md 的写法补充复核。同目录的 [review-fixes.md](review-fixes.md) 是负责人在 PR #78 合并前的修复记录，已含在被测代码里。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 r17 结果（`900f443`，PR #79 合并为 `18f20dc`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[run-metadata.json](run-metadata.json)、[config.experiment.yaml](config.experiment.yaml)、[service-probe.json](service-probe.json)、[integrity.json](integrity.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[supplement-answers.md](supplement-answers.md)、[supplement-answers.json](supplement-answers.json)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json) |
| 被测代码 | `82619a936a7c2afa3c38f67343d28b76d113ffde`，即 PR #78 合并（含负责人的 `9c7a625`）；源码指纹 `1b5fcf2c841a40e8ce8c344efd9340d939d1b7664fbc9a72dc7bfc0aedb7d16f` |
| 接入与配置 | 约定：官方 `https://api.deepseek.com`，运行与评委都是 `deepseek-flash`，实验配置 `ca6e52b2…`；评委 thinking=disabled、不设 reasoning_effort、max_tokens=8192 |
| 方法 | 离线：重算指纹，在 `82619a9` 的独立 git worktree 里按 `scripts/live_week23.py` 的取样范围逐文件对照；核对模型、配置、raw_sha256、evidence-manifest 和评分；repair-quotes.json 的 3 份被检稿件（未展开原稿）在 `82619a9` 上按 r17 运行时钟（`20261114T213503`）整稿重放；18 份流水线成稿按结构逐句、逐层重放；逐份看 18 份流水线成稿和 single 的 3 份编造失败。r18 的改动用 r1–r17 全部归档回答（612 份成稿逐句、逐层，83 份被检稿件整稿）在两个版本上各重放一遍。没有改共用规则，没有调用模型 |
| 日期 | 2026-11-15 |

## 1. 结论

**不满足 B，不冻结。** 我同意负责人在 [assessment.md](assessment.md) 里的判断，另补一处已知放过。

本轮流水线是目前最好的一轮：
- 提交 18/18、调用最多 2 次，已提交质量 17/18（94.4%），高于 single 的 11/15（73.3%），P1 四条满足；
- 流水线计数表“完整”、编造失败 0；
- r16 的相邻十年和“稳赚”误拒都没有再现。

没有满足的有三条：

- **造成降级的误拒 1 处**：投资 #3 两稿都写“……流月丙午与本命月柱庚子地支冲（6月6日至7月7日）、与时柱辛亥（天干辛为偏财）……”。时干辛对日主丁是偏财，写对了；十神检查看到同一分句前面关系事实里的“地支”，就转去核对地支藏干，报“这次的地支藏干里没有偏财”，两稿都拒，降级为关键词稿（§3.1）。
- **已知放过 1 处（交易边界）**：投资 #2 摘要“明年……更适合以保守、分散、先保生活底线的方式管理资金”。负责人 2026-11-15 判为放过，r18 补拒（§3.2）。
- **single 计数表不完整**：3 条待判定。本复核给出建议判定（§3.4）。

| B 条件 | r17 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 20 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 流水线完整、事实类 0；single 3 条待判定 |
| 没有造成降级、失答或质量失败的可定位误拒 | **不满足** | 投资 #3（§3.1） |
| 没有已知放过 | **不满足** | 投资 #2（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 17/18（94.4%）对 11/15（73.3%） |
| （前提）约定接入与配置 | 满足 | §2 |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 0 | 0（建议判定） |
| 叙述编造（不高于 single，争取 ≤ 10%） | 0/18 | 建议 3/15（20.0%） |
| `time_consistent` 失败 | 1（文字出生 #3，评委误读） | 4 |
| 降级比例（≤ 10%，监控项） | 1/18（5.6%）：投资 #3（误拒） | — |
| 每题模型调用（≤ 3） | 约 1.11（20/18），最多 2 | 约 6.56（118/18），最多 11 |
| 每题输入 token（≤ 20,000，不含评委） | 约 5,573 | 约 44,031 |
| P95 耗时（≤ 90 秒） | 10.1 秒 | 31.6 秒 |
| 已提交回答质量通过率 | 17/18（94.4%） | 11/15（73.3%） |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-flash`，同模型评分，不是独立评审。投资 #3 的关键词稿评委四项都判通过，17/18 里含这一份；它仍是误拒造成的降级。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，184 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `1b5fcf2c…`，与 execution.md、两份 summary、integrity.json 一致 |
| 被测提交 | 按 `scripts/live_week23.py` 的取样范围在 `82619a9` 的 worktree 重新列出 184 项，与 source-hashes 的键完全相同；除 config.yaml 外 183 项逐文件一致 |
| config.yaml 一项 | `ca6e52b2…`；入库的 config.experiment.yaml 为 LF（`2ec411fa…`），换成 CRLF 即 `ca6e52b2…` |
| 接入与模型 | run-metadata.json：官方 `https://api.deepseek.com`；两组 36 行运行和 36 条评分的 requested/returned 都只有 `deepseek-flash` |
| 探针 | [service-probe.json](service-probe.json) 三项通过：1、21、1 token，`reasoning_tokens` 为空 |
| raw 与发布文件 | 两组 raw_sha256 与 raw-manifest、integrity.json 一致；trace-manifest 36 条 |
| evidence-manifest | 列 27 个文件，按入库后的字节逐一相符；目录里只有 evidence-manifest.json 自身不在其中（不含本文件） |
| pricing.yaml | `15ea038e…`，与 r16 逐字节相同 |
| 评分完整性 | 两组 18/18 评分，没有未评分行。评委请求 single 19 次、pipeline 18 次：single 文字出生 #2（summary 的 repeat=1；execution.md 写作 #1）在运行器内置的解析重试中第 2 次成功，usage 是两次的累计（输出 975），不是事后补评。单行评委输出最多 558（pipeline）、975（single，两次合计） |
| 提交状态 | 流水线 18 条全部提交，修复 2、降级 1（keywords）。single 15 条提交，3 条 ask_user（海外 #1–#3），最多 11 次调用 |

**服务端行为**（按行的中位数）：评委每行输出 pipeline 346.5、single 362.5；运行每次调用（每行输出 ÷ 调用数）pipeline 653.5、single 346.6；每题耗时 pipeline 5.4 秒、single 15.2 秒，与 r13、r15、r16 一致。

## 3. 归因

### 3.1 修复、降级和误拒

3 份被检稿件在 `82619a9` 上按 r17 运行时钟整稿重放，问题与 repair-evidence.json 逐字一致，引句如下：

| 稿件 | 被拒的句子 | 核对 |
| --- | --- | --- |
| 性格 #1 首稿 | 月柱、年柱、时柱各重复一次；“［引用］R7 R5 R1”“［引用］R4 R6”（全角方括号，程序不认，编号留在正文） | 都是真问题，一次修好 |
| 投资 #3 首稿 | 标题“2月4日起：摩擦增多，宜守不宜押”，正文有 3 月 6 日起的流月癸卯 | 真问题 |
| 投资 #3 首稿、第 2 稿 | “……北京时间）与月柱庚子（天干庚为正财）有流月丙午与本命月柱庚子地支冲（6月6日至7月7日）、与时柱辛亥（天干辛为偏财）有流月丙午与本命时柱辛亥天干合（6月6日至7月7日），……” | **误拒，造成降级**：时干辛为偏财，对。`ten_god_problems` 只要同一分句（到逗号）前面出现“地支”就按藏干核对，而“、”不断分句，前面关系事实里的“地支冲”把这个偏财带进了藏干检查 |

第 2 稿已按修复请求改好了标题，只剩这一条误拒。

### 3.2 已知放过：投资 #2（交易边界，负责人 2026-11-15 决定）

> 按八字符号看，明年不适合把积蓄全部投入股市，更适合以保守、分散、先保生活底线的方式管理资金。

摘要第一句用推荐词带出“分散”的资金管理方式，有时间词“明年”。与 r14“以固定预算和分批规划为主”同类：分批、小范围 / 小步验证都已在词表里，“分散”没有。

**负责人决定不算放过**：投资 #1 第三层“如果你正在考虑大额投入，先把生活费和应急钱单独留出来，任何操作都设好上限，别用全部积蓄去赌一个判断”属于限制和克制。

18 份成稿在 `82619a9` 上逐句、逐层重放，全部没有问题，投资 #2 这句也一样。

### 3.3 质量失败

| 样本 | 维度 | 核对 | 类别 |
| --- | --- | --- | --- |
| 文字出生 #3 | time、supported | time：评委以“若用户语境为2025则全盘错位”判 false，as_of 是 2026-11-15，正文展开的是 2026 年的节气流月，评委自己也说节气处理正确，属误读。supported 是论证强度的意见，原分保留 | 不属编造 |

### 3.4 编造分类（建议，待负责人改定）

```yaml
# Claude offline attribution (review-claude.md §3.4); original judge scores are unchanged.
# This is not independent human calibration.
Bazi-single:
  bazi_pilot_investment_risk#1:
    - 叙述类
  bazi_pilot_typed_birth#3:
    - 叙述类
  bazi_pilot_investment_risk#3:
    - 叙述类
Bazi-pipeline: {}
```

- **single 投资 #1、文字出生 #3**：把行为和关系场景写成用户已知或必然的事，叙述类。
- **single 投资 #3**：
  - 评委说“证据中并无甲辰大运”属误读：dayun.sequence 里第 4 步就是甲辰（2026 年交运），current_candidates 也同时列了癸卯、甲辰。
  - “2026年底起进入甲辰大运”把交运年份说成“年底起”，这比事实具体，但无法核验为错，按叙述类计。
  - 其余是把经历写成已知。

按此改定后，single 叙述类 3/15（20.0%）、事实类 0；流水线 0/18。

### 3.5 逐份复核

**投资题**：

- **#1**：
  - 第一层“这一段更适合先整理账户、留出备用金，把决定放慢”是核实。
  - 第二层“这段时间更适合做功课、定规则、留余量，而不是把积蓄集中押上”是核实和克制。
  - 第四层“年底更适合复盘和修补，而不是补仓或加码”是克制。
  - 第三层“任何操作都设好上限”按负责人决定放行。
- **#2**：
  - 摘要的“分散”见 §3.2。
  - 第三层“这段时间尤其要克制‘先投了再说’的念头，把决定往后放一放”是收着。
  - 建议“分散核实”没有时间词，讲的是核实，放行。
- **#3**：关键词稿（§3.1）。

**时机题**：

- 事业三份 12 月 7 日换月。标题“12月上旬”“12月开头几天”“12月1日起”写的是己亥（至 12 月 7 日），都在口径内。#2 摘要“中旬之后更偏向有序推进”是概述，后面不紧接流月，与 r13 海外 #3 的先例相同，放行。
- 海外三份按洛杉矶时间 12 月 6 日换月，标题都对；#2 摘要“中旬后转向协调”同上。
- 文字出生三份：“7月7日之后 / 起”“8月7日起”“9月7日起”“10月8日起”“11月7日起”“12月7日起”都对；标题“7月到8月初”“8月到10月初”“10月到年底”在口径内。
- 没有春节。

**大运题**：

- 三份都写虚岁 6 岁、1993-02-10 起运、顺排、当前第 4 步己未、第 4 年 / 前半段，都对。
- #1“前一步是第3步大运戊午，2013年交运；下一步是第5步庚申，2033年交运”对。
- #2 计数概括“木土偏多”对。
- #3“日主乙木为日主”属已定的显示缺陷。

**性格题**：
- #1“你现在走在己巳这步大运的后半段”对。
- #2、#3 的计数概括“分布较匀”与木2、火1、土1、金2、水2 一致。
- 没有首步当成现在，也没有约定编号写在大运位置。

## 4. r1–r16 已修问题是否再现

| 问题 | r17 | 依据 |
| --- | --- | --- |
| 分批、试探投入等推荐的投入方式（r12–r15） | **换了词再现** | 投资 #2“分散”（§3.2） |
| 十神检查误拒（新） | **出现** | 投资 #3（§3.1） |
| 相邻十年（r16）、“稳赚”提及（r16） | 未再现 | — |
| 字面编号、重复标签、标题时间 | 首稿拦下，一次修好 | 性格 #1、投资 #3 |
| 首步当成现在、约定写在大运位置、计数概括、十神归纳、正文起点、立春、春节、虚岁、大运位置、顺逆排 | 未再现 | — |

## 5. r18 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 天干的十神（`STEM_GOD_BEFORE`，`pipeline/bazi.py`） | 十神紧跟在“天干X为 / 是”之后时，是这个天干对日主的十神，按 `ten_god` 直接核对；不再因分句前面出现“地支”就转去核对藏干。“天干X不为……”这类否定也读出 |
| 分散（`BATCH`） | 推荐词带出的“分散”（投资、配置、管理资金）与分批、小步验证一样处理：句内有时间词，或所在一层的标题写了时间，就拒；“注意力 / 精力 / 心思分散”不算 |

题集、rubric、评委配置、`*_final.yaml`、留出集断言都没有改；共用规则没有改；既有测试一条没改。

**天干的十神**：

- 修订版**仍拒**：
  - 同一句后面另写地支藏干里的偏财；
  - 写成“时柱辛亥地支亥里藏着偏财”（藏干写法照旧核对）；
  - 先否定后肯定、外层否定“不能说时柱的地支里没有偏财”、程度词“完全有偏财”、转折后重新肯定。
- **新拒**：天干写错的十神，“（天干辛为正财）”“（天干丙为偏财）”“（天干辛为七杀）”，以及否认正确值的“（天干辛不为偏财）”。改动前，这类写法在关系事实后面被当成藏干，在其他位置只核对“命局里有没有这个十神”。
- **仍放行**：r17 投资 #3 原句；“与时柱辛亥（天干辛为偏财）有天干合”。

**分散**：

- 新拒：“明年更适合分散投资”“明年建议分散配置，留足底线”“明年以分散为主”、外层否定“不能说明年不适合分散投入”、双重否定“不是不建议分散配置”、转折后重新肯定“明年不宜全投，但其实适合分散投入”。
- 仍放行：“明年不适合分散投资，也不适合全投”“注意力容易分散”“更适合把精力分散到学习和工作上”、r8 的“把‘全投’换成‘分批、留底、按预算’更稳妥”、r17 投资 #1 的“任何操作都设好上限”。

**端到端**：投资 #3 的两份原稿依次作为首稿和第二稿，修订版上修复 1 次、调用 2 次、不降级；修复请求只引出首稿的标题问题。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和 `tests/pipeline/fixtures/bazi_pilot_r17_review.json` 放进 `82619a9` 的独立 worktree 运行：25 项中 12 项以断言失败（全部是 AssertionError，没有导入错误），13 项两边都通过。
- 修订版 25 passed；r16、r17 的测试也都通过（共 138 项）。

**对历史回答的影响**（只用规则扫描回答文本，不重评）：r1–r17 全部归档（612 份成稿逐句、逐层，83 份被检稿件整稿）在两个版本上各重放一遍，8 处结果不同，都在预期内：

- **r17 的 5 处**：投资 #2 摘要新拒；投资 #3 两稿不再报藏干，首稿只剩标题问题。
- **更早推荐“分散”的 3 处**，按负责人 2026-11-15 的口径应拒：
  - r4 投资 #2 摘要“明年整体不宜把积蓄全部投入股市，财务安排上更适合分散、留足安全垫、按节奏配置”；
  - r7 single 投资 #3“明年暂不适合把全部积蓄投进股市，更适合小额、分散、有上限的尝试”（成稿和首稿）。
- **另 2 处是去掉的误命中**：r11 投资 #1、r16 投资 #3 的降级稿（代码写的依据列表）里，“日柱丁亥地支亥- 时柱辛亥（天干辛为偏财）”原本也会被当成藏干。降级稿是代码写的，运行时不过这道检查，所以不影响当时的结果。

**全量测试**：见 PR 说明。

## 6. 负责人决定（2026-11-15）

| 问题 | 决定 | 落实 |
| --- | --- | --- |
| r17 结果的合并 | 负责人先合并 PR #79 | 本 PR 基于 `18f20dc` |
| 投资 #2“更适合以保守、分散、先保生活底线的方式管理资金” | 算放过，r18 补拒 | `BATCH` |
| 投资 #1“任何操作都设好上限” | 不算，属限制和克制 | 不改 |

## 7. r18 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行，接入与 r15–r17 相同。`docs/verification/p3/bazi-pilot-r18/pricing.yaml` 已放好，与 r17 逐字节相同（`15ea038e…`）。

```powershell
Copy-Item config.yaml reports/config.personal.before-r18.yaml
```

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pathlib; b = pathlib.Path('docs/verification/p3/bazi-pilot-r17/config.experiment.yaml').read_bytes().replace(b'\r\n', b'\n'); pathlib.Path('config.yaml').write_bytes(b.replace(b'\n', b'\r\n'))"
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne 'CA6E52B208B6697DE7A7B8ACCC58604EB87E1A89EAB582DBC4937C138624BAB1') { Copy-Item reports/config.personal.before-r18.yaml config.yaml; throw 'config.yaml 不是约定配置 ca6e52b2' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r18.yaml config.yaml; throw '服务端探针未通过，暂停 r18' }
```

```powershell
if (Test-Path reports/p3-bazi-r18) { Move-Item reports/p3-bazi-r18 ("reports/p3-bazi-r18-old-" + (Get-Date -Format yyyyMMddHHmmss)) }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r18 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r18
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r18/Bazi-single reports/p3-bazi-r18/Bazi-pipeline --answers --output reports/p3-bazi-r18/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r18/Bazi-single reports/p3-bazi-r18/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r18/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r18/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r18/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r18/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r18.yaml config.yaml
```

- 探针结果存为 `docs/verification/p3/bazi-pilot-r18/service-probe.json` 一并发布，execution.md 记下接入地址和模型名。
- 照 r17 的范围首发证据：36 份全文、repair-evidence.json、repair-quotes.json；evidence-manifest 按入库后的字节生成。
- execution.md 里报两组评委和运行的输出 token 中位数（按行、按单次调用）以及耗时中位数。
- **single 的编造失败请在发布前判定。** r15–r17 的 single 计数表都因待判定而“不完整”，这一条单独就能挡住 B。可参照各轮复核 §3.4 的口径（把经历写成已知的计叙述类，评委理由没有指出可核验错误的按评委误读计叙述类），把判定写进 `fabrication-reviewed.yaml` 后再生成计数表。
- r17 的 single 计数表如要改定，用 §3.4 的 YAML 对 r17 的本机报告目录重跑 `--counts-only --reviewed`，输出到 `docs/verification/p3/bazi-pilot-r17/fabrication-counts.md`。
- r18 结果里请继续逐份看：投资题有日期的一层和摘要里的分批、试探、分散写法；时机题正文时间；大运题的前后步、岁数、所处位置和五行计数的概括；性格题里“现在”所指的大运。

**若 r18 满足 B**，下一步是在计划里记“八字代码冻结于 r18 的被测提交”，再按约定跑最终验收集 `p3-bazi-final`（命令届时在 r18 复核里给出）。

## 8. 已知局限

| 局限 | 处理 |
| --- | --- |
| 推荐的投入方式只认词表（分批、分次、定投、小范围 / 小步验证、试水、分散） | 其他写法仍靠逐份看投资题 |
| 天干十神只在紧跟“天干X为 / 是”时按天干核对 | 其他写法仍按原有的柱位、藏干和命局范围核对 |
| 显示缺陷（“日主乙木为日主”、同一编号写两遍、“地支X地支X”） | 按负责人决定，留到主集前 |
| 共用确定性检查 `certainty_claim` 的误拒 | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
| `74acc5a` 改了入库的 config.yaml | `tests/knowledge/test_live_review_regressions.py` 3 项自 `966eb22` 起失败（r15 复核 §8），待负责人决定 |
