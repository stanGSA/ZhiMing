# P3 八字调参集 r20 复核：不满足 B；根因与 r21 修法

负责人发布的文件不改；本文件按 r13–r19 的 review-claude.md 的写法补充复核，另加一节回答“为什么一直通不过”。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 r20 结果（`3e5d018`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[fabrication-attribution.md](fabrication-attribution.md)、[offline-review-checks.json](offline-review-checks.json)、两组 summary 与 source-hashes、[run-metadata.json](run-metadata.json)、[integrity.json](integrity.json)、[service-probe.json](service-probe.json)、[evidence-manifest.json](evidence-manifest.json)、[supplement-answers.json](supplement-answers.json)、[repair-evidence.json](repair-evidence.json) 等 31 个文件 |
| 被测代码 | `374d5855b4733fd87166d4474e7d9a7bb6ae0fe6`，即 PR #82 合并（含负责人的 `809ee4d`、`74c0045`）；源码指纹 `648b998b6ec4b8eed7a883852604f89c0d46b70d2004034d96ac1263e35eec35` |
| 接入与配置 | 约定：官方 `https://api.deepseek.com`，运行与评委都是 `deepseek-flash`，实验配置 `ca6e52b2…`；评委 thinking=disabled、不设 reasoning_effort、max_tokens=8192 |
| 方法 | 离线：<br>- 重算指纹，184 项逐文件对照被测提交（config.yaml 单列）；<br>- 核对配置、探针、evidence-manifest 和评分完整性；<br>- 3 份被检稿件按 r20 运行时钟（`20261116T164415`）整稿重放，18 份流水线成稿逐句、逐层重放；<br>- 逐份读 18 份流水线成稿；<br>- 汇总 r11–r20 各轮挡住 B 的问题，找根因；<br>- r21 的改动用 r1–r20 全部归档回答（720 份成稿逐句、逐层，96 份被检稿件整稿）在两个版本上各重放一遍。<br>没有改共用规则，没有调用模型 |
| 日期 | 2026-11-17 |

## 1. 结论

**不满足 B，不冻结。** 我同意负责人在 [assessment.md](assessment.md) 的判断。3 处漏检在 `374d585` 上重放属实，都是整稿和逐句检查放行：

- **事业 #3（事实类，评委判出）**：“首步大运己丑（1998年交运，2008年换下一步）已走到后半段”。2026 年所在的是丁亥（2018—2028）。首稿就写了“{{R3}}已走到后半段”，R3 是起运和首步那一条，修复只改了分层。这与 r13 事业 #3 是同一题、同一个错。
- **大运 #3（事实类，评委判通过）**：“再往后到第4步大运己未（2023年交运，2033年换下一步）就是第5步大运”。第5步是庚申。
- **投资 #2（交易边界）**：有日期的一层写“只用亏得起的小部分去验证判断”。按负责人 2026-11-17 的决定，同一份成稿“8月到年底”一层的“先补齐应急金、核实负债和收入稳定性，再谈是否小额参与”也算放过。

其余结果：
- 流水线提交 18/18，调用最多 2 次，修复 3 次，降级 0；
- 3 次修复都是真问题，没有误拒；
- 已提交质量 13/18（72.2%），single 为 10/14（71.4%）；
- 两组计数表都“完整”。

| B 条件 | r20 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次，共 21 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 计数表都“完整”，但流水线事业 #3 是事实类；另有大运 #3 的事实漏检 |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 3 次修复的首稿都有真问题（§3.1） |
| 没有已知放过 | **不满足** | 事业 #3、大运 #3、投资 #2（两句） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 13/18（72.2%）对 10/14（71.4%） |
| （前提）约定接入与配置 | 满足 | §2 |

| §5 指标（参考） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 2 份：事业 #3（计数表内）、大运 #3（评委判通过） | 1 份：事业 #3（“12月7日小寒前”） |
| 叙述编造（不高于 single，争取 ≤ 10%） | 2/18（11.1%） | 2/14（14.3%） |
| 降级比例（≤ 10%，监控项） | 0/18 | — |
| 每题模型调用（≤ 3） | 约 1.17（21/18），最多 2 | 约 5.94（107/18），最多 9 |
| 每题运行输入 token（≤ 20,000，不含评委） | 约 5,417 | 约 37,988 |
| P95 耗时（≤ 90 秒） | 8.8 秒（线性插值；execution.md 的另一种取法为 10.3） | 24.9 秒（另一种取法为 27.3） |
| 已提交回答质量通过率 | 13/18（72.2%） | 10/14（71.4%） |

统计只作参考；6 题各重复 3 次，不是 18 个独立样本。运行和评委都是 `deepseek-flash`，同模型评分，不是独立评审。

## 2. 为什么 r11–r20 一直通不过

**原因不是修过的说法原样复发，而是两类错误每轮换一种说法再出现，而每轮的修复又只补那一种说法。** 按计划里的记录，r11–r20 挡住 B 的已知放过约 26 处，其中 22 处属于两类：

| 类别 | 次数 | 各轮写法 |
| --- | ---: | --- |
| 大运的角色或位置写错（首步、前后步、当前、第几步） | 14 | r11“往前一步是第1步”、r12“中段偏后”、r13“首步己丑……后半段”、r15/r18“首步辛未……现在”、r16/r18/r19“第1步丙辰……前一步 / 上一步”、r18“日柱……前一步”、r18 主题、r20“首步己丑已走到后半段”“第4步己未就是第5步”等 |
| 投资题有日期的层里出现试探性投入 | 8 | 分批（r12）→ 以分批为主、小范围验证（r14）→ 小步验证（r15）→ 分散（r17）→ 小比例验证（r18）→ 支持分批（r19）→ 小部分验证、再谈小额参与（r20） |

**根因 1：时机题和性格题的事实表里，唯一能引用的大运事实是起运和首步那一条。**
- 那条事实写作“1998年6月26日起运……首步大运己丑（1998年交运，2008年换下一步）”，当前大运只在上下文的说明里出现。
- `pipeline/bazi.py` 里 r3 的注释已经记下这个陷阱：“the only luck-cycle fact on a timing sheet is the first one”。之后各轮的修法都是加提示、拒具体说法，事实表本身没改过。
- 结果是 14 处大运错误里，有 8 处把首步或第1步当成了当前、前一步或上一步。r13 和 r20 的事业 #3 是同一题、同一个错。

**根因 2：写手引用事实后，又用自己的话重述一遍，而检查是逐个说法追的。**
- r20 大运 #3 引用的事实都对，接着写了“再往后到第4步大运己未……就是第5步大运”。
- 大运检查已有几十个针对具体写法的正则，只能拦见过的说法。每轮 18 份回答、几百句话，出现一种新说法几乎是必然的。

**根因 3：交易边界是“默认放行、事后逐例判放过”。**
- r7 的规则是“只拒明确推荐，其余默认放行”，之后各轮陆续把 8 种试探性投入判为放过。
- 默认放行的检查追不上事后划定的边界。
- 例如 r18 补了“只用小比例、可承受损失的部分去验证判断”，r20 写成“只用亏得起的小部分去验证判断”就漏了：正则要求“只用”后紧接“小部分”。

**负责人 2026-11-17 的决定（r21 的修法）：**
- **大运：** 从源头改事实表，并改为按排出的序列核对角色，不再逐个追说法。
- **交易：** 投资题有日期的层和摘要改为默认拒投入，只放行核实、预算、应急金、学习、暂缓、不投入这类做法。
- r20 投资 #2 “再谈是否小额参与”那一句，按新规则处理（算放过）。

## 3. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，184 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `648b998b…`，与 execution.md、两份 summary、run-metadata.json、integrity.json 一致。键集合与 r19 相同，内容只有 `pipeline/bazi.py` 一项不同 |
| 被测提交 | 184 项中除 config.yaml 外 183 项与 `374d585` 逐文件一致；`374d585..3e5d018` 只动了本目录 |
| config.yaml 一项 | `ca6e52b2…`；入库的 config.experiment.yaml 为 LF（`2ec411fa…`），与 r19 的逐字节相同，换成 CRLF 即 `ca6e52b2…` |
| 模型与探针 | 两组 summary 的 requested / judge model 都是 `deepseek-flash`，返回模型名一致；[service-probe.json](service-probe.json) 三项通过，输出 1、21、1 token |
| evidence-manifest | 列 31 个文件（不含它自己），按 `3e5d018` 入库字节逐一重算，sha256 和字节数全部一致，目录里没有漏列的文件 |
| pricing.yaml | `15ea038e…`，与 r19 相同 |
| 评分完整性 | 两组 36 行全部有四维评分；评委每行输出最大 769 token（流水线）/ 568（single），远低于 8192 的单次上限；`usage_missing_calls` 全部为 0 |
| token 中位数 | 评委每行输出：流水线 375、single 367（r19 为 336、344.5；r13 为 337）；运行每次调用输出：流水线 653、single 395.2（r19 为 683.5、473.0）。服务端行为与 r13、r15–r19 相当 |

## 4. 归因与逐份复核

### 4.1 修复（3 次，都不是误拒）

| 题目 | 首稿问题 | 判断 |
| --- | --- | --- |
| 大运 #2 | 引用事实表里没有的 R13、R14，4 项编号错误 | 真问题，一次修复后通过 |
| 性格 #3 | 自写“月令偏印气”（命局和当前大运都没有偏印），另有“年柱年柱”“时柱时柱” | 真问题，一次修复后通过 |
| 事业 #3 | 标题“12月7日起”的层里放了 12月1日—7日的流月己亥 | 真问题，一次修复后通过；首步当现在的错误首稿就有，修复没有引入 |

3 份首稿在 `374d585` 上整稿重放，问题与记录逐条相同。

### 4.2 漏检

见 §1。18 份流水线成稿在 `374d585` 上逐句、逐层重放，没有任何问题，与负责人的 [offline-review-checks.json](offline-review-checks.json) 一致。

### 4.3 质量失败与编造分类

我同意负责人在 assessment.md 的分析和已确认的六项分类：
- 流水线事业 #1 判为叙述类，理由有争议；
- 投资 #1、#2 的时间理由是评委误读；
- 文字出生 #3 评委说“丙午与己丑无害”，与计算不符（丑午相害）。

这几项都与修复无关。

```yaml
# r20 编造分类：负责人已于 2026-11-17 确认（fabrication-reviewed.yaml），这里不改。
Bazi-single:
  bazi_pilot_investment_risk#1: [叙述类]
  bazi_pilot_next_month_career#3: [事实类]
  bazi_pilot_typed_birth#3: [叙述类]
Bazi-pipeline:
  bazi_pilot_next_month_career#1: [叙述类]
  bazi_pilot_investment_risk#1: [叙述类]
  bazi_pilot_next_month_career#3: [事实类]
```

### 4.4 逐份阅读（18 份流水线成稿）

- **投资 #1、#3**：有日期的层和摘要只有核实、预算、应急金、克制冲动这类内容。
  - 投资 #3 建议里的“先留后投”和投资 #2 建议里的“只有最后一份才谈得上参与波动市场”不带日期，不在 B 的范围内；按负责人的决定不算放过。
  - 投资 #2 见 §1。
- **大运 #1、#2**：起运 1993-02-10、虚岁 6 岁、顺排、当前第4步己未（2023—2033，第4年，前半段）都写对了；大运 #2 写的前后步戊午、庚申也对。
  - 大运 #2“己未这步的中段”在负责人定的宽容范围内。
  - “日主乙木是乙木日主”是已记的显示缺陷。
- **大运 #3**：见 §1；同一层的“前一步是第3步大运戊午，2013年交运”是对的。
- **性格 #1—#3**：“现在”都指己巳（2017—2027）。
  - 性格 #1 写“走到第10年、2027年换下一步”“前一步是庚午、下一步是戊辰”，都对。
- **事业 #1、#2，海外 #1—#3**：12月7日 10:52 换月（海外为 12月6日起）的边界写对，没有发现“X旬”紧接流月的错配。
  - 事业 #3 见 §1。
- **文字出生 #1—#3**：下半年各层与流月起止一致。“10月到年底”“年底”这类说法在已定口径内。

## 5. r1–r19 已修问题是否再现

| 问题 | r20 |
| --- | --- |
| 首步当现在（r13 事业 #3、r15 / r18 性格 #1） | **再现**：事业 #3，换成“已走到后半段”，现有 `STAGE_EVIDENCE`、`PRESENT_STAGE` 都没认出 |
| 前后步与第几步（r11、r16、r18、r19 大运） | **同类再现**：大运 #3，换成“第4步……就是第5步” |
| 试探性投入（r14、r15、r18 投资） | **再现**：投资 #2，“只用亏得起的小部分”，`TRIAL_FUNDS` 要求“只用”后紧接“小部分” |
| 支持你分批（r19 投资 #3） | 没有再现 |
| 交易换成核实（r19 投资 #1 误拒） | 没有再现 |
| 大运天干十神（r19 大运 #2） | 没有再现 |
| 日主写在前后步的位置（r19 大运 #3） | 没有再现 |
| 起运、虚岁、顺逆排、相邻大运、所处位置、五行计数、标题与正文时间、“稳赚”提及、十神并列 | 没有再现 |

## 6. r21 的改动（本 PR）

### 6.1 大运：从源头改，按序列核对

| 改动 | 内容 |
| --- | --- |
| 当前大运成为一条事实（`plugins/bazi/tools.py` `chart_atoms`、`Bazi.texts`、`Bazi.facts`） | 时机题和性格题（不问大运概览时）的事实表，除起运那条外多一条标“当前大运”的事实，例如“第3步大运丁亥（2018年交运，2028年换下一步）”，排在起运那条后面。当前大运是首步时不加，大运概览题不变。<br>这条事实（`dayun_current`）只放在计算结果里，不出现在模型读到的工具结果中（`BaziPlugin.project`）。所以 single 组看到的和以前一样，流水线其余事实的 R 编号也不变：新事实最后编号 |
| 大运题标签 | 不变，各步仍标“大运”（既有测试要求大运题至少 3 条“大运”）。原想按“首步 / 当前”给大运题各步标角色，没有做 |
| 按序列核对角色（`cycle_role_problems`，新） | 每个分句里写到的大运（“第N步大运X”“首步大运X”“X大运”“大运X”）先对应到排出的某一步：<br>- 分句里没写到当前那一步、却说“现在 / 目前 / 正走 / 已走到 / 走到后半段”的，拒；<br>- 括号里的交运说明不算断句；<br>- 否认（“现在不是首步大运己丑”）、另说别的时间（“早已过去 / 之后 / 那时 / 下一步”）、同句也写到当前那一步的，放行；<br>- 外层否定、程度词、转折后重新肯定仍拒 |
| 步数等同（`EQUATED_STEP`，新） | “第A步大运（X）（……）（就 / 也就 / 即）是第B步”，A≠B 就拒 |

这里的“按引用核对”，实际做的是**按排出的序列核对**，不要求写到的大运必须是引用的事实：时机题和性格题的事实表里没有前一步、下一步，强制引用会把写对的“前一步是庚午”也拒掉（性格 #1）。

### 6.2 交易：投资题有日期的层和摘要默认拒投入

| 改动 | 内容 |
| --- | --- |
| `entry_offered`、`ENTRY_PROBLEM`（新） | 投资题有日期的层和摘要里，以下写法没被否定就拒：<br>- 任何数额的投入：少量、小额、小部分、一部分、小比例、轻仓 + 验证 / 试 / 参与 / 投 / 买；<br>- 投入节奏：分批、分散、定投、小步、小范围、试水；<br>- 入场：参与、入场、进场、建仓、加仓、加码、上车、买入；<br>- 延后的投入：“再 / 才 / 然后谈（是否）……投入 / 参与 / 投资”。<br>以下情况放行：<br>- 否定：“不建议分批”“别急着加仓”“它不参与任何行情”“与其分批不如……”；<br>- 描述读者的状态、冲动或别人的说法：“如果你正想分批买入”“手一快就加仓”“那种‘再不上车就晚了’的感觉”；<br>- 往后放：“把重大加仓动作往后放一放”；<br>- 被比下去或被否定评价：“比小额试水更重要的是……”“小额参与也不合适”；<br>- 问句：“要不要分批，取决于……” |
| 写手上下文（`Bazi.context`） | 投资题加一行：“摘要和写了时间的每一层都不建议投入任何数额……只写核实财务、做预算、留应急金、学习、暂缓或不投入。” |

原有的交易检查（`trade_problems`、`batch_recommended`）都保留，新检查是在它们之后补上的。共用规则（`common/output_policy.py`）、题集、rubric、评委配置、`*_final.yaml`、留出集断言都没有改，既有测试一条没改。

### 6.3 测试

测试在 `tests/pipeline/test_bazi_pilot_r21.py`，数据在 `tests/pipeline/fixtures/bazi_pilot_r20_review.json`，取自 r20 的原句和成稿。

- **交易**：
  - 拒：
    - r20 两句原句；
    - 少量参与、一小部分资金试水、用小额去验证、“然后再考虑投入”“才谈得上参与”、以分散配置为主、定投、轻仓入场；
    - 同句其他意象：“先核实财务，再少量买入”；
    - 先否定后肯定：“不是全投，而是分批买入”；
    - 外层否定：“不能说不建议分批买入”“不能说不参与”；
    - 程度词插入：“更加适合小额参与”；
    - 双重否定：“并非不能小额参与”；
    - 转折后重新肯定：“不要急着买入，但可以少量试水”；
    - 描述之后另起推荐：“容易被消息带动，可以先少量试水”；
    - 摘要里的“明年适合小额参与”；
    - 整稿：首稿“只用亏得起的小部分去验证判断”被修复。
  - 放行：
    - r20 投资 #1、#3 全部层、投资 #2 的另两层和三份摘要；
    - 否定、读者状态、冲动描述、往后放、比较、否定评价、问句、核实与预算；
    - “大额投入前先核实清楚”（r11 的误拒）、“注意力容易分散”、不带日期的层。
- **大运**：
  - 拒：
    - r20 事业 #3 原句，“首步大运己丑已走到后半段”“你目前在第1步大运己丑的后半段”“第2步大运戊子正处在中段”；
    - 同句其他意象；
    - 外层否定：“不能说现在不在首步大运己丑”；
    - 程度词：“现在不完全是首步大运己丑这一步”；
    - 转折后重新肯定：“现在不是……，但其实还是首步大运己丑”；
    - r20 大运 #3 原句、“第4步大运己未就是第5步”“第2步大运丁巳即第3步大运”。
  - 放行：
    - 早已过去、起运原句、当前那一步已走到后半段；
    - 否认、之后又走了、同句写到当前那一步；
    - 写到自己的步数（“第1步……是第1步”“第4步之后是第5步”“第4步不是第5步”）；
    - r20 其余大运、性格、事业成稿。
  - 事实表：
    - 事业和性格题有一条“当前大运”，起运那条仍是唯一标“大运”的；
    - 大运题各步仍标“大运”；模型读到的排盘结果里没有新事实；
    - 整稿：引用当前大运写“已走到后半段”第一稿就提交；引用起运那条这样写就修复。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和数据放进 `374d585` 的独立 worktree 运行，73 项中 36 项以断言失败（全部是 AssertionError，没有导入错误），37 项两边都通过。
- 修订版 73 passed。

### 6.4 对历史回答的影响

只用规则扫描回答文本，不重评。r1–r20 全部归档在两个版本上各重放一遍：720 份成稿逐句、逐层，96 份被检稿件整稿。

- **大运**：720 份成稿里只新增 3 处，都是真错，没有误报：
  - r13 事业 #3“首步大运己丑……显示你正走在这步十年大运的后半段”（原来已由 `STAGE_EVIDENCE` 报，这里多一条同义的报告）；
  - r20 事业 #3；
  - r20 大运 #3。
- **交易**：120 份投资成稿中：
  - 流水线 60 份里有 20 份、共 31 句新被拒；single 60 份里有 38 份；
  - 流水线 31 句里，23 句是带数额、节奏或入场的投入，属于新规则要拒的；
  - 另 8 句只是“先……再谈投入 / 投资”，例如 r8 投资 #1“先把预算和风险承受能力算清楚，再谈投入与否”、r9 投资 #3“把资金分层、留足应急储备，再谈投资”、r14 投资 #3“再谈任何投入”。这一类此前没有判为放过，按负责人选定的规则（含“再谈投入”）现在也拒，见 §7。
  - 这些回答当时都已提交。如果 r21 的写手仍这样写，会多一次修复，不会直接失败。写手上下文里已经写明这条规则。
- **被检稿件**：编号不变，96 份照原样整稿重放：96 份里 9 份结果不同，都只是在原有问题上多报一条，被拒与否没有变化：
  - r20 事业 #3 首稿：新报首步当现在（真错）；
  - 8 份投资稿件（r1、r3、r6、r9、r10、r15 各 1 份，r7 2 份）：新报投入。

## 7. 负责人确认（2026-11-17）

1. **“先……再谈投入 / 投资”**：按您选的规则，这类说法也拒，归档里流水线有 8 句，此前都没有判为放过。**负责人确认不收窄**，r21 按现规则跑。
2. **按序列核对，而不是按引用核对**（理由见 §6.1 末尾）：**负责人确认可以。**
3. **大运题没有按角色标注各步**：提问时说过要给大运题的各步标上“首步 / 当前”，实际做时发现既有测试要求大运题的各步都标“大运”，而既有测试不能改，所以没有改标签，只靠按序列核对。**负责人确认可以。**
4. **当前大运事实只给流水线**：它不出现在模型读到的工具结果里，single 组和以前一样，对照组不变；附录说明另加了 `dayun_current` 的名称（`common/evidence.py`），共用的输出规则没有改。**负责人确认可以。**

## 8. r21 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行，接入与 r15–r20 相同。`docs/verification/p3/bazi-pilot-r21/pricing.yaml` 已放好，与 r20 逐字节相同（`15ea038e…`）。

```powershell
git checkout claude_modify_model; git pull; git log -1 --oneline
```

```powershell
Copy-Item config.yaml reports/config.personal.before-r21.yaml
```

```powershell
.venv\Scripts\python.exe -X utf8 -c "import pathlib; b = pathlib.Path('docs/verification/p3/bazi-pilot-r20/config.experiment.yaml').read_bytes().replace(b'\r\n', b'\n'); pathlib.Path('config.yaml').write_bytes(b.replace(b'\n', b'\r\n'))"
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne 'CA6E52B208B6697DE7A7B8ACCC58604EB87E1A89EAB582DBC4937C138624BAB1') { Copy-Item reports/config.personal.before-r21.yaml config.yaml; throw 'config.yaml 不是约定配置 ca6e52b2' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r21.yaml config.yaml; throw '服务端探针未通过，暂停 r21' }
```

```powershell
if (Test-Path reports/p3-bazi-r21) { Move-Item reports/p3-bazi-r21 ("reports/p3-bazi-r21-old-" + (Get-Date -Format yyyyMMddHHmmss)) }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r21 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r21
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r21/Bazi-single reports/p3-bazi-r21/Bazi-pipeline --answers --output reports/p3-bazi-r21/quality-reasons.md
```

判定编造失败、写进 `reports/p3-bazi-r21/fabrication-reviewed.yaml` 后：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r21/Bazi-single reports/p3-bazi-r21/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r21/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r21/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r21/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r21/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r21.yaml config.yaml
```

- 探针结果存为 `docs/verification/p3/bazi-pilot-r21/service-probe.json` 一并发布，execution.md 记下接入地址和模型名。
- **首发证据照 r20（`3e5d018`）的范围，一次发齐，全部取自 `reports/p3-bazi-r21/`**：
  - 两组 summary 与 source-hashes、raw-manifest.json、trace-manifest.json；
  - comparison.md、paired.json、两份 failures、fabrication-counts.md、fabrication-reviewed.yaml；
  - pipeline-problems-raw.md、pipeline-problem-counts.md；
  - quality-failures.json、quality-reasons-with-answers.md；
  - supplement-answers.json / .md（36 份全文）；
  - repair-evidence.json（含未展开原稿的 `text`）、repair-quotes.json；
  - run-metadata.json（`measured_checkout_head` 是本 PR 合并提交）、integrity.json、config.experiment.yaml、service-probe.json、pricing.yaml、execution.md、assessment.md。
- **evidence-manifest 按入库后的字节生成**：先 `git add` 本目录，再用暂存区的字节生成，最后单独 add 它：

```powershell
.venv\Scripts\python.exe -X utf8 -c "import hashlib,json,subprocess; d='docs/verification/p3/bazi-pilot-r21/'; fs=[f for f in subprocess.check_output(['git','ls-files',d],text=True).split() if not f.endswith('evidence-manifest.json')]; m={f[len(d):]:{'sha256':hashlib.sha256(b:=subprocess.check_output(['git','cat-file','blob',':'+f])).hexdigest(),'bytes':len(b)} for f in fs}; open(d+'evidence-manifest.json','w',encoding='utf-8',newline='\n').write(json.dumps(m,indent=2,ensure_ascii=False)+'\n')"
```

```powershell
git add docs/verification/p3/bazi-pilot-r21/evidence-manifest.json
```

- execution.md 里报以下几项：
  - 两组评委和运行的输出 token 中位数：评委按行，运行按“每行输出 ÷ 调用数”；
  - 耗时中位数；
  - 每题输入 token 请注明是否含评委。
- **请在发布前判定编造失败**，r19、r20 都这样做了。
- r21 结果里请重点看：
  - **投资题的修复次数和降级**：新规则下写手如果仍写“再谈投入”“小额验证”，会多一次修复；如果出现降级，请把首稿和修复稿一起发布，以便判断是误拒还是写手没照做；
  - 事业、性格题是否引用了新的“当前大运”事实；
  - 大运题里第几步、前后步与“现在”的写法。

**若 r21 满足 B**，下一步是在计划里记“八字代码冻结于 r21 的被测提交”，再按约定跑最终验收集 `p3-bazi-final`（命令届时在 r21 复核里给出）。

## 9. 已知局限

| 局限 | 处理 |
| --- | --- |
| 按序列核对角色只认“现在 / 目前 / 眼下 / 如今 / 当下 / 正走 / 正处 / 已走到 / 走到后半段（第N年）”这些现在时的词；分句里只要也写到当前那一步就不查 | 其他写法仍有原有的逐句检查和逐份阅读兜底 |
| 步数等同只认“第A步大运（X）（……）是第B步”紧挨着的写法 | 同上 |
| 投资题新规则只覆盖有日期的层和摘要；建议和收尾不在 B 的范围内 | 按负责人决定 |
| “是否 / 要不要分批”这类问句放行；单独的“投入”“投资”（不带数额或节奏）仍由原交易检查处理 | 若负责人认为问句也算推荐，可再收紧 |
| r19 复核遗留：大运“主题偏向……”不核对；“9月上旬流月丙申”刚好超出 1 天；“适合先核实，再把积蓄全投”“直接全投就好”“下一步其实是X” | 待负责人决定。“下一步其实是X”这类写法在本轮的按序列核对里仍不查（没有现在时的词） |
| 显示缺陷（“日主乙木是乙木日主”、同一编号写两遍、“地支X地支X”） | 按负责人决定，留到主集前 |
| 测试环境 | 离线测试未取得 de440s.bsp，11 项 Skyfield 测试和 `test_doctor_week1_required_checks` 失败；环境性失败，不是回归 |
