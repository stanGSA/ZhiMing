# P2 r13 复核：满足 B（2026-11-06 口径），代码冻结于 `83ce4f4`

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 [execution.md](execution.md)、[integrity.json](integrity.json)、[repair-attribution.md](repair-attribution.md)、[fabrication-attribution.md](fabrication-attribution.md)、[fabrication-counts.md](fabrication-counts.md)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[repair-quotes.json](repair-quotes.json) 及六组 summary（`1c3341c`） |
| 被测代码 | PR #53 合并提交 `83ce4f41319b456c89fa99b3761362177d02f4d1`，源码指纹 `fde7663cdcb41e8a5f55c1f92739a3fd43984ef80ee0dc10ef8f1c984b946b6c` |
| 方法 | 离线：重算源码指纹，核对 raw_sha256、模型、评分，逐条对照修复原句与编造分类；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-07 |
| 负责人决定 | 2026-11-07：“总格李娜的人格17”这类标签错配记为已知局限，代码不改，按 r13 冻结 |

## 1. 结论

**B 满足，代码冻结。**

- 冻结的是被测提交 `83ce4f4`，冻结范围为源码指纹覆盖的路径：agents/、app.py、common/、config.yaml、evals/、harness/、knowledge/、memory/、pipeline/、plugins/、scripts/、uv.lock。
- 之后到 p2-final 跑完为止，这些路径都不再改动；docs/ 不在冻结范围内。
- 下一步由负责人运行 p2-final（§5）。

| B 条件（2026-11-06 口径） | r13 | 依据 |
| --- | --- | --- |
| 三个流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 三个流水线都是 18/18；最多调用依次为 3、3、1；没有降级 |
| 流水线事实类编造 0，六组计数表“完整” | 满足 | 三个流水线 54 条的 `no_fabricated_facts` 全部为 true；六组计数表都是“完整”。single 组 10 条编造失败都已分类，其中事实类 2、叙述类 9，有 1 条两类都算 |
| 流水线中没有造成后果的可定位误拒 | 满足 | 15 次修复都只修一次就成功提交，没有第二次修复、降级或质量失败（§3） |
| 被测代码没有已知的放过 | 满足 | 审查发现的 F1–F4 和 r12 的两处规则问题都已在 `83ce4f4` 中修正；剩下的标签类重复按负责人决定记为已知局限（§4） |
| 已提交质量 ≥ 同批 single（只报告） | 三个体系都满足 | 解梦 18/18 对 12/13；姓名 18/18 对 9/11；每日 17/18 对 8/18 |

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 六份相同；重算得 `fde7663c…`，与 execution.md、integrity.json 一致 |
| 被测提交 | 除 config.yaml 外的 173 个文件与 `83ce4f4` 逐一一致 |
| 配置 SHA256 | `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3` |
| 请求和返回模型 | 108 行运行与评委的请求、返回都是 `deepseek-v4.1-flash` |
| 评分 | 108/108 四个维度都有评分；Daily-pipeline 有 1 条用了尾逗号修补 |
| 原始报告 | 六组 summary 的 `raw_sha256` 与 raw-manifest 一致 |

## 3. 修复与质量失败的归因

**15 次修复**（逐条见 [repair-attribution.md](repair-attribution.md)，我已对照 pipeline-problems-raw 与 repair-quotes 复核）：

- **Dream 3 次：**
  - 2 次按设计拒：从“不敢下去 / 不肯下去”这类状态推心理；
  - 1 次是“梦里逃跑之后”被判成未命中的“逃跑”。“被追”的释义本身就带逃跑，这是表达受限，但修复一次就通过了，没有造成后果。
- **Name 12 次：**全部是 r13 新加的“姓名或格名写了两遍”检查，拦下了“人格人格24”“外格外格2”“张伟的人格张伟的人格22”这类重复写法。这种写法在 r10–r12 已提交的回答里就存在，只是此前拦不住。其中一次还附带“地格地格1111”的数值拼接错误。都是真实问题，不是误拒。
- **全部修复都引出了触发句**（共 43 条），没有一条原样留在成稿里。

**流水线唯一的质量失败：**Daily `today_family#2`，失败维度是 time_consistent 和 supported_conclusion，没有修复也没有降级。当天乙酉分成两段，00:00–17:52 和 17:52–23:00，是节气换月造成的；评委把 17:52 当成了乙酉换丙戌的边界。正文的时段标注都来自代码渲染，原分保留，这一条是评委看错了。

## 4. 已知局限（不阻止冻结，留到后续阶段处理）

| 局限 | 现象 | 来源 |
| --- | --- | --- |
| 格名标签错配 | 总格李娜的人格17、总格张伟的人格22：格名和编号对应的格不一致，但数值本身没错 | r11 回答；负责人 2026-11-07 决定记为已知局限 |
| 三才标签重复 | 三才配置三才配置、三才三才配置、张伟的张伟的三才配置；12 条修复后的成稿中有 7 条仍带这种写法 | r13 repair-attribution.md。和上一条同属标签重复，`repeated_label` 只覆盖五格格名，没有覆盖三才与“姓名 + 的”的重复 |
| 修复提示里的数字截断 | 问题描述写成“人格人格2”，实际是 24。规则只取了数字的第一位，只影响提示文字，不影响判定 | r13 repair-attribution.md |
| 解梦表达受限 | “梦里逃跑之后”“到处找出口却找不到”这类自然改述会被闭集拒绝，靠修复引句一次改写 | r11–r13 |

这些都不改动冻结的代码。处理时机建议放在 P2 最终验收之后的阶段（P5 或单独的 PR），处理后必须重新验证。

## 5. 最终验收（由负责人在本机执行）

在 `83ce4f4`（或只多了 docs/ 提交的后续 `claude_modify_model`）上运行。`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，开跑前先检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```

`docs/verification/p2/final/pricing.yaml` 已存在。跑完后：

- 用 `scripts.quality_reasons` 的 `--reviewed` 流程生成编造计数表；
- 用 `scripts.pipeline_problems` 列出问题原文；
- 发布 repair-quotes。

最终验收按体系分别判定 P1 四条：

- 已提交 100%；
- 步数和预算失败为 0；
- 每轮调用 ≤ 3；
- 已提交回答质量 ≥ 同批 single。

任何一个体系不通过就回到调参，验收集不改。源码指纹必须仍是 `fde7663c…`。
