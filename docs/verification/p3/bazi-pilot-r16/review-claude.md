# P3 八字调参集 r16 复核：不满足 B，r17 修复后重跑

负责人发布的文件不改；本文件按 r12 复核和 r13–r15 的 review-claude.md 的写法补充复核。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 r16 结果（`a581161`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[run-metadata.json](run-metadata.json)、[config.experiment.yaml](config.experiment.yaml)、[service-probe.json](service-probe.json)、[integrity.json](integrity.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[supplement-answers.md](supplement-answers.md)、[supplement-answers.json](supplement-answers.json)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json) |
| 被测代码 | `5640889a3bbfe22f2885ed57e8672e0023fa3873`，即 PR #76 合并（含负责人的 `2044015`）；源码指纹 `05138a2ad01f20f0cfe2c264ee7d8018528761d66073e5f4fe500f46516b2007` |
| 接入与配置 | 新约定：官方 `https://api.deepseek.com`，运行与评委都是 `deepseek-flash`，实验配置 `ca6e52b2…`；评委 thinking=disabled、不设 reasoning_effort、max_tokens=8192 |
| 方法 | 离线：重算指纹，在 `5640889` 的独立 git worktree 里按 `scripts/live_week23.py` 的取样范围逐文件对照；核对模型、配置、raw_sha256、evidence-manifest 和评分；repair-quotes.json 的 4 份被检稿件（未展开原稿）在 `5640889` 上按 r16 运行时钟（`20261114T064934`）整稿重放；18 份流水线成稿按结构逐句、逐层重放；逐份看 18 份流水线成稿和 single 的 6 份编造失败。r17 的改动用 r1–r16 全部归档回答（576 份成稿逐句、逐层，80 份被检稿件整稿）在两个版本上各重放一遍；共用规则的改动另用 docs/verification 下全部体系含“稳赚”的 231 句对比。没有调用模型 |
| 日期 | 2026-11-14 |

## 1. 结论

**不满足 B，不冻结。** 我同意负责人在 [assessment.md](assessment.md) 里的判断。服务端行为稳定，与 r13、r15 相当。流水线提交 18/18、调用最多 2 次，已提交质量 13/18（72.2%）高于 single 的 8/14（57.1%），P1 四条满足。没有满足的有三条：

- **造成失答的误拒 1 处**：投资 #3 两稿都被共用 `hard_claim` 拒成“不能给出健康、投资或生死的确定性结论”，降级为安全回复“这次不作解读”。触发句都是被质疑、被劝阻的“稳赚”提及，规则没认出来（§3.1）。
- **已知放过 1 处（事实类）**：大运 #1 首稿“前一步是第1步大运丙辰”被正确拦下，修复稿改写成“走到这一步之前的那十年，天干为第1步大运丙辰天干丙为伤官”。前一步是第 3 步戊午，同一错误换了说法，检查放过（§3.2）。
- **计数表不完整**：single 6 条、流水线 1 条待判定。本复核给出建议判定（§3.4），由负责人改定后重新生成。

| B 条件 | r16 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 21 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 计数表待判定；按建议判定，计数表事实类 0，但大运 #1 是已知放过的事实类 |
| 没有造成降级、失答或质量失败的可定位误拒 | **不满足** | 投资 #3（§3.1） |
| 没有已知放过 | **不满足** | 大运 #1（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 13/18（72.2%）对 8/14（57.1%） |
| （前提）约定接入与配置 | 满足 | 官方 `deepseek-flash`，`ca6e52b2…`（§2） |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 1 份：大运 #1（已知放过） | 0（建议判定） |
| 叙述编造（不高于 single，争取 ≤ 10%） | 建议 1/18（5.6%）：投资 #2，评委误读 | 建议 6/14（42.9%） |
| `time_consistent` 失败 | 4（海外 #1、投资 #2、文字出生 #3 是评委误读；文字出生 #2 是标题宽于正文，§3.3） | 1 |
| 降级比例（≤ 10%，监控项） | 1/18（5.6%）：投资 #3（误拒，失答） | — |
| 每题模型调用（≤ 3） | 约 1.17（21/18），最多 2 | 约 6.89（124/18），最多 12 |
| 每题输入 token（≤ 20,000，不含评委） | 约 6,005 | 约 43,649 |
| P95 耗时（≤ 90 秒） | 12.2 秒 | 26.1 秒 |
| 已提交回答质量通过率 | 13/18（72.2%） | 8/14（57.1%） |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-flash`，同模型评分，不是独立评审。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，184 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `05138a2a…`，与 execution.md、两份 summary、integrity.json 一致 |
| 被测提交 | 按 `scripts/live_week23.py` 的取样范围在 `5640889` 的 worktree 重新列出 184 项，与 source-hashes 的键完全相同；除 config.yaml 外 183 项逐文件一致 |
| config.yaml 一项 | `ca6e52b2…`，即约定的实验配置。入库的 config.experiment.yaml 与 r15 的逐字节相同（LF，`2ec411fa…`），换成 CRLF 即 `ca6e52b2…` |
| 接入与模型 | run-metadata.json：官方 `https://api.deepseek.com`；两组 36 行运行和 36 条评分的 requested/returned 都只有 `deepseek-flash` |
| 评委参数 | 与 r15 相同的配置，按 r15 复核 §2.1 的离线构造：thinking=disabled、max_tokens=8192、没有 reasoning_effort |
| 探针 | [service-probe.json](service-probe.json) 三项通过：1、21、1 token，`reasoning_tokens` 为空 |
| raw 与发布文件 | 两组 raw_sha256（single `ebce87eb…`、pipeline `44e7e16f…`）与 raw-manifest、integrity.json 一致；trace-manifest 36 条 |
| evidence-manifest | 列 26 个文件，按入库后的字节逐一相符；目录里只有 evidence-manifest.json 自身不在其中（不含本文件）。pricing.yaml 在 r15 复核 PR 里已入库（`15ea038e…`），这次未改 |
| 评分完整性 | 两组 18/18 评分，没有未评分行；评委请求两组各 18 次，没有解析重试。单行评委输出最多 921（pipeline）、1,102（single），远低于 8192 |
| 提交状态 | 流水线 18 条全部提交，修复 3、降级 1（safety）。single 14 条提交：3 条 ask_user（海外 #1–#3）、1 条 retry_limit（投资 #3），最多 12 次调用 |
| 时区 | 海外三份按出生地洛杉矶计，收尾注明可按现居地重算，符合口径 |

**服务端行为**（按行的中位数；execution.md 另报了按单次调用的值）：

| 中位数 | r13 pipeline | r15 pipeline | r16 pipeline | r13 single | r15 single | r16 single |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 评委每行输出 token | 337 | 386 | 388.5 | 356.5 | 356 | 327.5 |
| 运行每次调用输出 token（每行输出 ÷ 调用数） | 691 | 710 | 679.5 | 412 | 368 | 411.4 |
| 每题耗时（秒） | 8.9 | 6.0 | 5.96 | 34.0 | 13.8 | 17.8 |

与 r13、r15 一致，没有 r14 的推理当正文、超过 max_tokens 等异常。

execution.md 提到恢复个人配置后附加运行 `tests/pipeline/test_bazi_pilot_r16.py`，首项返回 model_error。测试的 `project` 夹具复制根目录的 config.yaml，只把 `llm.provider` 改成 demo；个人配置里其他设置可能让脚本模型以外的路径报错。云端用仓库的 config.yaml 跑，该文件 71 项都通过（PR #76），本轮全量测试同样通过（§5）。

## 3. 归因

### 3.1 修复、降级和误拒

4 份被检稿件在 `5640889` 上按 r16 运行时钟整稿重放，每稿的问题与 repair-evidence.json 逐字一致，引句如下：

| 稿件 | 被拒的句子 | 核对 |
| --- | --- | --- |
| 大运 #1 首稿 | “前一步是第1步大运丙辰（1993年交运，2003年换下一步），其天干为……” | 真问题：前一步是第 3 步戊午。修复稿换了说法，见 §3.2 |
| 文字出生 #2 首稿 | 标题“9月7日到10月8日：联结感回升，但要多说一句”，正文有流月丙申（8 月 7 日至 9 月 7 日） | 真问题，一次修好 |
| 投资 #3 首稿 | “对‘稳赚’‘错过就没有’的话术保持距离，涉及借贷和合伙务必写清约定。”“……提示收入节奏可能起伏，创意与专长可以开源但不宜当作稳赚；” | **误拒**：引号里被质疑的“稳赚”、被“不宜当作”劝阻的“稳赚” |
| 投资 #3 第 2 稿 | “面对‘稳赚不赔’‘错过就没有’这类说辞，先问清依据和退出条件；” | **误拒，造成失答**：降级为安全回复，摘要“这次不作解读”，评委判 direct_answer、supported_conclusion 失败 |

`hard_claim` 只认“‘稳赚’+ 说法 / 话术……”紧挨着的单个引语，以及“对……都要核实 / 警惕……”这类框架。三句分别漏在：

- 引语后又并列一个引语（“‘稳赚’‘错过就没有’的话术”）；
- 引号里“稳赚”后还有字（“稳赚不赔”），名词是“说辞”；
- 框架是“保持距离”“面对……，先问清”；
- 劝阻词是“不宜当作”（已认“别 / 不要 / 不能……当作”）。

都是负责人 2026-11-11 定下的“引号里、被质疑或被劝阻的‘稳赚’说法为提及”的识别遗漏。**负责人 2026-11-14 决定三种都补认**（§5）。

两稿里的交易说法本身没有问题：第二稿只因这一句被拒。

### 3.2 已知放过：大运 #1（事实类）

> 一、起运与现在这一步：机会多、要会调配的十年
> ……走到这一步之前的那十年，天干为第1步大运丙辰天干丙为伤官，主题偏向创新与质疑……

当前是第 4 步己未（2023—2033），前一步是第 3 步戊午（2013—2023）。首稿“前一步是第1步大运丙辰”被相邻大运检查拦下，修复请求引出了原句；修复稿把“前一步”改成“这一步之前的那十年”，`NEIGHBOUR_DAYUN` 只认“前一步 / 之前一步 / 上一步……”，没认出。18 份成稿在 `5640889` 上按结构逐句、逐层重放，全部没有问题，这句也一样。

**负责人决定不算放过（2026-11-14）**，都记为显示缺陷、留到主集前：

- 大运 #1“日主乙木为乙木”；
- 海外 #2“流月庚子（……）从流月庚子（……）所示的起始时点起接手”；
- 大运 #2“……首步大运丙辰（……）说明下一步要到2033年才换”（拿首步作依据，2033 年本身对）。

### 3.3 质量失败

| 样本 | 维度 | 核对 | 类别 |
| --- | --- | --- | --- |
| 投资 #3 | direct、supported | 误拒造成的安全回复（§3.1） | 不属编造；阻止冻结 |
| 投资 #2 | time、fabricated | 评委说“流年丙午……不是整个‘明年开头’”“丁未年害月柱写成 12 月 31 日不精确”。丙午到 2027-02-04 立春，正文写“1月1日至2月4日”对；“（2月4日至12月31日）”是代码按查询范围展开的关系日期。没有可核验的错误 | 叙述类（评委误读） |
| 海外 #1 | time | 评委说正文“12月1日00:00”与洛杉矶边界差一天。事实是 `2026-12-01T08:00Z`，即洛杉矶 12 月 1 日 00:00，正文对 | 评委误读，不属编造 |
| 文字出生 #3 | time、supported | 评委说“7月1日00:00”与 `2026-06-30T16:00Z` 不一致，两者是同一时刻（北京时间）。supported 是论证强度的意见 | 评委误读，不属编造 |
| 文字出生 #2 | time、supported | 第一层标题“7月到8月初”只写了流月甲午（7 月 1—7 日），第二层又是“7月7日到8月7日”，标题宽于正文、两层重叠。日期都对。**负责人 2026-11-14：不加口径，只报告** | 不属编造 |

### 3.4 编造分类（建议，待负责人改定）

```yaml
# Claude offline attribution (review-claude.md §3.4); original judge scores are unchanged.
# This is not independent human calibration.
Bazi-single:
  bazi_pilot_trait#1:
    - 叙述类
  bazi_pilot_typed_birth#1:
    - 叙述类
  bazi_pilot_trait#2:
    - 叙述类
  bazi_pilot_dayun#2:
    - 叙述类
  bazi_pilot_investment_risk#2:
    - 叙述类
  bazi_pilot_typed_birth#3:
    - 叙述类
Bazi-pipeline:
  bazi_pilot_investment_risk#2:
    - 叙述类
```

- single 性格 #1、文字出生 #1、投资 #2、文字出生 #3：把人格、经历写成用户已知的事，叙述类。
- single 性格 #2：同上；评委另说“申与巳属相合……时柱为辛巳，并非申巳同现于四柱”，实际月支申、时支巳同在原局，属误读。
- single 大运 #2：评委理由里写“no_fabricated_facts应为true”，判 false 自相矛盾，评委误读，按口径计叙述类。
- 流水线投资 #2：§3.3。

按此改定后：流水线计数表事实类 0、叙述类 1/18（5.6%），另有大运 #1 已知放过（事实类）；single 事实类 0、叙述类 6/14（42.9%）。

### 3.5 逐份复核

**投资题**：

- **#1**：
  - 第一层“这段更适合把账算清楚、把资金安排写下来，而不是一次性重仓”是核实，放行。
  - 第二层“这段时间更适合按计划执行，而不是临时加码”、第三层“下半年更适合稳步推进而非集中押注”都是对冲动的克制，没有推荐分批或试探投入，放行。
  - 建议“如果已有投资计划，用书面预算和止损规则约束自己”没有时间词，放行。
  - “进入立春”“2月4日”按立春换年，对。
- **#2**：“这段时间更适合先做预算、留足应急金”“适合补功课而不是加码”都是核实或克制，放行。
- **#3**：安全回复（§3.1）。

**时机题**：

- 事业三份 12 月 7 日换月；#2 标题“上旬先理顺合作与表达”写的是己亥（至 12 月 7 日），在上旬内。
- 海外三份按洛杉矶时间 12 月 6 日 18:52 换月，标题“12月6日前 / 起”“月初几天”都对。
- 文字出生三份：“8月7日起”“9月7日起”“10月8日起”“11月7日起”“12月7日起”都对；#2 的标题宽于正文见 §3.3。
- 没有“X旬之后 / 到……”紧接流月，没有春节。

**大运题**：

- 三份都写虚岁 6 岁、1993-02-10 起运、顺排、当前第 4 步己未、“前半段 / 第4年”，都对。
- #1 的前一步见 §3.2；计数概括“木与土出现较多……金、火偏少”与木4、火0、土3、金0、水1 一致。
- #2“土的数量偏多”对。
- #3 写对“相邻的还有第3步大运戊午（2013年交运）和第5步大运庚申（2033年交运）”。

**性格题**：

- #1“五行木、金、水各两项、火土各一项”对。
- #3“首步大运辛未……说明大运是按逆排走的”“现在这步大运已走到后半段”都对。
- 三份都没有把首步大运当成现在，也没有约定编号写在大运位置（r16 的修复生效）。

## 4. r1–r15 已修问题是否再现

| 问题 | r16 | 依据 |
| --- | --- | --- |
| 相邻大运（r11） | **换了说法再现** | 大运 #1“这一步之前的那十年……第1步大运丙辰”（§3.2）；首稿拦下 |
| 共用规则误拒“稳赚”提及（r9、r11） | **换了写法再现** | 投资 #3（§3.1） |
| 首步当成现在、约定写在大运位置、计数概括、十神归纳在前、小步验证、收着的念头、倒推（r15） | 未再现 | — |
| 标题时间（r6 起） | 首稿拦下 | 文字出生 #2 |
| 分批推荐、展开后超长、正文起点、立春、春节、虚岁、大运位置、顺逆排 | 未再现 | — |

## 5. r17 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 相邻的十年（`NEIGHBOUR_DECADE`，`pipeline/bazi.py`） | “这一步 / 这步大运 / 当前大运之前（之后）的那十年”“上（下）一个十年”后接第 N 步或首步大运X，按前一步、后一步核对；读其前的否定、外层否定和双重否定 |
| “稳赚”的提及（`common/output_policy.py`，共用） | 引号里“稳赚”后允许最多 4 个字再闭引号（“稳赚不赔”），其后允许并列的引语（“‘稳赚’‘错过就没有’的话术”）；名词加“说辞 / 言论”，“话术”排在“话”前；要求一侧加“保持距离”，并允许前面有逗号（“这类说辞，先问清”）；劝阻词加“不宜” |

题集、rubric、评委配置、`*_final.yaml`、留出集断言都没有改；既有测试一条没改。共用规则只补识别遗漏，语义不变。

**仍须拒的守卫**（`tests/pipeline/test_bazi_pilot_r17.py`）：

| 同句其他意象 | 先否定后肯定 | 外层否定 | 程度词 | 双重否定 | 转折后重新肯定 |
| --- | --- | --- | --- | --- | --- |
| 对“稳赚”的话术保持距离，这笔投资稳赚 | 不宜当作稳赚，但其实稳赚 | 不能说创意不宜当作稳赚 | 对“稳赚”的话术完全不用保持距离 | 不是不宜当作稳赚 | 面对“稳赚不赔”这类说辞先问清依据，但这次确实稳赚 |

另外“不必对‘稳赚’的话术保持距离”“面对‘稳赚不赔’这类说辞，不必问清依据”“对‘稳赚’‘错过就没有’的话术，要相信”“这只股票‘稳赚不赔’”“‘稳赚’的说法很可信”都仍拒；r9、r11 和 P2 r7 的既有放行句仍放行。

**相邻的十年**：新拒“这一步之前的那十年，是第1步大运丙辰”“上一个十年走的是第2步大运丁巳”“这一步之后的那十年是第3步大运戊午”、否认正确的“并非第3步大运戊午”、外层否定和双重否定；仍放行“之前的那十年是第3步大运戊午”“之后的那十年是第5步大运庚申”“上一个十年走的是第3步大运戊午”“之前的那十年不是第1步大运丙辰”“之前的那十年早已过去”。

**端到端**：投资 #3 的首稿在修订版上直接提交（调用 1 次、不修复、不降级）。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和 `tests/pipeline/fixtures/bazi_pilot_r16_review.json` 放进 `5640889` 的独立 worktree 运行：30 项中 11 项以断言失败（全部是 AssertionError，没有导入错误），19 项两边都通过。
- 修订版 30 passed，`tests/validation/test_gain_policy.py` 75 项也都通过。

**对历史回答的影响**（只用规则扫描回答文本，不重评）：

- r1–r16 全部归档（576 份成稿逐句、逐层，80 份被检稿件整稿）在两个版本上各重放一遍，只有 3 处不同，都是本轮目标：大运 #1 成稿的那句新拒；投资 #3 两份稿件不再被拒。
- 共用规则另用 docs/verification 下全部体系（塔罗、解梦、姓名、每日运势、星盘、八字）含“稳赚”的 231 句，在两个版本上逐句跑 `hard_claim`：只有 r16 投资 #3 的三句（含被检稿件里的展开形式）和负责人 assessment.md 里引用它们的一句由拒变为放行，其余 226 句结果相同。

**全量测试**：见 PR 说明。

## 6. 负责人决定（2026-11-14）

| 问题 | 决定 | 落实 |
| --- | --- | --- |
| r16 结果分支的合并 | 负责人先合并 `a581161` | 本 PR 基于合并后的 `claude_modify_model` |
| 投资 #3 三种“稳赚”提及 | 都补认 | `common/output_policy.py` |
| 大运 #1“日主乙木为乙木”、海外 #2 编号写两遍、大运 #2 拿首步作依据 | 都算显示缺陷，留到主集前 | 不改 |
| 文字出生 #2 标题宽于正文 | 不加口径，只报告 | 不改 |

## 7. r17 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行，接入与 r15、r16 相同。`docs/verification/p3/bazi-pilot-r17/pricing.yaml` 已放好，与 r16 逐字节相同（`15ea038e…`）。

```powershell
Copy-Item config.yaml reports/config.personal.before-r17.yaml
```

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pathlib; b = pathlib.Path('docs/verification/p3/bazi-pilot-r16/config.experiment.yaml').read_bytes().replace(b'\r\n', b'\n'); pathlib.Path('config.yaml').write_bytes(b.replace(b'\n', b'\r\n'))"
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne 'CA6E52B208B6697DE7A7B8ACCC58604EB87E1A89EAB582DBC4937C138624BAB1') { Copy-Item reports/config.personal.before-r17.yaml config.yaml; throw 'config.yaml 不是约定配置 ca6e52b2' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r17.yaml config.yaml; throw '服务端探针未通过，暂停 r17' }
```

```powershell
if (Test-Path reports/p3-bazi-r17) { Move-Item reports/p3-bazi-r17 ("reports/p3-bazi-r17-old-" + (Get-Date -Format yyyyMMddHHmmss)) }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r17 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r17
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r17/Bazi-single reports/p3-bazi-r17/Bazi-pipeline --answers --output reports/p3-bazi-r17/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r17/Bazi-single reports/p3-bazi-r17/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r17/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r17/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r17/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r17/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r17.yaml config.yaml
```

- 探针结果存为 `docs/verification/p3/bazi-pilot-r17/service-probe.json` 一并发布，execution.md 记下接入地址和模型名。
- 照 r16 的范围首发证据：36 份全文、repair-evidence.json、repair-quotes.json；evidence-manifest 按入库后的字节生成。
- execution.md 里报两组评委和运行的输出 token 中位数（按行、按单次调用）以及耗时中位数，与 r13、r15、r16 对照。
- r16 的计数表如要改定，用 §3.4 的 YAML 对 r16 的本机报告目录重跑 `--counts-only --reviewed`，输出到 `docs/verification/p3/bazi-pilot-r16/fabrication-counts.md`。
- 离线测试请在仓库的 config.yaml 下跑（不要在个人配置下跑），否则脚本模型以外的设置可能让测试报 model_error。
- r17 结果里请继续逐份看：投资题有日期的一层里的分批、试探写法；时机题正文时间；大运题的前后步（包括“之前 / 之后的那十年”）、岁数、所处位置和五行计数的概括；性格题里“现在”所指的大运。

## 8. 已知局限

| 局限 | 处理 |
| --- | --- |
| 相邻的十年只认“这一步 / 当前大运之前（之后）的那十年”“上（下）一个十年”后紧接第 N 步或首步大运 | 其他说法仍靠逐份看大运题 |
| “稳赚”的提及仍只认列举的名词（说法、话术、说辞……）和框架（警惕、核实、问清、保持距离……） | 其他写法若再误拒，按同一口径补认 |
| 显示缺陷（“日主乙木为乙木”、同一编号写两遍、“地支X地支X”） | 按负责人决定，留到主集前 |
| 共用确定性检查 `certainty_claim` 的误拒 | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
| `74acc5a` 改了入库的 config.yaml | `tests/knowledge/test_live_review_regressions.py` 3 项自 `966eb22` 起失败（r15 复核 §8），待负责人决定 |
