# r10：修复 r9 流水线中的两处误拒

| 项目 | 内容 |
| --- | --- |
| 依据 | 负责人的 [r9 评估](../pilot-r9/assessment.md)、[校验复核](../pilot-r9/validation-findings.md)，以及我的 [r9 复核](../pilot-r9/review.md) |
| 判定口径 | 负责人 2026-11-06 决定的第 3 种：第三条只看流水线，只有造成后果的误拒才阻止冻结（见计划 P2 实施记录） |
| 被测代码 | r9 为 `eed3659`（源码指纹 `bdd23e63…`）；本 PR 基于 `3e01d64`（只多了文档） |
| 方法 | 离线，用 r9 原句构造测试；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-06 |

## 1. 修了什么

| # | 体系 | r9 原句 | 是否阻断 | 修法 | 位置 |
| --- | --- | --- | --- | --- | --- |
| 1 | 姓名 | 两个名字：都留意外格2数提示的基础与分工问题 | **阻断**：两稿被拒，降级，质量失败 | 共同主语与“都/均/皆”之间允许一个冒号或逗号 | `plugins/name/validation.py::COLLECTIVE` |
| 2 | 解梦 | 你梦到去世的奶奶在老房子里给你做饭 | 不阻断：修复一次后提交 | 某个命中的来源短语如果整体恰好是另一个意象的别名，这个短语本身就绑定到该命中 | `plugins/dream/validation.py::phrase_hits` |

single 组的三处误拒按口径不在本 PR 修：“己申”被当成干支、“地格三者”、“天格加地格减人格得18”。它们都在共用校验器里，流水线也可能碰到，见 [r9 复核 §5](../pilot-r9/review.md)。要不要在 P2 一并修，等负责人决定。

## 2. 范围与守卫

**冒号：**

- 只放宽“共同主语 +（冒号或逗号）+ 都”；
- 没有“都”时，“两个名字：外格2”仍不绑定；
- 前置否定（并非两个名字：都……）仍不绑定；
- 主语后面又写出全名时，后面的数值归那个名字；
- 数值仍要对每个名字逐一核对。

**来源短语：**

- 只绑定这一个完整短语（去世的奶奶），而且只在 `matcher.spans` 恰好给出一个覆盖全句的别名时才绑定；
- 由多个意象组成的短语（猫和蛇）不绑定，沿用 PR #46 的守卫；
- 另一个意象的其他别名（去世的亲人、去世的爷爷）仍是未命中；
- 只在流水线里生效，单 agent 校验器不继承。

## 3. 测试

| 测试 | `eed3659` | 本 PR |
| --- | --- | --- |
| 姓名：r9 原句走完整提交，0 次修复、不降级 | 失败 | 通过 |
| 姓名：“两个名字：都留意外格4”“两个名字，都留意人格22”被拦，并指出哪个名字不符 | 被拦，但报的是“须写明是哪个名字” | 通过 |
| 姓名：没有“都”、前置否定、主语后又写全名，仍按原规则拦 | 通过 | 通过 |
| 解梦：r9 原句走完整提交，0 次修复 | 失败 | 通过 |
| 解梦：“去世的奶奶在梦里给你做饭，往往反映……”走完整提交 | 通过 | 通过 |
| 解梦：去世的亲人 / 去世的爷爷 / 同句另有未命中的猫，仍拒 | 通过 | 通过 |
| 解梦：多意象短语不绑定（PR #46） | 通过 | 通过 |
| 解梦：单 agent 校验器不继承这个绑定 | 失败 | 通过 |

负责人此前的守卫全部保留，照旧通过。CI 范围的 `ruff check`、`ruff format --check` 通过。全量测试结果见 PR。

## 4. 重跑 r10

合并后在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，开跑前先检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r10 --snapshot . --baseline . --publish docs/verification/p2/pilot-r10
```

`docs/verification/p2/pilot-r10/pricing.yaml` 已放好，内容与 r9 相同。后续命令同 [r9 的 reproduction.md](../pilot-r9/reproduction.md)，把 `p2-r9` 换成 `p2-r10`。

**判定（新口径）：**同时满足以下各项，就冻结代码：

- 三个流水线都是已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3；
- 流水线事实类编造 0，六组计数表都是“完整”；
- 流水线中没有造成降级、失答或质量失败的可定位误拒。

冻结范围是源码指纹覆盖的路径：agents/、app.py、common/、config.yaml、evals/、harness/、knowledge/、memory/、pipeline/、plugins/、scripts/、uv.lock。冻结后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```

跑完后用 `scripts.quality_reasons` 的 `--reviewed` 流程生成编造计数表，用 `scripts.pipeline_problems` 列出问题原文。
