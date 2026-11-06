# r13：修正 r12 的两处解梦规则问题，避免姓名编号前重复写姓名格名

| 项目 | 内容 |
| --- | --- |
| 依据 | 负责人的 [r12 已知规则问题](../pilot-r12/known-review-findings.md)、[r12 归因](../pilot-r12/quality-attribution.md)，以及我的 [r12 复核](../pilot-r12/review.md) |
| 判定口径 | 2026-11-06：B 第三条只看流水线，只有造成后果的误拒才阻止冻结；被测代码不能有已知的放过 |
| 被测代码 | r12 跑的是 PR #53 未合并快照 `e1314b4`（源码指纹 `6b81e8c0…`）；本次修正仍提交在 PR #53 上 |
| 方法 | 离线；每个反例都写成测试，在 `e1314b4` 上失败、在修正版上通过；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-07 |

## 1. 修正

| # | 例句 | 修法 | 位置 |
| --- | --- | --- | --- |
| 1 | 这个梦不可能完全没有预示现实中的好转；这个梦不是完全没有预示…… | “完全、根本、压根、从来、丝毫、一点也/都”算作内层否定“没有”的一部分，所以外层的“不可能 / 不是”仍能找到 | `plugins/dream/validation.py::NO_PROPHECY` |
| 2 | 这个梦不是不幸的预兆；……不是不祥的预兆 | “不是X的预兆”里的修饰语可以是完整的不幸、不祥、不好、不利、不吉；其他带否定字的修饰语仍拒 | `plugins/dream/validation.py::DENIED_OMEN` |
| 3 | （李娜段落）外格张伟的外格2 | 提示词：比较两个名字时编号会渲染成“张伟的人格23”，编号前不要再写姓名或格名，也不要用另一个名字的编号 | `pipeline/compose.py::NAME_SYSTEM` |
| 4 | 同上；以及 r11 的“地格李娜的地格11” | 新增闭集检查 `repeated_label`：格名紧跟着编号里又出现的同一格名（外格张伟的外格），以及“格名格名数字”（外格外格2），都要求改写；修复请求会引出这句 | `pipeline/name.py` |

**仍须拒（都有测试）：**

- 这是不幸的预兆；
- 这个梦是不祥的预兆；
- 这个梦不是不幸的预兆，而是好运的预兆；
- 不是不作预兆解读；
- 不能说这个梦根本没有预示好转；
- PR #53 审查 F1 的全部反例。

**不会误拦：**

- 张伟的外格2和李娜的外格2一样；
- 李娜的外格，张伟的外格2；
- 两个名字都可留意外格2；
- 只写编号（渲染为“张伟的外格2的提示”）。

## 2. 测试

| 测试 | `e1314b4` | 本次 |
| --- | --- | --- |
| 解梦：两句“完全没有预示”走完整提交，修复一次，原句没进入成稿 | 2 项失败 | 通过 |
| 解梦：“不是不幸 / 不祥的预兆”走完整提交，0 次修复 | 2 项失败 | 通过 |
| 解梦：“完全没有预示什么”放行；三句不幸、不祥预兆的肯定写法仍拒 | 通过 | 通过 |
| 姓名：编号前重复写“李娜的外格”或“外格”，修复一次，修复请求引出原句 | 2 项失败 | 通过 |
| 姓名：只写编号时 0 次修复，提示词里有新规则 | 失败 | 通过 |

在 `e1314b4` 上，新增测试共 7 项失败。r10、r11、r12 已有的测试和负责人此前的守卫全部保留，照旧通过。CI 范围的 `ruff check`、`ruff format --check` 通过。全量测试结果见 PR。

## 3. 重跑 r13

PR #53 合并后，在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，开跑前先检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r13 --snapshot . --baseline . --publish docs/verification/p2/pilot-r13
```

`docs/verification/p2/pilot-r13/pricing.yaml` 已放好，内容与 r12 相同。

**判定（2026-11-06 口径）：**同时满足以下各项，就冻结代码：

- 三个流水线都是已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3；
- 流水线事实类编造 0，六组计数表都是“完整”；
- 流水线中没有造成降级、失答或质量失败的可定位误拒；
- 被测代码没有已知的放过。

冻结范围是源码指纹覆盖的路径：agents/、app.py、common/、config.yaml、evals/、harness/、knowledge/、memory/、pipeline/、plugins/、scripts/、uv.lock。冻结后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```
