# P2 r9 复核：按负责人确定的第 3 种口径，B 未通过，不冻结

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 [assessment.md](assessment.md)、[validation-findings.md](validation-findings.md)、[quality-attribution.md](quality-attribution.md) 及同目录证据（`3e01d64`） |
| 方法 | 离线：重算源码指纹与发布文件哈希，逐行读六组 summary，按原句在本地回放校验；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-06 |
| 本文件 | 新增，不改负责人已发布的文件；[evidence-manifest.json](evidence-manifest.json) 中的哈希仍全部一致 |

## 1. 口径（负责人 2026-11-06 决定）

B 的第三条“没有能定位到代码或提示词的误拒或缺陷”调整如下（即复核中提出的第 3 种）：

1. **只看三个流水线。** single 组（agent 循环）的校验误拒照常记录，留到 P5 处理，不阻止 P2 冻结。
2. **只有造成后果的误拒才阻止冻结。** 后果指降级、失答或已提交回答质量失败。只修复一次、最终正常提交且质量通过的误拒，照常记录、修复并配守卫，但不单独阻止冻结。

B 的其余各条不变，四条 P1 通过条件仍以最终验收集为准。调整的依据是 r9 的统计，见 §5。

## 2. 结论

**按上述口径，B 仍不满足，不冻结，不运行 p2-final。** 唯一的阻断是 Name-pipeline 的冒号误拒，它造成了降级和质量失败（§4）。

| B 条件 | r9 | 说明 |
| --- | --- | --- |
| 三个流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 最多调用依次为 3、2、1 |
| 可核验事实类编造 0，六组计数表“完整” | 满足 | 三个流水线的编造失败都是 0；六组都是“完整”，108 行全部有评分 |
| 流水线中没有造成后果的可定位误拒 | **不满足** | name_compare_two#3（§4） |
| 已提交质量 ≥ 同批 single（只报告） | 三个体系都满足 | 解梦 18/18 对 14/14，姓名 17/18 对 9/12，每日 14/18 对 13/17 |

修复见 [../pilot-r10/tuning-r10.md](../pilot-r10/tuning-r10.md)。

## 3. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 六份 source-hashes 内容相同；重算得 `bdd23e63fb8b084846d8d61eb9875a8bfe308625ace9adca4061c1867af55b81` |
| 被测提交 | 174 个文件中，除 config.yaml 外其余 173 个与 `eed3659` 逐一一致；`3e01d64` 只多文档 |
| 配置 SHA256 | `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3` |
| 请求和返回模型 | 108 行运行与评委的请求、返回都是 `deepseek-v4.1-flash` |
| 记录数与评分 | 每组 18 行，(id, repeat) 不重复；108/108 四个维度均为布尔值 |
| 修复与降级 | Dream 4 次修复、0 次降级；Name 1 次修复、1 次降级（keywords）；Daily 0/0。与 pipeline-problems.md 一致 |
| 发布文件 | evidence-manifest 中的文件全部一致，没有清单外的文件；各 summary 的 `raw_sha256` 与 raw-manifest 一致 |

## 4. 流水线的修复、降级与质量失败

| 回答 | 结果 | 归因 | 是否阻断 |
| --- | --- | --- | --- |
| Name / compare_two#3 | 两稿被拒，keywords 降级，质量失败（模板只罗列各格，没回答哪个更好） | **可定位误拒**：“两个名字：都留意外格2”中，冒号让 `COLLECTIVE` 认不出共同主语。张伟、李娜的外格都是 2 | **阻断** |
| Dream / late_grandmother#1 | 修复 1 次，提交，质量通过 | **可定位误拒**：用户原话“去世的奶奶”命中了“祖父母”，这四个字同时又是“去世的亲人”的别名；复述时被归到未命中的“去世的亲人” | 不阻断，r10 照常修 |
| Dream / chased_to_exam#1、#2，flood_and_snake#2 | 各修复 1 次，提交，质量通过 | 按设计拒：解读未收录的考场，或从“没复习”“不敢下去”这类状态推心理 | — |
| Daily / today_general#2、tomorrow_work#2、lucky_color#3 | 质量失败，没有修复 | 评委时区误读：把已标注上海时间的时段再加 8 小时，或按 UTC 日期判断；正文与计算一致。原分保留 | 不是代码误拒 |
| Daily / unknown_birth_time#3 | 质量失败，没有修复 | 依据不足：把合相、三会扩写成具体心理状态。这是写稿质量，不是校验误拒 | 不是代码误拒 |

## 5. single 组的误拒（记录，留到 P5）

| 回答 | 误拒 | 位置 |
| --- | --- | --- |
| Dream-single / hospital_health#2（重试耗尽） | “给自己申请”中的“己申”被当成干支 | `plugins/bazi/validation.py::validate_output` |
| Name-single / compound_surname#1、career_grid#2（重试耗尽） | “地格三者”被读成地格 3 | `plugins/name/validation.py::CLAIMED/GRID` |
| Name-single / without_lead_in#3（重试耗尽） | “天格加地格减人格得18”被读成人格 18 | `plugins/name/validation.py::GRID` |

**风险：**这三处都在共用校验器里，流水线的回答同样会经过它们，只是 r9 的流水线没写出这些说法。如果 r10 的流水线写到了，并因此降级，按现行口径会阻断冻结。负责人决定在 P2 一并修，r10 的 PR 已包含这三处修复（[tuning-r10.md](../pilot-r10/tuning-r10.md)）。

**按体系统计的校验拒绝次数**（single 指 agent 循环中 validation_failed 的工具错误，pipeline 指被拒的稿件）：

| 轮次 | single 三组合计 | 流水线三组合计 |
| --- | ---: | ---: |
| r6 | 88 | 9 |
| r7 | 71 | 16 |
| r8 | 100 | 12 |
| r9 | 88 | 6 |

single 每轮和共用校验器碰撞的次数，大约是流水线的 10 倍。这就是只看流水线的依据。
