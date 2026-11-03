# 解梦 r3 调参：逐条归因与改动

| 项目 | 内容 |
| --- | --- |
| 依据 | [r2 复核](assessment.md)（负责人）、[各稿问题原文](dream-pipeline-problems-raw.md)、[被追进考场第 3 次](dream-chased-to-exam-r3-review.md) |
| 被测代码 | r2 为 `8f87d75`；本 PR 基于 `8e9c3fa`（只多了文档） |
| 方法 | 离线，用 r2 的问题原文和原题在当前代码上复现；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-03 |

## 1. 每条问题的归因

解梦有 7 条回答修复过，其中 4 条降级。下表逐条对照 [问题原文](dream-pipeline-problems-raw.md)。

| 回答 | 问题 | 归因 | 本 PR |
| --- | --- | --- | --- |
| 生病住院 #2 | 两稿都是“不能劝阻就医（‘不要去做检查’）”，降级为 `safety` | **误拒，已复现。** 撰写者复述用户的问题“要不要去做检查”，共用的就医规则把其中的“不要去做检查”当成劝阻。离线验证：“关于要不要去做检查：……如有不适请及时就医”在当前代码上被拒 | 修 `common/output_policy.care_advice`：正反问（要不要、需不需要、用不用）中的“不”不算劝阻。“不要去做检查”“你不需要去做检查”照样拒 |
| 家里进水和蛇 #2 | 意象“不敢下去”未收录，且“不敢下去”不在事实表里 | **抽取把反应当成了意象**（r1 改过的抽取提示词没有完全约束住）。“不敢下去”一旦进了“未收录”，复述都会被拒 | 代码和提示词同口径：抽出来的词如果词典里没有，并且带否定、程度或持续（不、没、未、一直、总是、到处），就不进“未收录”。复述放行，拿来解读仍按事实表外的内容拒 |
| 家里进水和蛇 #1、#3 | “不敢下去”“游来游去”不在事实表里 | 撰写者拿用户描述的反应或动作来解读。**按设计拒**：事实表里没有这些内容 | 不改检查；撰写提示词沿用 r1 的“先复述，再用编号或‘这个梦’作主语解读” |
| 生病住院 #1 | “住院”未收录；“伴随住院”不在事实表里 | 解读了未收录的意象。**按设计拒** | 不改 |
| 商场迷路 #1 | “找不到出口”未收录 | 同第二行：“找不到出口”带否定，是状态而不是意象 | 同第二行，不再进“未收录” |
| 家里进水和蛇 #3 | 两稿都是“‘火’不是本次命中的意象” | **原句无法恢复。** 词典里“火”的别名有火、着火、大火、起火、家里着火等；问题文字只记了词条名，草稿没有入库，也没有进 trace。按问题文字判断不了是误拒还是确实提到了火 | 不按猜测改检查。trace 增记被拒稿的全文，`scripts.pipeline_problems` 在本机为每条问题列出所在原句 |
| 商场迷路 #2 | 两稿都是“‘鱼’不是本次命中的意象”，降级为 `keywords` | 同上，原句无法恢复 | 同上 |

**被追进考场 #3（唯一的质量失败）：**

- 这条一次写成，没有修复，也没有降级。
- 结尾原句：“梦里的追赶声，其实是你心里那份压力在提醒你：它需要被看见……”
- 评委判为叙述编造：把象征写成了用户确定的内心事实。
- 计划把叙述编造归为只能靠撰写提示词解决的问题，所以本 PR 在解梦撰写提示词里加了一条：说到用户心理时写“可能、也许、如果你最近……”；结尾和收尾不写“其实是你心里……”“这说明你就是……”“不是……而是你……”这类替用户下的判断。

**撰写提示词另加一条（针对生病住院）：** 用户问要不要检查时，正面说怎么判断：梦本身不能说明身体状况，是否检查看身体的实际感受，有不适请及时就医；不写“不要去、不用去、不需要去检查”。代码修好后，即使撰写者复述了用户的问题，也不会再被拒。

## 2. 改动范围

| 文件 | 改动 | 影响 |
| --- | --- | --- |
| `common/output_policy.py` | `care_advice` 跳过正反问里的“不”（新增 `a_not_a`） | **共用规则**，single 和流水线的所有体系都受影响。只放宽正反问，劝阻就医的写法照样拒 |
| `pipeline/dream.py` | 抽取结果中，词典里没有、又带否定、程度或持续的词，不进“未收录”（`STATE`） | 只影响解梦流水线 |
| `pipeline/compose.py` | 解梦撰写提示词加两条：心理写成可能的线索；正面回答要不要检查 | 只影响解梦流水线 |
| `pipeline/runner.py` | trace 的 `problems` 阶段增记该稿全文（`text`）。全文不放进 `run.problems`，因为 runner 用正则读问题文字来判断要不要走安全模板 | 全体系，只多记 trace |
| `scripts/pipeline_problems.py` | 不加 `--tally` 时，在每条问题下列出被引用的词所在的原句；`--tally` 仍只输出固定类别 | 只在本机输出 |

降级的规则没有改。但“要不要去做检查”不再触发“劝阻就医”，所以 r2 里生病住院 #2 那种 `safety` 降级不会再出现。负责人当初选定的选项 A（两稿都触发时降级为安全模板）不变。

## 3. 测试

新增 6 条，在 `8e9c3fa` 上都失败，在本 PR 上都通过；另有 4 条守卫，两版都通过。

- `tests/validation/test_negation_and_dates.py`：
  - 3 条正反问放行（失败 → 通过）；
  - 4 条劝阻照样拒（两版都通过）：不要去做检查、你不需要去做检查、要不要紧都不要去医院、用不用去医院，不用去医院。
- `tests/pipeline/test_runner_dream.py`：
  - 高风险题撰写者复述“要不要去做检查”时，0 次修复、不降级、直接提交（失败 → 通过）；
  - “不敢下去”不进“未收录”，复述放行，拿来解读照样拒；“家里进水了”仍然算未收录（失败 → 通过）；
  - trace 记录被拒稿的全文（失败 → 通过）。
- `tests/tooling/test_pipeline_problems.py`：
  - 渲染列出原句，`--tally` 不带原句；
  - 没有记录草稿时，不列原句。
  - 在 `8e9c3fa` 上整个模块因缺 `sources` 而导入失败。

## 4. 停止调参的标准（负责人已确认 B，2026-11-03）

负责人在会话中选定 B，已写进[计划](../../../根因整改实施计划.md) P2 的实施记录。事先约定，r3 结果出来之前定下，之后不改：

- r3 是最后一轮调参。
- 冻结条件：
  - 三个流水线都是已提交 18/18，步数和预算失败 0，每轮调用 ≤ 3；
  - 可核验事实类编造 0，六组计数表都是“完整”；
  - 每条质量失败、每次修复和降级都已对照原文归因，没有能定位到代码或提示词的误拒或缺陷。剩下的失败只能是同题偶发的写作失误，或者评委理由自相矛盾，并逐条写明。
- 第四条照常计算并如实报告。在调参集上不满足时写明差几条、失败出在哪题，但不因此阻止冻结；通过与否以最终验收集为准。
- 如果 r3 仍有能定位的缺陷：修完再跑一轮，但不再为没有归因的单条失败继续调参。

**为什么选 B：** 计划写的是通过条件“以最终验收集为准”。两轮 single 已提交回答的质量都是 100%，第四条在调参集上实际等于要求流水线零失败。r1、r2 的失败出在不同的题、不同的维度，继续只在这 6 道题上调参，等于在拟合这 6 道题。

## 5. 重跑命令

合并后在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r3 --snapshot . --baseline . --publish docs/verification/p2/pilot-r3
```

`docs/verification/p2/pilot-r3/pricing.yaml` 已放好，与前两轮逐字节相同。

跑完后：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r3/Dream-pipeline reports/p2-r3/Name-pipeline reports/p2-r3/Daily-pipeline --output reports/p2-r3/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p2-r3/Dream-pipeline reports/p2-r3/Name-pipeline reports/p2-r3/Daily-pipeline --tally --output docs/verification/p2/pilot-r3/pipeline-problems.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r3/Dream-single reports/p2-r3/Dream-pipeline reports/p2-r3/Name-single reports/p2-r3/Name-pipeline reports/p2-r3/Daily-single reports/p2-r3/Daily-pipeline --answers --output reports/p2-r3/quality-reasons.md
```

逐条判定类别，写进 `reports/p2-r3/fabrication-reviewed.yaml`，然后：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p2-r3/Dream-single reports/p2-r3/Dream-pipeline reports/p2-r3/Name-single reports/p2-r3/Name-pipeline reports/p2-r3/Daily-single reports/p2-r3/Daily-pipeline --counts-only --reviewed reports/p2-r3/fabrication-reviewed.yaml --output docs/verification/p2/pilot-r3/fabrication-counts.md
```

`reports/p2-r3/pipeline-problems.md` 里，现在每条问题下面会列出原句。如果“火”“鱼”这类问题再出现，请把那几行连同原句发给我。
