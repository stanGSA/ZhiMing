# P3 八字调参集 r2 复核：不满足 B，r3 修复后重跑

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot-r2 结果（`5c0ab98`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[comparison.md](comparison.md)、[integrity.json](integrity.json)、[acceptance.json](acceptance.json)、两组 summary 与 source-hashes、[repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)、[fallback-probe.json](fallback-probe.json)、[title-checks.json](title-checks.json)、[unscored-reviews.json](unscored-reviews.json) |
| 被测代码 | `c683cf6c35e0e064e03e65740d9b1f49fd210ec6`，即 PR #61 合并后加负责人修复，源码指纹 `ca76af32f8251c6b8075f8907a28faa1b7071479514f4a3d919976866626fe62` |
| 实验配置 | `3dfa2e81…`，八字约定配置 |
| 方法 | 离线：重算指纹，逐文件对照 `c683cf6`；核对模型、raw_sha256、evidence-manifest 和评分；降级链在 `c683cf6` 的独立 git worktree 里用原稿复现。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-09 |

## 1. 结论

**P1 四条里，流水线一侧满足；“已提交质量 ≥ 同批 single”无法判断，因为 single 有 9 条已提交回答没有评分。按 B 不冻结**，原因有二：

- 降级输出里有一处可定位的放过；
- single 的计数表不完整。

r3 修降级链的三处问题，配了离线测试。

| B 条件 | r2 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | single 已提交 14 条里有 9 条未评分（评委连接错误），计数表“不完整”。流水线事实类 1 条，是代码写的降级稿（§3.2），属实 |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 3 次修复：两次是重复标签；一次是正文展开后超长，属于真实的长度上限，不是误拒（§3.1） |
| 没有已知放过 | **不满足** | 投资 #1 的降级稿把“甲己合”接在丙辛合、丁壬合后面，三句都通过了 `Bazi.problems`（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 无法判断 | 流水线 13/18（72.2%）；single 已评分的 5 条里通过 3 条，另有 9 条未评分，区间是 3/14 至 12/14 |

- 单看 r1 的两项问题（标题漏拦、引号里的否定误拒），r2 都没有再现。负责人用新检查核对了 39 个时间标题，没有问题。
- 叙述类：流水线 1/18（5.6%），达到 ≤ 10% 的争取值。
- 未评分行按约定作为服务故障保留，不补评、不剔除。它影响了 B 的“两组完整”和质量比较，我在上面如实写明。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 相同，183 项，重算得 `ca76af32…` |
| 覆盖范围 | 与 `c683cf6` 按同一规则取样的文件列表相同，不缺不多 |
| 被测提交 | 除 config.yaml 外 182 个文件与 `c683cf6` 逐文件一致；与当前分支头也一致（`5c0ab98` 只多了 docs/） |
| 配置 | `3dfa2e81…` |
| 模型 | 两组的请求、返回和评委都是 `deepseek-v4.1-flash`。single 的 12 条未评分行没有评委返回模型（连接错误） |
| raw 与发布文件 | raw_sha256 与 raw-manifest 一致；evidence-manifest 的 31 个文件按字节一致 |
| 评分 | 流水线 18/18；single 6/18，12 条为 `APIConnectionError`，见 [unscored-reviews.json](unscored-reviews.json) |
| 追问 | 海外题 3 次都只问 1 次真太阳时，澄清是新的“不用真太阳时。”；收尾都写明了出生时刻的排盘口径和日期所用时区 |
| 题集 | 海外题澄清按负责人 2026-11-09 的决定改过，这一题与 r1 不完全可比；其余题目和 rubric 没改 |

## 3. 归因

### 3.1 三次修复

| 样本 | 首稿问题 | 归因 |
| --- | --- | --- |
| 大运 #1 | 年柱年柱、时柱时柱、月柱月柱、日主日主、日柱日柱 | 真错误，一次修好。该条质量失败另有原因：叙述类，写了童年、学校里的表现 |
| 大运 #3 | 年柱年柱、月柱月柱、日柱日柱、时柱时柱 | 真错误，一次修好，质量通过 |
| 投资 #1 | 两稿都在提交时被拒：`sections.1.body` 超过 1200 字 | 真实上限，但修复请求帮不上忙，见下 |

投资 #1 的长度问题，我在 `c683cf6` 的 worktree 里用原稿复现：

| 稿 | 第 2 层原文 | 编号 | 展开后 |
| --- | --- | --- | --- |
| 第 1 稿 | 396 字 | 24 个 | 约 1400 字 |
| 第 2 稿 | 336 字 | 22 个 | 约 1350 字 |

- `compose.parse` 检查的是原文长度，所以两稿都过了格式检查，到提交时才被 schema 拒绝。
- 修复请求里只有一句“String should have at most 1200 characters”，写作者看不到展开后的长度。第二稿只删了两个编号，仍然超长，于是降级。

### 3.2 已知放过：降级稿里的关键词

- 降级稿由 `Bazi.degraded` 写，每条事实后面接释义的前三个关键词。
- “天干合”这个条目的关键词依次是天干合、天干五合、甲己合、乙庚合、丙辛合……。所以丙午与辛亥、辛丑与丙寅（丙辛合）、壬寅与丁亥（丁壬合）这三条后面都接上了“甲己合”。
- 最后一层按 1200 字硬截，停在“常和地支刑、地支相刑、相”。
- 这些都是代码写错的，属可核验事实的错配。负责人的 [fallback-probe.json](fallback-probe.json) 已复现，我同意。
- 降级稿的摘要只说“这是……的计算”，没有回应“该不该把积蓄投进股市”。

同一份关键词也出现在事实表里，写作者看到的也是“甲己合……”。本批没有写作者因此写错，但这是同一个来源。

### 3.3 其余质量失败（流水线）

| 样本 | 维度 | 归因 |
| --- | --- | --- |
| 大运 #1 | fabricated | 写了“如果你回看童年到青少年阶段……在家里、学校里更愿意自己拿主意”，带“如果”“可能”限定，但仍是在推测用户过去的经历。r3 的提示词加了一条：不推测用户过去在哪个年龄段发生过什么 |
| 投资 #1 | direct、supported、fabricated | 降级稿（§3.2）。评委另说乙巳、戊申、己酉等流月不存在，说没有投资风险提示，这两条都不成立 |
| 海外 #2 | time、supported | 计算范围和时区正确；“缺乏金水调候”、月令与十神混用属撰写问题，原分保留 |
| 文字出生资料 #2 | time | 评委要求“下半年”只算剩余日期，并把次年零点的右开端点读成多算了一天；与约定的 7 至 12 月整段口径不符，原分保留 |
| 投资 #3 | time、supported | 年内由丙午转丁未、UTC 与北京时间的边界都对；用八字推出股票资金配置的支撑问题保留 |

## 4. r3 的改动（本 PR）

| 改动 | 内容 | 测试 |
| --- | --- | --- |
| 展开后的长度（`Bazi.length_problems`） | 提交前就检查每层展开编号后的长度，超过 1200 字直接要求修复：“第 N 层正文的编号展开成事实后有 X 字……把这一层拆成两层，或少引几个编号” | 端到端：一层塞进全部编号，一次修复通过、不降级，提交只调用一次 |
| 关系事实的文字缩短 | 流期与原局的关系只写日期，例如“（12月7日至12月31日）”；流年流月自己的事实仍保留精确时刻和时区 | 端到端：关系行没有时刻和时区，流月行保留 |
| 只用本条的配对关键词（`relevant_keywords`） | 写出具体配对或组合的关键词（甲己合、申子辰）只在事实本身就是它时保留。事实表和降级稿都用这个规则 | r2 的三句原文：保留丙辛合或丁壬合，去掉甲己合；三合组合同理 |
| 降级稿按整句分层 | 不再硬截；一组写不下就分到下一层（最多 6 层）。高风险问题的摘要先回应：“八字只能作反思参考，不能决定这类现实中的重大决定” | 端到端：每层 ≤ 1200 字且以句号结束，所有配对关键词都与本句的干支一致（这张盘 2027 年确有丙辛合，检查不是空跑） |
| 提示词 | 一层引用的编号不超过 8 个；不推测用户过去的经历 | — |

- 3 个行为测试在 `c683cf6` 上失败，在 r3 上通过（独立 worktree 核对）。
- 两份题集都没改。

## 5. 主动说明

- **PR #61 的标题样本没有提交上去。** 我把它放在 `tests/pipeline/data/`，被 `.gitignore` 的 `data/` 规则忽略了，所以合并后的测试缺文件。负责人已移到 `tests/pipeline/fixtures/`。
- **负责人同时修了我写的时间解析。** “十二月中下旬”“12月上旬之后”读窄了；“春风得意”“秋后算账”的单字被当成季节；“底色”被当成月底。这些都是我的疏漏。

## 6. r3 重跑（负责人本机）

在 r3 合并后的 `claude_modify_model` 上运行，配置仍用 `3dfa2e81…`。`docs/verification/p3/bazi-pilot-r3/pricing.yaml` 已放好，与 r2 逐字节相同：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r3 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r3
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r3/Bazi-single reports/p3-bazi-r3/Bazi-pipeline --answers --output reports/p3-bazi-r3/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r3/Bazi-single reports/p3-bazi-r3/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r3/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r3/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r3/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r3/pipeline-problems-raw.md
```

如果评委连接再出错，请照约定保留，不补评。B 的“两组完整”要求两组都评完；只要有缺口，这一条就不满足。

## 7. 已知局限

| 局限 | 现象 | 处理 |
| --- | --- | --- |
| 评分载荷不含运行日，也不说明出生钟表口径 | 多条 time 理由与约定口径冲突 | 评委配置不改；复核时逐条看理由，原分保留 |
| 单一模型评分不稳定 | 投资 #1 评委称流月不存在、说没有风险提示，都与事实不符 | 原分保留 |
| 喜用、调候和具体场景的写法 | 海外 #2、投资 #3 的 supported 失败 | 提示词已要求写明依据；r3 只加了“不推测过去经历”，先看再现率 |
| 星盘、每日运势的降级稿也是硬截 1200 字 | 本批不涉及 | 主集前一并检查 |
