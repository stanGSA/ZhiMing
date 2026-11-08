# P3 八字调参集 r1 复核：不满足 B，r2 修复后重跑

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot 结果（`bfc8a84`）：[execution.md](execution.md)、[assessment.md](assessment.md)、[comparison.md](comparison.md)、[integrity.json](integrity.json)、[acceptance.json](acceptance.json)、两组 summary 与 source-hashes、[repair-attribution.md](repair-attribution.md)、[repair-quotes.json](repair-quotes.json)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)、[known-escape-probe.json](known-escape-probe.json)、[false-rejection-probe.json](false-rejection-probe.json)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[temporal-evidence.json](temporal-evidence.json) |
| 被测代码 | `7ba34e6f4dfc5d1e211f8215b688f60b01975b0c`（PR #60 合并后加负责人修复），源码指纹 `7a6f3d2d08f69d8ffd68f571c7605fa718a8b548de4be47b22076ea88036548a` |
| 实验配置 | `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`：执行记录写明是在 `248e6db0…` 的 `pipeline.systems` 末尾加 `bazi`。原始配置字节不在仓库里，这一点我无法离线核对，按执行记录采信 |
| 方法 | 离线：重算指纹，逐文件对照 `7ba34e6`；核对模型、raw_sha256、evidence-manifest 和评分；逐条读修复、质量失败和编造分类的原文，并在 `7ba34e6` 的独立 git worktree 里用原文做最小对照。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-09 |

## 1. 结论

**P1 四条满足；按 B 不冻结。** 有一处已知放过（文字出生资料 #1 的分段标题“上半年尾巴”），r2 已修，配了离线守卫。

| B 条件（2026-11-06 口径） | r1 | 依据 |
| --- | --- | --- |
| 已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；最多 2 次 |
| 事实类编造 0，两组计数表“完整” | **按计数表不满足**（流水线事实类 1） | 两组都“完整”。这 1 条是评委把“按固定UTC+8”读成咨询时区（§3.3），计算本身与负责人 2026-11-08 的口径一致。按约定只计计数表里的数字，所以记为 1；是否改判请负责人决定 |
| 没有造成降级、失答或质量失败的可定位误拒 | 满足 | 唯一误拒（“不是‘必然发财’”）一次修好，没有降级，该条质量通过（§3.1） |
| 没有已知放过 | **不满足** | 分段标题“先甜后磨的上半年尾巴”，所看范围是 7 至 12 月（§3.2） |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 14/18（77.8%）≥ 7/13（53.8%） |

降级 0/18。叙述类 2/18（11.1%），不高于 single 的 5/13（38.5%），但没到 ≤ 10% 的争取值。

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 相同，183 项；按 `scripts/live_week23.py` 的算法重算得 `7a6f3d2d…` |
| 覆盖范围 | 按同一取样规则列出 `7ba34e6` 的文件，与 183 项完全相同，不缺不多 |
| 被测提交 | 除 config.yaml 外 182 个文件与 `git show 7ba34e6:<path>` 逐文件一致；与当前 `claude_modify_model` 也一致（`bfc8a84` 只多了 docs/） |
| 配置 SHA256 | source-hashes 中 config.yaml 为 `3dfa2e81…`，与执行记录一致 |
| 请求和返回模型 | 两组 `requested_model`、`judge_model`，36 行的 `returned_models`、评分的请求与返回模型都是 `deepseek-v4.1-flash`。同一模型评分 |
| 原始报告 | 两组 `raw_sha256` 与 raw-manifest 一致 |
| 发布文件 | evidence-manifest 列出的 29 个文件按字节重算全部一致 |
| 评分完整性 | 36/36 四维都是布尔值，`unscored-reviews.json` 为空 |
| 结局 | 流水线 18 行都是 `submit_reading`。single：提交 13、`ask_user` 4（海外 3 次全部停在追问，大运 1 次）、`retry_limit` 1 |
| 追问 | 流水线海外题 3 次都只问 1 次真太阳时，收尾都注明了出生地时区；文字出生资料题 3 次都没有追问，画像存下女、`1995-04-28 07:15`、深圳 |

## 3. 归因（在 `7ba34e6` 的独立 worktree 里用原文对照）

### 3.1 三次修复

| 样本 | 首稿问题 | 冻结代码对照 | 归因 |
| --- | --- | --- | --- |
| 大运 #2 | “不能使用‘必然’这类确定性说法” | `certainty_claim` 对原句返回“必然”；去掉引号后的同一句返回 None | **误拒**。“不是必然发财”本来就放行，只因否定词和“必然”之间多了一个前引号就没认出否定。属于现有否定语义的识别遗漏，不是规则本身要禁止。一次修好，没有降级，不阻止冻结 |
| 大运 #3 | 年柱年柱、月柱月柱、时柱时柱 | `REPEATED_LABEL` 在渲染稿命中这三处 | 真错误，一次修好 |
| 投资 #3 | 年柱年柱、月柱月柱 | 同上，命中两处 | 真错误，一次修好 |

后两次是写作者在编号前又写了“年柱”“月柱”。与星盘的“本命本命”同一类，引句准确，修复有效。

### 3.2 已知放过：文字出生资料 #1 的分段标题

- 范围是 2026-07-01 至 12-31，第一层的标题是“先甜后磨的上半年尾巴”，正文写的却是七月。
- 冻结代码的 `Bazi.reading_problems` 只看摘要第一句，对这条回答返回空列表。我用原文复现，结果相同（与负责人的 [known-escape-probe.json](known-escape-probe.json) 一致）。
- **这是可定位的漏拦，阻止冻结。** 该条另有 `supported_conclusion=false`，评委理由是关系事件推断过强，与标题无关。
- 我还用 r2 的新检查核对了流水线全部 18 条回答的 34 个分段标题：只有这一条被拒。

另外两处我看过但不算错误：

- **文字出生资料 #2 第三层**：标题写“九月到十月……十月到十一月”，正文最后还写了“十二月上旬之后流月庚子”。正文给每个流月写的月份都对，评委四项全过。标题只是概括，所以不算错误；r2 的检查也有意放行这种写法（§4）。
- **海外 #3**：写了“月令又落在水旺的节气里”。本命月柱是乙巳（巳属火），这里的“月令”如果指本命就写错了，如果指十二月的流月（亥、子属水）就是对的。存在歧义，记入已知局限，不计为放过。

### 3.3 流水线四条质量失败

| 样本 | 失败维度 | 归因 |
| --- | --- | --- |
| 文字出生资料 #1 | time、supported | 标题错写确实存在（§3.2）。评委另外说“没有当前年份锚点”：评分载荷里没有运行日，与星盘最终验收的疑点相同 |
| 海外 #2 | time | 评委把澄清里的“按固定UTC+8”读成咨询时区。这句话回答的是真太阳时的追问，按 2026-11-08 的口径，没有说明现居地时就按出生地洛杉矶时区算。计算和收尾的注明都对 |
| 海外 #3 | time、supported、fabricated | 时区理由同上。另有两条：一是把喜用倾向建立在五行计数上，二是写了“同事主动递话”“投入没被看见”这类具体场景。这两条与时区无关，属于撰写问题 |
| 文字出生资料 #3 | time、fabricated | 评委的 time 理由写“故不直接判 false”，布尔值却是 false，前后矛盾。编造指控是“遇到想认真对待的人”“年底把关系定下来”这类具体感情场景，属叙述类 |

- 海外题的时区误读部分出在我写的调参集澄清“不用真太阳时，按固定UTC+8”：普通读者也可能把后半句当成时区。
- r2 的收尾因此先写“出生时刻按固定UTC+8排盘”，再写日期按哪个时区（§4），让读者和评委都看得出这是两回事。
- 调参集这句澄清要不要改成只说“不用真太阳时”，请负责人决定（§5）。

### 3.4 编造分类

我对照原文看了 7 条分类，同意负责人的拆分：

- **流水线海外 #3 的事实类那一项：** 指控的是时区。按口径计算正确，所以我认为它不是可核验事实写错。计数表照约定保留为 1。
- **single 大运 #2 的事实类：** 评委写的是“逆推”，实际 `forward=true`，指控本身有疑问。
- **single 性格 #3 的事实类：** 指控的是引用错配，不是当前大运干支算错。

两组计数表都“完整”，可以计数。

## 4. r2 的改动（本 PR）

| 改动 | 内容 | 守卫 |
| --- | --- | --- |
| 分段标题的时间（`pipeline/bazi.py`） | 标题里的月份、上下半年、年初年中年底、季节、单月的上中下旬、下个月等相对说法，必须落在所看的范围里；这一层引用了流期的，至少有一个流期落在标题说的时间里。读法放宽：时段按概括理解，比较时允许两天误差，流期超出标题一部分不拒。修复请求引出标题本身（`reading_quotes`） | 用 r1 的 34 个真实标题做回归：只拒“上半年尾巴”。另有 14 条接受、10 条仍须拒 |
| 引号里的否定（`common/output_policy.py`） | `certainty_claim` 读否定时，把否定词和确定性词之间的前引号当标点，“不是‘必然发财’”与“不是必然发财”判法相同。共用规则的语义不变 | 10 条对照，带引号和不带引号的结果逐条相同，其中 7 条仍须拒：肯定、同句另一处断言、外层否定、双重否定、转折后重新肯定等 |
| 海外出生的收尾（`pipeline/bazi.py`） | 由代码写“出生时刻按固定UTC+8排盘；日期按出生地……的时区计算……”，把出生钟表口径和日期时区分开 | 端到端测试 |

- 新增的 4 个行为测试在 `7ba34e6` 上失败、在 r2 上通过；守卫在两版上都通过。均在独立 worktree 里核对。
- 两份题集都没改。

## 5. 请负责人决定

1. 海外 #3 那条事实类指控（评委误读时区）是否改判。不改判时，r2 的 B 条件里事实类按计数表计。
2. 调参集 `bazi_pilot_overseas_solar` 的澄清，是否从“不用真太阳时，按固定UTC+8。”改成“不用真太阳时。”。这句澄清是我写的，后半句会被读成咨询时区。改了以后 r1、r2 之间这一题不再是同一道题，所以没有擅自改。

## 6. r2 重跑（负责人本机）

在 r2 合并后的 `claude_modify_model` 上运行，配置仍用八字约定配置 `3dfa2e81…`。`docs/verification/p3/bazi-pilot-r2/pricing.yaml` 已放好，与 r1 逐字节相同：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r2 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r2
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r2/Bazi-single reports/p3-bazi-r2/Bazi-pipeline --answers --output reports/p3-bazi-r2/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r2/Bazi-single reports/p3-bazi-r2/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r2/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r2/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r2/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r2/pipeline-problems-raw.md
```

## 7. 已知局限（不阻止冻结，后续处理）

| 局限 | 现象 | 处理 |
| --- | --- | --- |
| 评分载荷不含运行日，也没有说明出生钟表口径和咨询时区的区别 | 3 条 time 失败与此有关 | 评委配置不改（已拍板）；复核时逐条看理由 |
| 正文里的月份与流期只按标题核对 | 例如“八月上旬的流月乙未”：乙未从 7 月 7 日起，与 8 月上旬有重叠，所以放行 | 正文逐句核对误拒风险高，暂不做 |
| “月令”的五行不检查 | 海外 #3 的“月令又落在水旺的节气里”有歧义 | 先观察 r2 是否再现 |
| 喜用倾向和具体场景的写法 | 海外 #3、文字出生资料 #3 的 supported、fabricated 失败 | 属撰写问题，提示词已要求写明依据和用条件句；r2 不改提示词，先看再现率 |
| single 海外题 3 次都停在追问 | 预设澄清之后 single 仍继续追问 | single 不在调参范围内，如实记录 |
