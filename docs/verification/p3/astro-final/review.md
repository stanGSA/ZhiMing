# P3 星盘最终验收复核：满足 P1 四条和 §5，星盘完成

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 astro-final 结果（`27019dd`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[comparison.md](comparison.md)、[integrity.json](integrity.json)、[acceptance.json](acceptance.json)、两组 summary 与 source-hashes、[repair-attribution.md](repair-attribution.md)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[temporal-evidence.json](temporal-evidence.json)、[unscored-reviews.json](unscored-reviews.json) |
| 被测代码 | 冻结合并 `d7c3ff89f6e39f48f41038be781e85e7fdbd0cf1`，源码指纹 `1b96414d8332a4c3388150b99d6992d94117296a13030fe0f99ba1dc0a5ff53c` |
| 运行提交 | `babeceaad67d2ab8887cbc30041b568aece4051e`（`d7c3ff8` 之后只多了 docs/，符合 r4 复核 §5 的运行条件） |
| 实验配置 | `248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`，即约定的配置 |
| 方法 | 离线：重算源码指纹，逐文件对照 `d7c3ff8`、`babecea` 和当前 `claude_modify_model`；核对 raw_sha256 与 evidence-manifest；逐行读两组 summary。修复、质量失败、编造分类逐条对照原句，并在 `d7c3ff8` 的独立 git worktree 里用原文做最小对照（§3）。没有调用模型，没有改动负责人发布的任何文件 |
| 日期 | 2026-11-08 |

## 1. 结论

**星盘最终验收集满足 P1 的四条通过条件，§5 编造指标的硬性目标和争取值也都满足。星盘完成，可以开八字 PR。**

| 条件（以最终验收集为准） | 结果 | 依据 |
| --- | --- | --- |
| 已提交 100% | 12/12 | 12 行结局都是 `submit_reading` |
| 步数和预算失败 0 | 0 | 没有 `retry_limit`、超时或预算结局 |
| 每轮调用 ≤ 3 | 最多 2 | 11 行 1 次；海外 #3 修复一次，共 2 次。海外题的时区追问由代码发出，不占模型调用 |
| 已提交质量 ≥ 同批 single | 11/12（91.7%）≥ 7/8（87.5%） | 唯一失败是海外 #2 的 `time_consistent`，归因见 §3.2 |
| §5 可核验事实编造 = 0 | 0 | 流水线 `no_fabricated_facts=false` 为 0 条 |
| §5 叙述编造 ≤ 同批 single | 0/12 ≤ 1/8 | 两组计数表都“完整”，可以计数 |
| §5 叙述编造争取 ≤ 10% | 0% | — |

需要如实说明的三点，都不改变上表的判定：

- **流水线唯一的质量失败不归给产品。** 海外 #2 被判 `time_consistent=false`，评委自己逐项核对后承认日期全对，理由只是“没法确认下个月是 2026 年 12 月”。代码按运行日算出的范围确实是 12 月（§3.2）。原分保留，质量仍按 11/12 报告；即使把它算作产品问题，11/12 仍高于 single 的 7/8。
- **single 是 8 条已提交里比较。** single 有 3 行 `retry_limit`、1 行停在追问，这 4 行不在已提交分母里。按全部请求算，流水线任务完成且质量通过 11/12，single 7/12。
- **这批没有触发分段日期修复。** 唯一一次修复是“本命本命”。r4 新增的分段引句在真实模型上的证据仍只有 r4 那一条，本批不能当作新的压力验证。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 内容相同，共 179 项；按 `scripts/live_week23.py` 的算法（`sha256(json.dumps(hashes, sort_keys=True))`）重算得 `1b96414d…`，与两份 summary、execution.md、integrity.json、run-metadata.json 一致 |
| 覆盖范围 | 按同一脚本的取样规则（harness、agents、common、pipeline、plugins、knowledge、memory、scripts、evals/cases 下的 .py/.yaml，加 app.py、config.yaml、uv.lock）列出 `d7c3ff8` 的文件，与 source-hashes 的 179 项完全相同，不缺不多 |
| 被测提交 | 除 config.yaml 外的 178 个文件与 `git show d7c3ff8:<path>` 逐文件 SHA256 一致；与运行提交 `babecea`、当前 `claude_modify_model` 也逐文件一致。`d7c3ff8` 到当前分支头之间没有 docs/ 以外的改动 |
| 配置 SHA256 | source-hashes 中 config.yaml 为 `248e6db0…`，与约定一致；本机个人配置运行后已按原字节恢复（`d20f8ebd…`） |
| 请求和返回模型 | 两组 summary 的 `requested_model`、`judge_model` 都是 `deepseek-v4.1-flash`；24 行的 `returned_models` 和 `review_usage.requested_model / returned_model` 也都是 `deepseek-v4.1-flash`。是同一模型评分，不是独立评审；`--judge pro` 只是角色名 |
| 原始报告 | 两组 summary 的 `raw_sha256` 与 raw-manifest.json 逐一相同 |
| 发布文件 | evidence-manifest.json 列出的 26 个文件按工作区字节重算 SHA256 全部一致；清单不含它自己，也不含本复核文档 |
| pricing.yaml | 与 `8aea103` 放好的版本逐字节相同 |
| 评分完整性 | 24/24 行四个维度都是布尔值；`unscored-reviews.json` 为空 |
| 追问 | 流水线海外题 3 次都 `asks=1`，收到“按北京时间。”后按 `Asia/Shanghai` 计算 2026-12-01 至 12-31；指定月份题都是 2027-03-01 至 03-31；下周题都是 2026-11-09 至 11-15 |
| 结局 | 流水线 12 行都是 `submit_reading`。single：`submit_reading` 8、`retry_limit` 3、`ask_user` 1 |

## 3. 修复、质量失败与编造的归因

最小对照脚本在 `d7c3ff8` 的独立 worktree 里运行，直接导入冻结代码的 `pipeline.astro` 和 `plugins.astro.calculator`，输入取自发布文件的原文。

### 3.1 唯一的修复：海外 #3，“本命本命”

- 首稿写了 `结合你本命{{R7}}…`，R7 渲染出来是“本命土星在水瓶座”，所以成了“本命本命”。这是真错误，不是误拒。
- 冻结代码的 `REPEATED_LABEL` 在渲染后的首稿里命中 `本命本命`，在最终回答里命中 0 处。
- repair 事件引的那一句在首稿里原样存在，最终回答里已经没有。
- 修复一次通过，没有降级，质量四项都通过。
- [pipeline-problems-raw.md](pipeline-problems-raw.md) 用 `runner.triggering` 逐句复现，列了 11 条“候选原句”，大多和问题无关；实际发出的修复请求只引了这一句，是 `reading_quotes` 给出的。两份文件的差别来自工具，不是修复请求引错了。

### 3.2 唯一的质量失败：海外 #2，`time_consistent=false`

- 评委逐项把 UTC 换算成北京时间，承认正文的日期全部正确；失败理由只有一条：“用户提问时间为当前上下文未明确给出……模型自行将‘下个月’锚定为 2026 年 12 月”。
- **范围不是模型选的。** 冻结代码的 `relative_span("下个月", 2026-11-08)` 返回 2026-12-01 至 2026-12-31，与 temporal-evidence 记录的计算区间相同；本批在 2026-11-08 运行。
- **评分输入里没有运行日。** `scripts/live_week23.py` 给评委的载荷只有 question、clarification、answer、structured、facts 五项，没有单独的运行日期字段；评委只能看到已经算好的 12 月区间。
- 同题 #1、#3 用同一区间，评委判了通过，#3 的理由还写明“transit 范围为 2026-12-01 至 12-31……日期换算与计算事实一致”。同一模型对同一前提判法前后不一，和 r4 复核 §4 记的“同一模型评分不稳定”是同一类问题。
- 分段也对：这条回答“月初”一段的相位日期是 2–8 日，“月中”一段是 11–19 日，“月底”一段是 26 日，都在对应时段内。
- 结论：这条失败不归给代码或提示词。原分保留，质量按 11/12 报告。评分载荷不含运行日，记入已知局限（§4）。

### 3.3 有没有漏拦

- **分段与日期。** 我用冻结代码的 `PARTS`（上旬/月初 1–10、中旬/月中 11–20、下旬/月底/月末 21–31）核对了流水线 12 条最终回答：按月分段的标题共 18 个，正文写出的相位精确日期全部落在本段内，连 `TOLERANCE` 的两天放宽都没有用到。
- **按周分段。** 下周题的“前半周 / 中间几天 / 后半周 / 周末”不在代码的分段检查范围内。我人工核对了 3 条：前半周 9–11 日，中段 11–13 日，后半周和周末 12–15 日（11 月 12 日是周四），没有明显越界。这项检查只靠人工，列入已知局限。
- **重复标签。** 12 条最终回答里没有“本命本命”“行运行运”。
- **摘要的相对时间。** 海外题 3 条摘要都写“下个月”，下周题都写“下周”，指定月份题都写“2027 年 3 月”，与计算区间一致。
- 评委判 `no_fabricated_facts=false` 的流水线回答为 0 条。0 次失败不能证明没有漏检，这是同模型评分的限制。

### 3.4 编造分类：single 下周 #2，叙述类

负责人的分类（[fabrication-attribution.md](fabrication-attribution.md)）把它归为叙述类。我先排除了它是事实类的可能，用冻结的计算器重算了这题的星盘：

- **本命。** 太阳双子第 7 宫、水星巨蟹第 7 宫、月亮巨蟹第 8 宫、火星巨蟹第 8 宫、金星金牛第 6 宫；月亮合火星、月亮冲海王星、水星冲海王星都在相位表里。正文写的“水星巨蟹加海王星对冲”“本命火星在巨蟹与月亮合相”都对。
- **行运（上海时间）。** 水星六分海王星 11 月 9 日、月亮冲金星 9 日、水星三分火星 10 日、木星三分天王星 11 日、月亮冲太阳 11 日、月亮合土星 12 日、月亮合天王星 12 日、月亮冲水星 13 日、土星六分太阳 15 日。正文写的日期都对。

所以评委指的是“你容易在沟通里……退让”“对方往往觉得你好沟通”“你在实际利益上的判断力其实很好”这类把星盘象征写成用户已有特征的话，没有可核验事实写错。同意归为叙述类。

| 组别 | 已提交 | 编造失败 | 事实类 | 叙述类 | 计数表 |
| --- | ---: | ---: | ---: | ---: | --- |
| AstroFinal-single | 8 | 1 | 0 | 1（12.5%） | 完整 |
| AstroFinal-pipeline | 12 | 0 | 0 | 0（0%） | 完整 |

两组都“完整”，按约定可以计数。分类是 Codex 离线做的，不是独立人工裁决；评委的布尔分全部保留。

### 3.5 single 的未完成（只作描述）

single 有 4 行未提交：工作方式 #1、下周 #3 因重复免责声明到了重试上限；指定月份 #1 因行运日期与引用事件不符到了重试上限；海外 #3 停在地点消歧的追问上。这些不进 P1 判定，也不影响上面的比较。

## 4. 已知局限（不影响判定，后续处理）

r4 复核 §4 的五项仍然存在，这批没有新增后果。本批新增或再次确认的：

| 局限 | 本批后果 | 处理 |
| --- | --- | --- |
| 评分载荷不含运行日 | 海外 #2 因“无法确认下个月是哪个月”判 `time_consistent=false`；同题另两次通过 | 评委配置不改（已拍板）。主集复核时，相对时间题的 `time_consistent` 失败要逐条看理由，原分保留 |
| 按周分段没有代码检查 | 本批 3 条人工核对没有越界 | 解冻后可以让分段检查也覆盖“前半周 / 后半周 / 周末”；不阻止冻结 |
| `pipeline_problems` 的候选原句和实际引句不一致 | 海外 #3 列了 11 条候选，实际只引 1 条 | 报告工具的局限，不影响修复。以后的归因以 repair 事件里的 `quotes` 为准 |
| 同一模型评分 | 判法不稳定（§3.2）；0 次编造失败不证明没有漏检 | 人工校准之前，不把评委当作可靠的独立评审 |

r4 §4 的“消息里用文字给出生资料仍交给 agent 循环”在八字 PR 里处理，星盘和八字共用。

## 5. 与 r4 调参集对照（只作描述）

| 指标 | r4 调参集（流水线） | 最终验收集（流水线） |
| --- | --- | --- |
| 提交 | 18/18 | 12/12 |
| 已提交质量 | 17/18 | 11/12 |
| 同批 single 已提交质量 | 9/11 | 7/8 |
| 修复 / 降级 | 3 / 0 | 1 / 0 |
| 事实类 / 叙述类编造 | 0 / 0 | 0 / 0 |
| 最多调用 | 2 | 2 |
| P95 | 35.3 秒 | 23.2 秒 |

两批代码和配置相同，题目不同。同题三次不是独立样本，不外推为总体比例。

## 6. 下一步

- 计划里记“星盘完成”。
- 按负责人约定开八字 PR：`requirements.py` 的八字部分、消息里用文字给出生资料由代码处理（星盘和八字共用）、八字事实表和闭集、4 条八字 xfail 转为通过、接受路径生成器、`bazi_pilot.yaml` / `bazi_final.yaml` 和对应编排。
