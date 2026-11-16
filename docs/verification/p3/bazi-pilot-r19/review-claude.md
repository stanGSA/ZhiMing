# P3 八字调参集 r19 复核：不满足 B，r20 修复后重跑

负责人发布的文件不改；本文件按 r12 复核和 r13–r18 的 review-claude.md 的写法补充复核。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 r19 结果：`aacbb00` 首发，`7ee718b` 补齐证据（中间的 `db5be54` 误放了 r18 的文件，已由 `7ee718b` 换成 r19 自己的）。包括 [execution.md](execution.md)、[assessment.md](assessment.md)、[run-metadata.json](run-metadata.json)、[config.experiment.yaml](config.experiment.yaml)、[service-probe.json](service-probe.json)、[integrity.json](integrity.json)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[pipeline-problem-counts.md](pipeline-problem-counts.md)、[fabrication-counts.md](fabrication-counts.md)、[quality-failures.json](quality-failures.json)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[supplement-answers.md](supplement-answers.md)、[supplement-answers.json](supplement-answers.json)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json) |
| 被测代码 | `cc5a4b6996e33e07eafaf19c3a93aa34991692eb`，即 PR #81 合并（含负责人补的 `42d2aa8`）；源码指纹 `f05c93db8ba32470b1d2a8c40035d0a4c22822e5cea17e4337364681813cec3a` |
| 接入与配置 | 约定：官方 `https://api.deepseek.com`，运行与评委都是 `deepseek-flash`，实验配置 `ca6e52b2…`；评委 thinking=disabled、不设 reasoning_effort、max_tokens=8192 |
| 方法 | 离线：<br>- 重算指纹；在 `cc5a4b6` 的独立 git worktree 里，按 `scripts/live_week23.py` 的取样范围逐文件对照；<br>- 核对模型、配置、raw_sha256、evidence-manifest 和评分完整性；<br>- 5 份被检稿件（未展开原稿在 repair-evidence.json 的 `text` 字段）在 `cc5a4b6` 上按 r19 运行时钟（`20261116T103654`）整稿重放；<br>- 18 份流水线成稿按结构逐句、逐层重放；<br>- 逐份读 18 份流水线成稿和 single 的 2 份编造失败；<br>- r20 的改动用 r1–r19 全部归档回答（684 份成稿逐句、逐层，93 份被检稿件整稿）在两个版本上各重放一遍。<br>没有改共用规则，没有调用模型 |
| 日期 | 2026-11-16 |

## 1. 结论

**不满足 B，不冻结。** 负责人的 [assessment.md](assessment.md) 没有记冻结，但把文字出生题的质量失败留作待确认项。我核对后认为：
- 那两项质量失败不是误拒造成的：两行都没有修复，评委理由也没有指出可核验的错误；
- 挡住 B 的是两处已知放过：
  - **大运 #2（事实类）**：“第1步大运丙辰天干丙为伤官对应的是前一步第3步大运戊午，2013年交运，那时天干带伤官主题”。前一步是戊午，这一处写对了；但“第1步……对应的是前一步”把首步当成了前一步，而戊午的戊对乙是正财，不是伤官。这是 r18 大运 #1 换了写法的再现。
  - **投资 #3（交易边界，负责人 2026-11-16 判为放过）**：标题“5月到年底”这一层写“这段时间的波动更支持你保留余地、分批规划，而不是一次性押上”。

流水线其余表现良好：
- 提交 18/18、调用最多 2 次、修复 5、降级 0；
- 已提交质量 16/18（88.9%），高于 single 的 12/14（85.7%），P1 四条满足；
- **两组计数表第一次都“完整”**：负责人发布前已判定，我同意；
- 5 份被检稿件中有 3 份的拒绝理由不对（§3.1），都在一次修复后通过，没有造成降级、失答或质量失败，不阻止冻结。r20 一并修正。

| B 条件 | r19 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 23 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 计数表都“完整”，事实类 0；但另有 1 份已知放过的事实类（§3.2） |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 降级 0；3 次误拒都在一次修复后通过（§3.1）；2 项质量失败与修复无关（§3.3） |
| 没有已知放过 | **不满足** | 大运 #2、投资 #3（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 16/18（88.9%）对 12/14（85.7%） |
| （前提）约定接入与配置 | 满足 | §2 |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 1 份：大运 #2（已知放过，评委判通过） | 0 |
| 叙述编造（不高于 single，争取 ≤ 10%） | 0/18（0.0%） | 2/14（14.3%） |
| `time_consistent` 失败 | 2（文字出生 #2、#3，评委误读） | 2（事业 #2 的“节令大寒前”、海外 #3 追问未作答） |
| 降级比例（≤ 10%，监控项） | 0/18 | — |
| 每题模型调用（≤ 3） | 约 1.28（23/18），最多 2 | 约 6.44（116/18），最多 10 |
| 每题输入 token（≤ 20,000，不含评委） | 约 6,313 | 约 47,310 |
| P95 耗时（≤ 90 秒） | 10.5 秒 | 35.8 秒 |
| 已提交回答质量通过率 | 16/18（88.9%） | 12/14（85.7%） |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-flash`，同模型评分，不是独立评审。

execution.md 表里的“每题运行输入 / 输出 token”（pipeline 20,441 / 1,219，single 58,260 / 3,278）取的是 summary 的总数除以 18，含评委。不含评委时：
- pipeline 每题 6,313 / 869；
- single 每题 47,310 / 2,941；
- 与两份 failures 文件一致。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，184 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `f05c93db…`，与 execution.md、两份 summary、run-metadata.json、integrity.json 一致。与 r18 相比只有 `pipeline/bazi.py` 一项不同 |
| 被测提交 | 按 `scripts/live_week23.py` 的取样范围在 `cc5a4b6` 的 worktree 重新列出 184 项，与 source-hashes 的键完全相同；除 config.yaml 外 183 项逐文件一致。`cc5a4b6..7ee718b` 只动了本目录 |
| config.yaml 一项 | `ca6e52b2…`；入库的 config.experiment.yaml 为 LF（`2ec411fa…`，与 r18 的逐字节相同），换成 CRLF 即 `ca6e52b2…` |
| 接入与模型 | run-metadata.json：官方 `https://api.deepseek.com`，评委 `pro` → `deepseek-flash`、thinking=disabled、max_tokens=8192；两组 36 行运行和 36 条评分的 requested/returned 都只有 `deepseek-flash` |
| 探针 | [service-probe.json](service-probe.json) 三项通过（运行回复、工具调用、评委回复），requested/returned 都是 `deepseek-flash` |
| raw 与发布文件 | 两组 raw_sha256 与 raw-manifest 一致（single `30ace81b…`，pipeline `5b9c3fc6…`）；trace-manifest 36 条，覆盖两组 18 行（trace 本体在本机，哈希无法离线复核） |
| evidence-manifest | `7ee718b` 版列 26 个文件，按入库后的字节逐一相符；目录里只有 evidence-manifest.json 自身不在其中（不含本文件）。`db5be54` 版有 12 项是按 Windows 工作区的 CRLF 字节算的，已由 `7ee718b` 改正 |
| pricing.yaml | `15ea038e…`，与 r18 逐字节相同 |
| 评分完整性 | 两组 18/18 评分，没有未评分行。评委请求各 18 次，没有解析重试，usage 齐全，运行没有缺 usage 的调用。累计评委输出：pipeline 6,283、single 6,058；单行最多 496（pipeline）、497（single），远低于单次上限 8192 |
| 提交状态 | 流水线 18 条全部提交，修复 5、降级 0、工程 18/18。single 14 条提交：海外 #1–#3 ask_user，投资 #3 retry_limit |

**服务端行为**（按行的中位数）：

| 轮次 | 评委每行输出（pipeline / single） | 运行每次调用输出（pipeline / single） | 每题耗时（pipeline / single） |
| --- | --- | --- | --- |
| r13 | 337 / 356.5 | 691.0 / 412.5 | 8.9 / 34.0 秒 |
| r15-deepseek-flash | 386 / 356 | 710.0 / 368.0 | 6.0 / 13.8 秒 |
| r16 | 388.5 / 327.5 | 679.5 / 411.4 | 6.0 / 17.8 秒 |
| r17 | 346.5 / 362.5 | 653.5 / 346.6 | 5.4 / 15.2 秒 |
| r18 | 355 / 381 | 682.5 / 400.4 | 6.9 / 15.4 秒 |
| **r19** | **336 / 344.5** | **683.5 / 473.0** | **6.6 / 15.1 秒** |

运行每次调用的输出按“每行输出 ÷ 调用数”算。r19 与 r13、r15–r18 一致；single 每次调用的输出略高，仍在同一量级。

**发布过程**：
- 首发 `aacbb00` 只有 13 个文件，缺 run-metadata、配置、清单、全文和修复证据；
- 第一次补发 `db5be54` 放进的是 r18 目录的 12 个文件（run-metadata 写的是 `41d3efd` 和 r18 的 run_id）；
- `7ee718b` 换成了 r19 自己的文件，本复核据此进行。

r20 起请按 §7 的清单首发。

## 3. 归因

### 3.1 修复和误拒

5 份被检稿件在 `cc5a4b6` 上按 r19 运行时钟整稿重放，问题与 repair-evidence.json 逐字一致，修复请求都引出了原句（repair-quotes.json）。投资 #1 的交易问题在 pipeline-problems-raw.md 里没列候选原句，但 repair-quotes.json 里有，r11、r13、r15 的同类记录也一样，属于报告格式，不是没引出。

| 稿件 | 问题 | 判断 |
| --- | --- | --- |
| 大运 #1 首稿 | “下一步是第5步大运庚申”被报成后一步应是第 4 步己未 | **误拒**。原句“前一步是{{R?前一步戊午}}——第3步大运戊午（2013年交运），下一步是第5步大运庚申（2033年交运）”说的是当前大运的前后步，都对。前一步的说法中间夹了残缺编号，检查没认出来，就把戊午当成了“下一步”的起点 |
| 大运 #1 首稿 | “月柱月柱” | 真问题 |
| 大运 #1 首稿 | “不代表某十年里事件必然发生”被确定性检查拒 | 共用 `certainty_claim` 的误拒（否定了的“必然”），按负责人决定留到主集前 |
| 投资 #1 首稿 | 交易问题，触发句“全年看，适合把‘全投’改成‘先核实、再规划’” | **误拒**。推荐的是核实和规划，不是交易；去掉“全年看，”就放行。负责人照拒的是“改成‘有边界地参与’” |
| 大运 #2 首稿 | “日主日主” | 真问题。首稿已有 §3.2 那句已知放过，修复稿原样保留 |
| 大运 #3 首稿 | “下一步是第5步大运庚申”被报成后一步应是第 4 步己未 | **理由不对**。原句“前一步是日主乙木所对应的第3步大运戊午，下一步是第5步大运庚申”的前后步都对；真正的问题是日主被写在了前一步大运的位置（同 r18 的原局柱当前一步） |
| 事业 #3 首稿 | 标题“12月7日起”，正文是 12 月 1—7 日的流月己亥 | 真问题 |

三处误拒或理由不对，都在一次修复后通过：没有降级、没有失答，所在样本质量都通过。按 B 不阻止冻结，r20 一并修正（§5）。

### 3.2 已知放过

18 份成稿在 `cc5a4b6` 上按结构逐句、逐层重放，全部没有问题；下面两处都是检查放过、评委也判通过的。

**大运 #2（事实类）**

> 第1步大运丙辰天干丙为伤官对应的是前一步第3步大运戊午，2013年交运，那时天干带伤官主题，偏向创新与质疑，提出改进时最好同时说明依据。

- r19 的 `NEIGHBOUR_NAMED_FIRST` 只认“第N步大运X……是 / 为 / 属于 / 就是上（下）一步”，不认“对应的是”。
- 后半句给戊午安上伤官，是首步丙辰的十神；`DAYUN_THEME` 只核对“主题（会）转向 / 是……+主题词”，不核对“天干带X”。
- 首稿已有这句，修复稿原样保留。

**投资 #3（交易边界，负责人 2026-11-16 决定）**

> 三、5月到年底：波动明显，守住底线比抓机会重要
> ……如果你正在考虑把积蓄全投进去，这段时间的波动更支持你保留余地、分批规划，而不是一次性押上。

- 有日期的一层里，“更支持你……分批规划”是给这段时间推荐分批。
- 分批的推荐词只认“适合 / 可以 / 建议……”，没认出“支持你”。
- r8 放行的“把‘全投’换成‘分批、留底、按预算’更稳妥”没有推荐词、也没有时间，不受影响。

**其他观察（不计放过）**：
- 投资 #3 第二层（“2月到5月”）“更适合把规则、预算、止损线写清楚，而不是凭感觉下单”是设上限、写规则，放行。投资 #1、#2 各层都是核实、学习和克制。
- 海外 #2 摘要“上旬易有直接拉扯……中下旬协作……变多”、建议“上旬遇到临时变动时……中下旬合作变多”，都不紧接流月，按“摘要里不紧接流月的概述放行”的口径不计；流月庚子 12 月 6 日起，比“中下旬”早。
- 海外 #3“用新方法小步试错”、建议“想推新做法先用小范围验证”说的是工作做法，不是资金。
- 显示缺陷（已定留到主集前）：
  - 性格 #1“日主乙木落在乙木上”；
  - 大运 #1“首步大运丙辰（……），第一步落在第1步大运丙辰（……）”“这步大运的天干第4步大运己未天干己为偏财”“日柱地支日柱乙亥地支亥”；
  - 大运 #2“第4步大运己未（……）显示你当前处在第4步大运己未”。

### 3.3 质量失败

| 样本 | 维度 | 核对 | 类别 |
| --- | --- | --- | --- |
| 文字出生 #2 | time | 评委写正文“用节气交接日（7月7日、8月7日等）划分……未明确说明节气流月边界，时间标注基本合规”，结论却判失败。正文每个流月都带了代码给的起止时刻，按节气换月正确 | 评委误读，不属编造 |
| 文字出生 #2 | supported | 评委认为“整体平稳、收尾偏暖”是综合冲突信号后的笼统定性。这是对概括力度的评价，没有指出事实错误；摘要的“对关系的要求比较清楚，但容易在细节上挑剔”是倾向性措辞 | 质量判断，不属编造 |
| 文字出生 #3 | time | 评委四条理由都是肯定（“使用用户指定范围”“节气月边界……以流月切换标注，未当作公历整月”），结论却判失败 | 评委误读，不属编造 |

两行都没有修复（`repairs: 0`），失败与流水线的检查无关，不是误拒。

single 的质量失败：
- 事业 #2：“节令大寒前”（12 月 7 日换月的节气是大雪）；
- 海外 #1、#3：追问未作答；
- 投资 #3：retry_limit；
- 大运 #3：见 §3.4。

### 3.4 编造分类

负责人发布前已判定，两组计数表都“完整”。我同意：

```yaml
# Claude offline attribution (review-claude.md §3.4); original judge scores are unchanged.
# This is not independent human calibration.
Bazi-single:
  bazi_pilot_next_month_career#2:
    - 叙述类
  bazi_pilot_dayun#3:
    - 叙述类
Bazi-pipeline: {}
```

- **single 事业 #2**：评委的编造理由是把“愿意把责任扛下来、对机会敏感、会自己找钱路”这类性格和职业习惯写成用户情况，属叙述类。时间安排里的“节令大寒前”是可核验的节气错误，评委已记在 `time_consistent` 下。负责人 2026-11-16 决定维持叙述类。
- **single 大运 #3**：把起运折算成“90年代初上幼儿园、小学那段时间”，并把大运十神写成少年期性格，属叙述类。大运序列、交运年份、十神都与计算一致。
- **流水线**：没有编造失败；大运 #2 的已知放过（§3.2）另计事实类。

计数：流水线事实类 0、叙述类 0/18（0.0%），另有 1 份已知放过的事实类；single 事实类 0、叙述类 2/14（14.3%）。

### 3.5 逐份复核

**投资题**（有日期的分层与摘要）：

- **#1**：
  - 摘要“先核实自己的财务底数和风险承受能力”；
  - 第一层“先把手头积蓄的用途、应急备用金和负债情况列清楚”；
  - 第二层“更适合把精力放在完善自己的财务知识和风险认知上，而不是急于做全投决定”；
  - 第三层“与其急着做决定，不如先把风险承受能力想明白”。
  - 都是核实或克制。首稿的误拒见 §3.1。
- **#2**：
  - 第一层“不要在这段时间凭一时热劲做全投决定”；
  - 第二层“更适合做功课、核实风险承受能力，而不是把积蓄一次性押上”。
  - 都是克制。
- **#3**：
  - 第二层的止损线见 §3.2 其他观察；
  - 第三层的“分批规划”见 §3.2。
- 三份都写“2月4日立春后进入流年丁未”，或标题以立春分段；没有春节。

**时机题**（正文时间）：

- 事业三份的换月日都是 12 月 7 日，海外三份都是洛杉矶时间 12 月 6 日；标题与流月一致。
- 文字出生：
  - #1“7月上旬流月甲午”，甲午 7 月 1—7 日，落在上旬里；
  - #3“7月上旬这段时间”指甲午，同样落在上旬里；
  - 三份的分层“7月到8月初”“8月到10月初”“10月到年底”与流月一致。

**大运题**：

- 三份都写虚岁 6 岁、1993-02-10 起运、顺排、当前第 4 步己未、前半段，都对。
- 五行计数概括“木4、土3、水1、火金为0，木土偏多而火金不显”“土的数量偏多”“火金偏少”，都对。
- 前后步：
  - #1“往前看是第3步大运戊午（2013年交运），往后则是第5步大运庚申”对；
  - #3“当前大运之前已经经历到第3步戊午，再往后则由第5步庚申接续”对；
  - #2 见 §3.2。
- 主题与十神：己未的己为偏财，“机会与调配”对；#2 的戊午错，见 §3.2。
- 没有原局柱或约定写在大运位置；#3 首稿的日主写在前一步位置，修复后已去掉。

**性格题**：

- #1“当前大运走到后半段”：2026 年在己巳（2017—2027）的后半段，对。
- #2、#3 没有写“现在”所处的大运。
- 计数：
  - #1、#3“木2、火1、土1、金2、水2……较均衡”与计数一致；
  - #2“金水合计偏多，木只有两个”也一致。
- #3 的“子时按23点换日只说明排盘口径”写在口径位置，不在大运位置。

## 4. r1–r18 已修问题是否再现

| 问题 | r19 | 依据 |
| --- | --- | --- |
| 先写大运再说前后步（r18） | **换了写法再现** | 大运 #2“……对应的是前一步”（§3.2） |
| 十神或主题写错（r7、r17、r18） | **换了形式再现** | 大运 #2 戊午“那时天干带伤官主题”（§3.2） |
| 推荐分批、分散、试探（r7、r12、r14、r15、r17、r18） | **换了写法再现** | 投资 #3“更支持你……分批规划”（§3.2） |
| 原局柱或约定写在大运位置（r4、r15、r18） | 首稿出现，修复后去掉 | 大运 #3 首稿的“日主乙木所对应的第3步大运戊午”（§3.1） |
| 重复标签、标题时间 | 首稿拦下，一次修好 | §3.1 |
| 首步当成现在（r3、r13、r15、r18）、正文起点与写了月份的“X旬”（r8、r13、r18）、用小部分资金去试（r18） | 未再现 | §3.5 |
| 相邻大运（r11、r16）、天干十神、“稳赚”提及、计数概括、立春、春节、虚岁、大运位置、顺逆排、藏干误拒（r17） | 未再现 | — |
| 前后步检查的误拒 | 新出现，未造成降级 | 大运 #1、#3 首稿（§3.1） |

## 5. r20 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 先写大运再说前后步（`NEIGHBOUR_NAMED_FIRST`） | 在“是 / 为 / 属于 / 就是”之外，也认“对应（的）（就）是 / 指的是 / 即”；读其前的否定和外层否定 |
| 大运天干的十神（`CYCLE_STEM_GOD`，新） | “第N步大运X（……）（，YYYY年交运）（，那时 / 当时 / 这一步）天干（带 / 为 / 是）+十神”，十神要与 X 的天干对日主的十神一致；读否定、双重否定和外层否定。写出天干字的“天干己为正官”仍由每句的天干十神检查报，不重复报 |
| 有日期一层里“支持你……分批”（`BATCH_RECOMMENDED`） | 推荐词加上“更 / 更加 / 也 / 还是支持”和后接“你 / 您”的“支持”；“不支持 / 并不支持”放行，外层否定、双重否定、转折后的“但支持你分批投入”仍拒 |
| 把交易换成不交易的做法（`SWAPPED_AFTER`，放宽） | 推荐词后紧接“把（积蓄）‘全投’改成 / 换成……”，而换成的内容不含交易、分批、试探、参与、投、买、仓这类词时，不算推荐交易；推荐词前有否定（“不能说适合把……改成……”）不放宽 |
| 前一步之后的“下一步”（`neighbour_origin`，放宽） | 同一句里“前一步 / 上一步”之后点名的那步大运，不再当作“下一步”的起点；“下一步”按当前大运算 |
| 日主写在前后步的位置（`DAY_MASTER_AS_NEIGHBOUR`，新） | “前一步 / 下一步是 / 为 / 在（本命的）日主X（所）对应 / 所在 / 代表的”拒（同 r18 的原局柱当前后步） |
| 前后步的否定隔着编号（`NEIGHBOUR_DAYUN`，补识别） | “下一步不是第5步大运庚申”：否定和干支之间隔着“第N步大运”时，`value_claim` 读不到否定，原来放行；现在按匹配里的否定计数，外层否定再翻转 |

题集、rubric、评委配置、`*_final.yaml`、留出集断言都没有改；共用规则（`common/output_policy.py`）没有改；既有测试一条没改。

**新拒和放宽的守卫**（`tests/pipeline/test_bazi_pilot_r20.py`，数据在 `tests/pipeline/fixtures/bazi_pilot_r19_review.json`）：

- **先写大运再说前后步**：
  - 拒：
    - “第1步大运丙辰对应前一步”“第1步大运丙辰指的是前一步大运”“首步大运丙辰对应的是上一步”“第2步大运丁巳对应的是前一步”“第1步大运丙辰对应的是后一步”；
    - 外层否定“不能说第1步大运丙辰不对应前一步”。
  - 放行：“第3步大运戊午对应（的就）是前一步”“第5步大运庚申对应的是下一步”“第1步大运丙辰并不对应前一步”。
- **大运天干的十神**：
  - 拒：
    - “第3步大运戊午，2013年交运，那时天干带伤官主题”“第5步大运庚申（2033年交运），天干为伤官”；
    - 双重否定“……并非不带伤官主题”、外层否定“不能说……不带伤官主题”。
  - 放行：
    - 正确值，如“……天干带正财主题”“首步大运丙辰……天干带伤官主题”“第5步大运庚申……天干为正官”；
    - 否定，如“那时天干不是伤官，而是正财”“并不带伤官主题”。
- **支持你分批**：
  - 拒：
    - “这段时间的波动更支持分批规划”“更加支持你分批投入”；
    - 外层否定“不能说这段时间不支持你分批规划”、双重否定“并非不支持你分批规划”；
    - 转折后“不支持你分批规划，但支持你分批投入”。
  - 放行：“并不支持你分批规划”“这段时间有家人支持”“更支持你保留余地、先核实财务状况”“正印支持你学习理财知识”。
- **把交易换成不交易的做法**（放宽）：
  - 放行：本轮原句、“换成‘先学清楚、再做计划’”“适合把积蓄全投改成先核实、再规划”。
  - 仍拒：
    - 负责人定的“改成‘有边界地参与’”；
    - 同句其他交易：“改成‘分批买入’”“改成‘小步验证’”“改成‘先核实’再全投”“改成‘先核实、再规划’，再分批买入”；
    - 程度词插入：“最适合把‘全投’改成‘先核实、再少量买入’”；
    - 先否定后肯定：“改成‘不是先核实而是分批买入’”；
    - 外层否定：“不能说适合把‘全投’改成‘先核实、再规划’”；
    - 双重否定：“不是不适合直接全投，把‘全投’改成‘先核实’也行”；
    - 转折后重新肯定：“……，但其实还是适合全投”。
  - 整稿：投资 #1 首稿在第一稿就提交。
- **前一步之后的“下一步”**（放宽）：
  - 放行：大运 #1、#3 首稿两句不再报“后一步是第4步己未”；“第3步大运戊午之后，下一步是第4步大运己未”仍按戊午算。
  - 仍拒：
    - 换错的下一步：“前一步是……第3步大运戊午，下一步是第4步大运己未”；
    - 前一步写错：“前一步是第2步大运丁巳，下一步是第5步大运庚申”；
    - 转折后：“……，但下一步是第4步大运己未”；
    - 否认正确值：“……，下一步不是第5步大运庚申”；
    - 双重否定：“……下一步并非不是第6步大运辛酉”。
- **日主写在前后步的位置**：
  - 拒：大运 #3 首稿原句、“下一步是日元乙木所在的第5步大运庚申”。
  - 放行：“前一步不是日主乙木所对应的那一步，而是第3步大运戊午”“日主乙木所对应的五行是木，前一步是第3步大运戊午”。
- **否定隔着编号**：
  - 拒：“下一步不是第5步大运庚申”“前一步不是第3步大运戊午”。
  - 放行：“不能说下一步不是第5步大运庚申”“下一步不是第6步大运辛酉”。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和夹具放进 `cc5a4b6` 的独立 worktree 运行：68 项中 35 项以断言失败（全部是 AssertionError，没有导入错误），33 项两边都通过。
- 修订版 68 passed。

**对历史回答的影响**（只用规则扫描回答文本，不重评）：r1–r19 全部归档（684 份成稿逐句、逐层，93 份被检稿件整稿）在两个版本上各重放一遍，7 处结果不同，都在预期内：

- **r19 成稿 2 份**：
  - 大运 #2 新报前后步和十神两条；
  - 投资 #3 新报交易问题（逐句与层级检查都报出）。
- **r19 被检稿件 4 份**：
  - 投资 #1、大运 #1 的误拒消失（大运 #1 仍有“月柱月柱”和共用的“必然”）；
  - 大运 #3 的理由由“后一步是第4步己未”换成日主写在前一步位置；
  - 大运 #2 首稿另报前后步和十神。
- **r15-deepseek-flash 大运 #4 首稿**：“前一步是……首步大运丙辰（……），下一步是第1步大运丙辰”两个版本都拒，后一步由按丙辰算的“第2步丁巳”改为按当前算的“第5步庚申”，后者是作者想说的那一步。

**全量测试**：见 PR 说明。

## 6. 负责人决定（2026-11-16）

| 问题 | 决定 | 落实 |
| --- | --- | --- |
| 投资 #3“这段时间的波动更支持你保留余地、分批规划，而不是一次性押上” | 算放过，r20 补拒 | `BATCH_RECOMMENDED` |
| single 事业 #2 的编造分类（含“节令大寒前”） | 维持叙述类 | 计数表不改 |

## 7. r20 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行，接入与 r15–r19 相同。`docs/verification/p3/bazi-pilot-r20/pricing.yaml` 已放好，与 r19 逐字节相同（`15ea038e…`）。

```powershell
Copy-Item config.yaml reports/config.personal.before-r20.yaml
```

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pathlib; b = pathlib.Path('docs/verification/p3/bazi-pilot-r19/config.experiment.yaml').read_bytes().replace(b'\r\n', b'\n'); pathlib.Path('config.yaml').write_bytes(b.replace(b'\n', b'\r\n'))"
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne 'CA6E52B208B6697DE7A7B8ACCC58604EB87E1A89EAB582DBC4937C138624BAB1') { Copy-Item reports/config.personal.before-r20.yaml config.yaml; throw 'config.yaml 不是约定配置 ca6e52b2' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r20.yaml config.yaml; throw '服务端探针未通过，暂停 r20' }
```

```powershell
if (Test-Path reports/p3-bazi-r20) { Move-Item reports/p3-bazi-r20 ("reports/p3-bazi-r20-old-" + (Get-Date -Format yyyyMMddHHmmss)) }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r20 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r20
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r20/Bazi-single reports/p3-bazi-r20/Bazi-pipeline --answers --output reports/p3-bazi-r20/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r20/Bazi-single reports/p3-bazi-r20/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r20/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r20/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r20/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r20/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r20.yaml config.yaml
```

- 探针结果存为 `docs/verification/p3/bazi-pilot-r20/service-probe.json` 一并发布，execution.md 记下接入地址和模型名。
- **首发证据照 r18 和 r19（`7ee718b`）的范围，一次发齐，全部取自 `reports/p3-bazi-r20/` 这一轮**：
  - 两组 summary 与 source-hashes、raw-manifest.json、trace-manifest.json；
  - comparison.md、paired.json、两份 failures、fabrication-counts.md；
  - pipeline-problems-raw.md、pipeline-problem-counts.md；
  - quality-failures.json、quality-reasons-with-answers.md；
  - supplement-answers.json / .md（36 份全文）；
  - repair-evidence.json（含未展开原稿的 `text`）、repair-quotes.json；
  - run-metadata.json（`measured_checkout_head` 是本 PR 合并提交，run_id 是本轮的）、integrity.json、config.experiment.yaml、service-probe.json、pricing.yaml、execution.md、assessment.md。
- **evidence-manifest 按入库后的字节生成**：先 `git add` 本目录，再用暂存区的字节生成，最后单独 add 它：

```powershell
.venv\Scripts\python.exe -X utf8 -c "import hashlib,json,subprocess; d='docs/verification/p3/bazi-pilot-r20/'; fs=[f for f in subprocess.check_output(['git','ls-files',d],text=True).split() if not f.endswith('evidence-manifest.json')]; m={f[len(d):]:{'sha256':hashlib.sha256(b:=subprocess.check_output(['git','cat-file','blob',':'+f])).hexdigest(),'bytes':len(b)} for f in fs}; open(d+'evidence-manifest.json','w',encoding='utf-8',newline='\n').write(json.dumps(m,indent=2,ensure_ascii=False)+'\n')"
```

```powershell
git add docs/verification/p3/bazi-pilot-r20/evidence-manifest.json
```

- execution.md 里报以下几项：
  - 两组评委和运行的输出 token 中位数：评委按行，运行按“每行输出 ÷ 调用数”；
  - 耗时中位数；
  - 每题输入 token 请注明是否含评委。
- **请在发布前判定编造失败**（写进 `fabrication-reviewed.yaml` 后再生成计数表），r19 这样做了，两组计数表都“完整”。
- r20 结果里请继续逐份看：
  - 投资题有日期的一层与摘要里推荐的分批、分散、试探写法，含“支持你分批”“用小部分资金去试”；
  - 时机题正文时间，含写了月份的“X旬”紧接流月；
  - 大运题：
    - 前后步，含“X对应的是上一步”；
    - 主题与十神，含“那时天干带X”；
    - 岁数、所处位置和五行计数的概括；
  - 性格题里“现在”所指的大运。

**若 r20 满足 B**，下一步是在计划里记“八字代码冻结于 r20 的被测提交”，再按约定跑最终验收集 `p3-bazi-final`（命令届时在 r20 复核里给出）。

## 8. 已知局限

| 局限 | 处理 |
| --- | --- |
| 大运主题只核对“主题（会 / 将）转向 / 转为 / 是 / 为……”和这次的“天干带 / 为 / 是X”，不核对“主题偏向……” | 待负责人决定（r19 复核遗留项）；其他写法仍靠逐份看 |
| “支持你分批”只认“更 / 更加 / 也 / 还是支持”和“支持你 / 您” | 其他推荐说法仍靠逐份看投资题 |
| 把交易换成不交易的做法，只在“推荐词 + 把（积蓄）+交易”紧接“改成 / 换成……”时放宽 | 别的句式仍按原规则 |
| 交易检查不认“适合先核实，再把积蓄全投”“直接全投就好”这类无推荐词、分句开头不是动作的写法（两个版本都放行；离线构造，未在归档回答中出现） | 记作已知局限，靠逐份看 |
| 前后步检查只认“前一步 / 下一步……（是）……X”，不认“下一步其实 / 可能是X” | 两个版本相同；靠逐份看 |
| 写了月份的“X旬”紧接流月按两种方向留 2 天，r3 的“9月上旬流月丙申”刚好超出 1 天 | 待负责人决定（r19 复核遗留项） |
| 显示缺陷（“日主乙木为乙木”、同一编号写两遍、“地支X地支X”、拿首步作下一步的依据） | 按负责人决定，留到主集前 |
| 共用确定性检查 `certainty_claim` 的误拒（本轮大运 #1 首稿的“不代表……必然发生”） | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
| `74acc5a` 改了入库的 config.yaml | `tests/knowledge/test_live_review_regressions.py` 3 项自 `966eb22` 起失败（r15 复核 §8），待负责人决定 |
