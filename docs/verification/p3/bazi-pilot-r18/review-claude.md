# P3 八字调参集 r18 复核：不满足 B，r19 修复后重跑

负责人发布的文件不改；本文件按 r12 复核和 r13–r17 的 review-claude.md 的写法补充复核。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 r18 结果（`6f62d7e`，直接提交在 `claude_modify_model`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[run-metadata.json](run-metadata.json)、[config.experiment.yaml](config.experiment.yaml)、[service-probe.json](service-probe.json)、[integrity.json](integrity.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[pipeline-problem-counts.md](pipeline-problem-counts.md)、[fabrication-counts.md](fabrication-counts.md)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[supplement-answers.md](supplement-answers.md)、[supplement-answers.json](supplement-answers.json)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json) |
| 被测代码 | `41d3efd1039b2cd7aa605573177e5f616eb28161`，即 PR #80 合并；源码指纹 `aceae1461352546d9d3d53608204f52df536f412038f76c0e4d390755caf1a33` |
| 接入与配置 | 约定：官方 `https://api.deepseek.com`，运行与评委都是 `deepseek-flash`，实验配置 `ca6e52b2…`；评委 thinking=disabled、不设 reasoning_effort、max_tokens=8192 |
| 方法 | 离线：重算指纹，在 `41d3efd` 的独立 git worktree 里按 `scripts/live_week23.py` 的取样范围逐文件对照；核对模型、配置、raw_sha256、evidence-manifest 和评分；repair-evidence.json 的 5 份被检稿件（本轮的未展开原稿在该文件的 `text` 字段，repair-quotes.json 只有引句）在 `41d3efd` 上按 r18 运行时钟（`20261115T121114`）整稿重放；18 份流水线成稿按结构逐句、逐层重放；逐份看 18 份流水线成稿和 single 的 2 份编造失败。r19 的改动用 r1–r18 全部归档回答（648 份成稿逐句、逐层，88 份被检稿件整稿）在两个版本上各重放一遍。没有改共用规则，没有调用模型 |
| 日期 | 2026-11-16 |

## 1. 结论

**不满足 B，不冻结。** 负责人的 [assessment.md](assessment.md) 以计数表待判定为由不冻结。我同意，并另补六处已知放过，其中三处是事实类：

- **已知放过，事实类 3 份**：
  - **性格 #1**：“你正处在……首步大运辛未（1997年交运，2007年换下一步）所说的这一步大运中，按逆排走到后半段”。2026 年所在的是己巳，首步大运又被当成了现在。
  - **大运 #1**：“第1步大运丙辰天干丙为伤官是上一步大运的主题”。前一步是第 3 步戊午。
  - **大运 #2**：“此后每一步依次接续，前一步是日柱乙亥地支亥所在那一步”。原局的柱被写成大运。
- **负责人 2026-11-16 判为放过的 3 处**：
  - **大运 #3（事实类）**：“2033年接上的第5步大运庚申，主题会转向创新与质疑”。庚对乙是正官，“创新与质疑”是伤官的主题。
  - **文字出生 #1**：“9月上中旬流月丁酉与本命月柱庚辰地支六合（9月7日至10月8日）”。
  - **投资 #1（交易边界）**：标题“5月到8月”那一层写“……只用小比例、可承受损失的部分去验证判断”。
- **两组计数表都不完整**：single 2 条、流水线 1 条待判定。本复核给出建议判定（§3.4）。

流水线其余表现良好：
- 提交 18/18、调用最多 2 次、修复 5、降级 0；
- 已提交质量 15/18（83.3%）高于 single 的 12/15（80.0%），P1 四条满足；
- 5 份被检稿件都是真问题，没有误拒。

| B 条件 | r18 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 23 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 计数表待判定；另有 4 份已知放过的事实类（§3.2） |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 降级 0，5 次修复都是真问题（§3.1） |
| 没有已知放过 | **不满足** | §3.2 |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 15/18（83.3%）对 12/15（80.0%） |
| （前提）约定接入与配置 | 满足 | §2 |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 4 份：性格 #1、大运 #1、大运 #2、大运 #3（都是已知放过） | 0（建议判定） |
| 叙述编造（不高于 single，争取 ≤ 10%） | 建议 1/18（5.6%）：投资 #1，评委误读 | 建议 2/15（13.3%） |
| `time_consistent` 失败 | 2（文字出生 #2、投资 #2，都是评委误读） | 3 |
| 降级比例（≤ 10%，监控项） | 0/18 | — |
| 每题模型调用（≤ 3） | 约 1.28（23/18），最多 2 | 约 6.28（113/18），最多 11 |
| 每题输入 token（≤ 20,000，不含评委） | 约 6,563 | 约 45,445 |
| P95 耗时（≤ 90 秒） | 13.6 秒 | 41.3 秒 |
| 已提交回答质量通过率 | 15/18（83.3%） | 12/15（80.0%） |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-flash`，同模型评分，不是独立评审。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，184 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `aceae146…`，与 execution.md、两份 summary、run-metadata.json 一致 |
| 被测提交 | 按 `scripts/live_week23.py` 的取样范围在 `41d3efd` 的 worktree 重新列出 184 项，与 source-hashes 的键完全相同；除 config.yaml 外 183 项逐文件一致。`41d3efd..6f62d7e` 只加了本目录 |
| config.yaml 一项 | `ca6e52b2…`；入库的 config.experiment.yaml 为 LF（`2ec411fa…`），换成 CRLF 即 `ca6e52b2…` |
| 接入与模型 | run-metadata.json：官方 `https://api.deepseek.com`；两组 36 行运行和 36 条评分的 requested/returned 都只有 `deepseek-flash` |
| 探针 | [service-probe.json](service-probe.json) 三项通过 |
| raw 与发布文件 | 两组 raw_sha256 与 raw-manifest 一致；trace-manifest 36 条 |
| evidence-manifest | 列 26 个文件，按入库后的字节逐一相符；目录里只有 evidence-manifest.json 自身不在其中（不含本文件） |
| pricing.yaml | `15ea038e…`，与 r17 逐字节相同 |
| 评分完整性 | 两组 18/18 评分，没有未评分行，评委请求各 18 次，没有解析重试；单行评委输出最多 722（pipeline）、635（single） |
| 提交状态 | 流水线 18 条全部提交，修复 5、降级 0、工程 18/18。single 15 条提交，3 条 ask_user（海外 #1–#3） |
| 被检稿件 | 本轮 repair-quotes.json 只列引句，未展开原稿在 repair-evidence.json 的 `text`、展开稿在 `rendered_text`；重放据此进行 |

**服务端行为**（按行的中位数）：评委每行输出 pipeline 355、single 381；运行每次调用（每行输出 ÷ 调用数）pipeline 682.5、single 400.4；每题耗时 pipeline 6.9 秒、single 15.4 秒，与 r13、r15–r17 一致。

## 3. 归因

### 3.1 修复和误拒

5 份被检稿件在 `41d3efd` 上按 r18 运行时钟整稿重放，问题与 repair-evidence.json 逐字一致，修复请求都引出了原句，**都是真问题，没有误拒**：

| 稿件 | 问题 |
| --- | --- |
| 大运 #2 首稿 | 摘要引了不存在的 R13；“第一步大运第1步大运”“日主是日主”“日柱为日柱”重复 |
| 大运 #3 首稿 | 时柱、日柱重复；“前一步子时按23点换日性质的说明……”（约定写在大运位置）；“下一步第1步大运丙辰”（后一步是第 5 步庚申） |
| 文字出生 #2 首稿 | “中旬起流月乙未”（乙未 7 月 7 日起） |
| 投资 #2 首稿 | 标题“下半年到年底”，正文有 6 月 6 日起的流月丙午 |
| 海外 #3 首稿 | 标题“12月6日起”，正文有 12 月 1—6 日的流月己亥 |

### 3.2 已知放过

18 份成稿在 `41d3efd` 上按结构逐句、逐层重放，全部没有问题；下面几处都是检查放过、评委也判通过的。

**性格 #1（事实类）**

> 你正处在1997年9月27日起运（出生后3年1个月10天），首步大运辛未（1997年交运，2007年换下一步）所说的这一步大运中，按逆排走到后半段……

r15 的首步当成现在检查要求“现在 / 目前……处在”，且首步大运后紧接“这一步”；这里只有“正处在”，中间又隔了“所说的”。

**大运 #1（事实类）**

> 往前看，第1步大运丙辰天干丙为伤官是上一步大运的主题……

相邻大运检查只认“前一步 / 上一步……是X”，不认先写X、再说它“是上一步”。

**大运 #2（事实类）**

> ……此后每一步依次接续，前一步是日柱乙亥地支亥所在那一步。

首稿同句已因重复标签被拒；修复稿保留了这句，原局的柱被写成了前一步大运。r4 的“大运层面有年柱丙寅”是同类（原局柱叫作大运）。

**大运 #3（事实类，负责人 2026-11-16 决定）**

> 2033年接上的第5步大运庚申，主题会转向创新与质疑，届时提出改进要同时给出依据……

首稿“下一步第1步大运丙辰天干丙为伤官从2033年换运，主题会转向创新与质疑”被拦下。修复稿把大运换成了对的第 5 步庚申，却留着伤官的主题；庚对乙是正官，主题是职责与规范。

**文字出生 #1（负责人 2026-11-16 决定）**

> 9月上中旬流月丁酉与本命月柱庚辰地支六合（9月7日至10月8日）和……都指向联结和协调

“9月上中旬”紧接流月丁酉的关系事实；丁酉 9 月 7 日起，比“上中旬”晚 6 天，又有大半在 9 月 21 日以后。正文起点检查只认“X旬之后 / 起 / 到……”紧接流月。

**投资 #1（交易边界，负责人 2026-11-16 决定）**

> 三、5月到8月：变动集中，最忌全押
> ……这段时期波动感偏强，不建议把积蓄全部投入；更稳妥的是保留大部分现金和应急资金，只用小比例、可承受损失的部分去验证判断。

在有日期的一层里，用一小部分资金去验证，是给这段时间推荐试探投入。没有“适合 / 建议”这类推荐词，检查没认出。r13 的“更稳妥的做法是……先用小步验证自己的判断”验证的是判断、不是资金，负责人当时判为不算。

**负责人决定不算放过**：投资 #3 标题“6月到年底：起伏明显，克制冲动、分批思考”。

**其他观察（不计放过）**：
- 投资 #1 建议“用小步验证：想尝试就用小比例、可承受损失的部分”、投资 #3 建议“如果参与，提前写下投入上限、止损条件和退出计划”，都没有时间词，按口径放行；
- 事业 #1 摘要的“前半段 / 后半段”是概述；
- 大运 #1、#2“日主乙木为乙木”是已定的显示缺陷。

### 3.3 质量失败

| 样本 | 维度 | 核对 | 类别 |
| --- | --- | --- | --- |
| 投资 #1 | fabricated | 评委自己写“部分以‘可能/如果’条件句出现，属允许写法……整体仍可用条件句解释，故判为false偏严”，没有指出可核验的错误 | 叙述类（评委误读） |
| 投资 #2 | time | 评委说“流年丁未（……至2028年1月1日00:00）”“地支害至12月31日”与立春换年不符；两处都是代码按查询范围（2027 年）截断的流期和关系日期 | 评委误读，不属编造 |
| 文字出生 #2 | time | 评委说“丑午相害”标为 7 月 1 日至 12 月 31 日而丙午覆盖全年；这是代码按“今年下半年”截断的关系日期 | 评委误读，不属编造 |

### 3.4 编造分类（建议，待负责人改定）

```yaml
# Claude offline attribution (review-claude.md §3.4); original judge scores are unchanged.
# This is not independent human calibration.
Bazi-single:
  bazi_pilot_typed_birth#2:
    - 叙述类
  bazi_pilot_typed_birth#3:
    - 叙述类
Bazi-pipeline:
  bazi_pilot_investment_risk#1:
    - 叙述类
```

- **single 文字出生 #2、#3**：把合冲、十神落到具体感情事件和用户表现上，叙述类。#3 的“2027年进入甲申大运”与交运年份一致，没有写错。
- **流水线投资 #1**：§3.3。

按此改定后：流水线计数表事实类 0、叙述类 1/18（5.6%），另有 4 份已知放过的事实类；single 事实类 0、叙述类 2/15（13.3%）。

### 3.5 逐份复核

**投资题**：

- **#1**：
  - 第一层“先把它当成核实成本的阶段”是核实；
  - 第二层“先把功课做足，而不是急着把积蓄一次性放进去”是克制；
  - 第三层的“小比例”见 §3.2；
  - 第四层“把财务底盘打牢”。
- **#2**：
  - 第一层“先分清哪些钱是生活底线”、第二层“先核实财务状况和风险承受能力”都是核实；
  - 建议“春季适合补理财常识和风险知识”不是交易。
- **#3**：
  - 第一层“剩下的部分再谈配置”是先后次序，没有推荐交易；
  - 第三层标题的“分批思考”按负责人决定放行；
  - 建议“如果参与，提前写下投入上限、止损条件和退出计划”没有时间词。

**时机题**：
- 事业、海外六份的换月日（北京时间 12 月 7 日、洛杉矶时间 12 月 6 日）和标题都对。
- 文字出生 #1 的“9月上中旬”见 §3.2。
- 文字出生 #2 的标题“7月”“8月到9月上旬”“9月到10月上旬”“10月到11月上旬”“11月到年底”与各层流月一致。
- 没有春节。

**大运题**：
- 三份都写虚岁 6 岁、1993-02-10 起运、顺排、当前第 4 步己未、第 4 年 / 前半段，都对。
- 计数概括“木和土出现较多，火与金没有出现，水只有一处”“土的数量偏多、火金缺位”对。
- 前后步和主题见 §3.2。

**性格题**：
- #1 见 §3.2。
- #2“五行较均衡”、#3“木2、火1、土1、金2、水2，木与水都不算少”与计数一致。
- 没有约定编号写在大运位置。

## 4. r1–r17 已修问题是否再现

| 问题 | r18 | 依据 |
| --- | --- | --- |
| 首步当成现在（r3、r13、r15） | **换了写法再现** | 性格 #1（§3.2） |
| 相邻大运（r11、r16） | **换了写法再现** | 大运 #1“X是上一步”（§3.2）；大运 #3 首稿拦下 |
| 原局柱叫作大运（r4） | **换了写法再现** | 大运 #2（§3.2） |
| 十神写错（r7、r17） | **换了形式再现** | 大运 #3 的主题（§3.2） |
| 正文起点（r8、r13） | **换了写法再现** | 文字出生 #1“9月上中旬流月丁酉”（§3.2）；#2 首稿“中旬起”拦下 |
| 试探投入（r7、r14、r15） | **换了写法再现** | 投资 #1“只用小比例……去验证”（§3.2） |
| 约定写在大运位置、重复标签、标题时间 | 首稿拦下，一次修好 | §3.1 |
| 天干十神、分散、“稳赚”提及、计数概括、立春、春节、虚岁、大运位置、顺逆排 | 未再现 | — |

## 5. r19 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 首步当成现在（`PRESENT_STAGE`） | 只有“正处在 / 正走在”也算“现在”；首步或第 N 步大运后允许“所说 / 所指 / 对应 / 代表的”再接“这一步 / 这步大运 / 这一阶段” |
| 先写大运再说它是前后步（`NEIGHBOUR_NAMED_FIRST`） | “第N步大运X（……）（天干X为……）（的主题）是 / 为上（下）一步”，X 要是当前大运的相邻一步；读其前的否定和外层否定 |
| 原局柱当前后步（`NATAL_AS_NEIGHBOUR`） | “前一步 / 下一步……是 / 为（本命）X柱YY”拒 |
| 大运的主题（`DAYUN_THEME`） | “第N步大运X（……），主题（会 / 将）转向 / 转为 / 是 / 为 + 十神主题”，主题要与 X 的天干对日主的十神一致（主题取自十神释义：职责与规范、创新与质疑……）。为保持既有测试不变，“主题偏向……”不在其内 |
| 写了月份的“X旬”紧接流月（`bare_part_findings`） | “9月上中旬流月丁酉……”这类写法：流月在查询范围内的日子落在这段里（标题口径），或这段落在流月里（“十一月下旬，流月己亥……”），各留 2 天，否则拒。没写月份的“月初 / 月末”和“7月7日到8月初”这类区间终点不在其内 |
| 用小部分资金去试（`TRIAL_FUNDS`） | “只用 / 用 / 拿出（一）小比例 / 小部分 / 少量 / 小额……资金 / 钱 / 积蓄 / 部分……去验证 / 试 / 尝试 / 参与 / 投入”，句内有时间词或所在一层有日期就拒；前面有“不要 / 别 / 不建议……”的放行，外层否定、双重否定仍拒 |

题集、rubric、评委配置、`*_final.yaml`、留出集断言都没有改；共用规则没有改；既有测试一条没改。

**新拒的守卫**（`tests/pipeline/test_bazi_pilot_r19.py`）：

- **首步当成现在**：
  - 拒“你正处在首步大运辛未（……）所指的这一步大运中”；
  - 放行“你正处在第3步大运己巳（……）所说的这一步大运中”“你在首步大运辛未（……）所说的这一步大运里打下了底子”。
- **先写大运再说前后步**：
  - 拒“第2步大运丁巳是上一步”“第1步大运丙辰是下一步大运”，以及否认正确值的“第3步大运戊午不是上一步”；
  - 放行“第3步大运戊午天干戊为正财是上一步大运的主题”“第5步大运庚申是下一步”“第1步大运丙辰不是上一步”。
- **原局柱**：放行“前一步是第3步大运戊午”“前一步不是日柱乙亥”“日柱乙亥地支亥与前一步大运无关”。
- **主题**：放行“第5步大运庚申，主题会转向职责与规范”“第4步大运己未（……），主题是机会与调配”“第1步大运丙辰的主题是创新与质疑”。
- **X旬**：放行“7月上旬流月甲午提示责任”“9月7日起流月丁酉……”“9月上中旬多留意情绪，流月丁酉的主题是探索”（流月不紧接）。
- **小部分资金**：
  - 拒“这段时间只用小额资金去尝试”“这段时间可以拿出一小部分积蓄去试水”，外层否定“不能说不要用小比例资金去验证”、双重否定“不是不建议用小部分钱去试”、转折后“不要全投，但可以用小部分钱去试”；
  - 放行“这段时间不要用小比例资金去试”“别只用小部分钱去验证，先把账算清楚”“用小部分时间去验证想法”、r13 的“先用小步验证自己的判断”、没有时间词的建议。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和 `tests/pipeline/fixtures/bazi_pilot_r18_review.json` 放进 `41d3efd` 的独立 worktree 运行：35 项中 16 项以断言失败（全部是 AssertionError，没有导入错误），19 项两边都通过。
- 修订版 35 passed；八字相关测试（r2–r19、标题、交易、runner、`test_gain_policy.py`）都通过。

**对历史回答的影响**（只用规则扫描回答文本，不重评）：r1–r18 全部归档（648 份成稿逐句、逐层，88 份被检稿件整稿）在两个版本上各重放一遍，14 处结果不同，都在预期内：

- **r18 的 7 处**：§3.2 的六句成稿新拒（投资 #1、文字出生 #1 是层级检查报出）；大运 #2 首稿另报原局柱。
- **更早用小部分资金去试的 2 句**，按负责人 2026-11-16 的口径应拒：
  - r3 投资 #2“年初和年中几段……更适合用小比例资金验证策略，把大部分积蓄留在安全垫里”；
  - r1 投资 #3“（8 月到 9 月）……适合用少量资金做尝试、记录结果”。
- **更早写了月份的“X旬”紧接流月的 2 句**，按同一口径应拒：
  - r1 文字出生 #3“8月上中旬流月丙申”（丙申 8 月 7 日起，早 6 天）；
  - r3 文字出生 #1“9月上旬流月丙申”（丙申到 9 月 7 日，“上旬”多出 3 天，刚超过 2 天，属边界）。
- **另 3 处是被检稿件里同一问题报了两次的顺序差异**，问题集合不变。

**全量测试**：见 PR 说明。

## 6. 负责人决定（2026-11-16）

| 问题 | 决定 | 落实 |
| --- | --- | --- |
| 投资 #1“只用小比例、可承受损失的部分去验证判断” | 算放过，r19 补拒 | `TRIAL_FUNDS` |
| 投资 #3 标题“克制冲动、分批思考” | 不算 | 不改 |
| 大运 #3“第5步大运庚申，主题会转向创新与质疑” | 算放过（事实类），r19 补拒 | `DAYUN_THEME` |
| 文字出生 #1“9月上中旬流月丁酉……” | 算放过，r19 补拒 | `bare_part_findings` |

## 7. r19 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行，接入与 r15–r18 相同。`docs/verification/p3/bazi-pilot-r19/pricing.yaml` 已放好，与 r18 逐字节相同（`15ea038e…`）。

```powershell
Copy-Item config.yaml reports/config.personal.before-r19.yaml
```

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pathlib; b = pathlib.Path('docs/verification/p3/bazi-pilot-r18/config.experiment.yaml').read_bytes().replace(b'\r\n', b'\n'); pathlib.Path('config.yaml').write_bytes(b.replace(b'\n', b'\r\n'))"
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne 'CA6E52B208B6697DE7A7B8ACCC58604EB87E1A89EAB582DBC4937C138624BAB1') { Copy-Item reports/config.personal.before-r19.yaml config.yaml; throw 'config.yaml 不是约定配置 ca6e52b2' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r19.yaml config.yaml; throw '服务端探针未通过，暂停 r19' }
```

```powershell
if (Test-Path reports/p3-bazi-r19) { Move-Item reports/p3-bazi-r19 ("reports/p3-bazi-r19-old-" + (Get-Date -Format yyyyMMddHHmmss)) }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r19 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r19
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r19/Bazi-single reports/p3-bazi-r19/Bazi-pipeline --answers --output reports/p3-bazi-r19/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r19/Bazi-single reports/p3-bazi-r19/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r19/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r19/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r19/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r19/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r19.yaml config.yaml
```

- 探针结果存为 `docs/verification/p3/bazi-pilot-r19/service-probe.json` 一并发布，execution.md 记下接入地址和模型名。
- 照 r18 的范围首发证据：36 份全文、repair-evidence.json（含未展开原稿的 `text`）、repair-quotes.json；evidence-manifest 按入库后的字节生成。
- execution.md 里报两组评委和运行的输出 token 中位数（按行、按单次调用）以及耗时中位数。
- **请在发布前判定编造失败。** r15–r18 的计数表都因待判定而不完整，单这一条就挡住 B。可按各轮复核 §3.4 的口径判定，写进 `fabrication-reviewed.yaml` 后再生成计数表。
- r18 的计数表如要改定，用 §3.4 的 YAML 对 r18 的本机报告目录重跑 `--counts-only --reviewed`，输出到 `docs/verification/p3/bazi-pilot-r18/fabrication-counts.md`。
- r19 结果里请继续逐份看：
  - 投资题有日期的一层里推荐的分批、分散、试探写法（含“用小部分资金去试”）；
  - 时机题正文时间（含写了月份的“X旬”紧接流月）；
  - 大运题的前后步（含“X是上一步”）、主题与十神、岁数、所处位置和五行计数的概括；
  - 性格题里“现在”所指的大运。

**若 r19 满足 B**，下一步是在计划里记“八字代码冻结于 r19 的被测提交”，再按约定跑最终验收集 `p3-bazi-final`（命令届时在 r19 复核里给出）。

## 8. 已知局限

| 局限 | 处理 |
| --- | --- |
| 大运主题只核对“主题（会 / 将）转向 / 转为 / 是 / 为……”，不核对“主题偏向……” | 既有 r12 测试的合成句“第3步大运戊午，主题偏向竞争与共享”须放行，按约定不改既有测试；其他写法仍靠逐份看 |
| 写了月份的“X旬”紧接流月按两种方向留 2 天，r3 的“9月上旬流月丙申”刚好超出 1 天 | 若负责人认为这类边界应放行，可把这一检查的余量放宽 |
| 小部分资金的试探只认列举的说法 | 其他写法仍靠逐份看投资题 |
| 显示缺陷（“日主乙木为乙木”、同一编号写两遍、“地支X地支X”） | 按负责人决定，留到主集前 |
| 共用确定性检查 `certainty_claim` 的误拒 | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
| `74acc5a` 改了入库的 config.yaml | `tests/knowledge/test_live_review_regressions.py` 3 项自 `966eb22` 起失败（r15 复核 §8），待负责人决定 |
