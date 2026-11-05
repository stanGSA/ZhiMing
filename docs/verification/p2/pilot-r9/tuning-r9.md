# r9：修复 r8 定位的三类误拒，保存解析失败的评委原文

| 项目 | 内容 |
| --- | --- |
| 依据 | 负责人的 [r8 评估](../pilot-r8/assessment.md)、[校验复核](../pilot-r8/validation-findings.md)、[质量归因](../pilot-r8/quality-attribution.md)，以及我的 [r8 复核](../pilot-r8/review.md) |
| 被测代码 | r8 为 `e01a008`（源码指纹 `74d3ff68…`）；本 PR 基于 `26a3d38`（只多了文档） |
| 方法 | 离线，用 r8 原句构造测试；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-05 |

## 1. 修了什么

| # | 体系 | r8 原句 | 修法 | 位置 |
| --- | --- | --- | --- | --- |
| 1 | 解梦 | 梦里牙齿是一颗一颗掉下来的 | “掉牙”构式的副词表加上“是” | `plugins/dream/match.py::NORMALISATIONS` |
| 2 | 共用确定性用语 | 不是事情必然顺利的保证 | 新增 `negated_head`：“不是/并非/不等于……”加一个短主语，“必然……”之后以“的保证/结论/定论/预言/承诺/依据/证明/意思”收尾，视为否认 | `common/output_policy.py` |
| 3 | 共用确定性用语 | 别把配合当成必然有利 | `NEGATED_NOUN` 新增一个分支：“别/不要/不必……把 + 短宾语 + 当成”，宾语与稳赚规则共用 | `common/output_policy.py` |
| 4 | 共用稳赚规则 | 别在情绪顺畅时把配合或行情当成稳赚；别因为情绪顺畅就把……当作稳赚；别把“有机会”直接当成“稳赚” | 否定词与“把”之间允许一个受控状语，宾语与谓语之间允许一个副词 | `common/output_policy.py` |
| 5 | 评测记录 | daily_unknown_birth_time#3 未评分，回复原文没有留下 | 解析失败时保存每次回复的前 4,000 字和错误信息（`unparsed_replies`）；判分与重试不变 | `scripts/live_week23.py::judge_answer` |

2–4 都在负责人批准的语义之内：

- 明确否认确定性结论的不算确定性断言；
- 明确否定“稳赚”的放行。

“必涨、必死、必然确诊”的硬规则不变。

## 2. 受控范围

**状语（`DISMISS_ADVERBIAL`），只认这几种：**

- 在 / 趁 + 1–8 个字 + 时 / 的时候；
- 因为 + 1–8 个字；
- 一下子、轻易、急着、随便、再；
- 后面可再带一个“就”。

**动词前副词（`DISMISS_VERB_ADVERB`）：** 直接、轻易、简单（地）、随便、马上、就。

**宾语（`GAIN_OBJECT`），r8 起增加限制：**

- 不能含否定、转折、确定性用语、“是 / 必”或另一个“稳赚”；
- 不能含框架动词或情态词：当、看、视、想、认、应、该、要、误、理解、解读、作为。这样宾语吞不进第二个“当作 / 理解成”。负责人原有的守卫“不要把它当作偶然应理解成必然的结果”“别把它想复杂了应看成必然的结果”照旧拒。

**“……的保证”（`NEGATED_HEAD_*`）：**

- 主语最多 6 个字，“必然”之后最多 8 个字再接收尾名词；
- 中间不能有标点、否定或转折；
- 句末是问句（……的保证吗？）时不算否认；
- 否定本身被否定时（不是不……）也不算。

**双重否定：**新分支对“不得不把 / 不是不把 / 不能不把”等用 lookbehind 排除，稳赚规则沿用 `GAIN_DENIAL_NEGATED`。

## 3. 测试

| 测试 | `e01a008` | 本 PR |
| --- | --- | --- |
| 解梦：r8 掉牙原句走完整提交，0 次修复、不降级 | 失败 | 通过 |
| 解梦：梦里牙齿象征财富 / 复述后再解读牙齿 / 牙齿是白的……仍拒 | 通过 | 通过 |
| 确定性：r8 的两种原句，加上带状语、“不等于……的结论”等 4 句放行 | 失败 | 通过 |
| 确定性：问句、逗号或转折后重新肯定、“的原因”、双重否定、宾语带标点等 10 句仍拒 | 通过 | 通过 |
| 确定性：负责人原有的“当作偶然应理解成必然”等守卫仍拒 | 通过 | 通过 |
| 稳赚：r8 的 3 种原句放行 | 失败 | 通过 |
| 稳赚：双重否定加状语、续文、状语带否定或确定性、逗号断开等 6 句仍拒 | 通过 | 通过 |
| 每日：r8 的 5 种原句走完整提交，0 次修复 | 失败 | 通过 |
| 每日：“别因为不想亏就把配合当成稳赚”“这不是事情必然顺利的保证吗？”修复一次 | 通过 | 通过 |
| 评测：两次解析失败时保存回复原文（截断）和错误；第二次成功时照旧评分 | 失败 | 通过 |

负责人在 `e01a008` 和更早提交中加的守卫全部保留，照旧通过。CI 范围的 `ruff check`、`ruff format --check` 通过。全量测试结果见 PR。

## 4. 请负责人决定

收敛风险见 [r8 复核 §5](../pilot-r8/review.md)：每轮都会出现新的自然说法，按现行 B 第三条可能长期无法冻结。是否调整口径由负责人决定；本 PR 按现行 B 修复。

## 5. 重跑 r9

合并后在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，开跑前先检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r9 --snapshot . --baseline . --publish docs/verification/p2/pilot-r9
```

`docs/verification/p2/pilot-r9/pricing.yaml` 已放好，内容与 r8 相同。后续命令同 [r8 的 reproduction.md](../pilot-r8/reproduction.md)，把 `p2-r8` 换成 `p2-r9`。

如果还有未评分的行，summary 里会有 `unparsed_replies`，可以直接看评委回复的原文。

判定沿用 B 标准（或负责人调整后的口径）。满足就冻结代码。冻结范围是源码指纹覆盖的路径：agents/、app.py、common/、config.yaml、evals/、harness/、knowledge/、memory/、pipeline/、plugins/、scripts/、uv.lock。冻结后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```
