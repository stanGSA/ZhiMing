# r12：修正 PR #53 审查 F1–F4，修复引句补上相邻两句

| 项目 | 内容 |
| --- | --- |
| 依据 | 负责人的 [PR #53 审查](../pilot-r11/pr53-review.md)、[r11 实验记录](../pilot-r11/assessment.md)，以及我的 [r11 复核](../pilot-r11/review.md) |
| 判定口径 | 2026-11-06：B 第三条只看流水线，只有造成后果的误拒才阻止冻结 |
| 被测代码 | r11 跑的是 PR #53 未合并快照 `cff1f61`（源码指纹 `08485d66…`）；本次修正仍提交在 PR #53 上 |
| 方法 | 离线；审查里的每个反例都写成测试，在 `cff1f61` 上失败、在修正版上通过；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-06 |

## 1. 修正

| 编号 | 审查反例 | 修法 | 位置 |
| --- | --- | --- | --- |
| F1 | 这个梦不可能没有预示现实中的好转；不能说这个梦没有预示现实中的好转；这个梦不是不提供预言 | 新增 `inner_denial`：“没（有）+ 预示/预言”和“不作/不提供……”这两种否定，都要确认外面没有再套一层否定（共用的 `denial_negated`，加上不可能、不会、未必、不见得、难说），中间允许隔一个短主语（这个梦、它、这）。“不是X的预兆”同样做这项检查，修饰词里也不能出现否定字 | `plugins/dream/validation.py` |
| F2 | 你是阳性上升；你的阴性上升 | 去掉“只看前一个字”的写法，改为完整数量词加上升才豁免，例如活跃度、人气、信心、压力、收入，可以带“有所、逐渐”等 | `plugins/astro/validation.py::RISING_QUANTITY` |
| F3 | 陈思远的人格二十四点五；陈思远的数理二十四点五 | 量词表撤回套、些、点；只豁免完整的“一套、一些”，以及后面不接数字的“一点”。格数、数理后面接“点 / .”再接数字一律拒绝，整数部分对也一样（人格二十五点五） | `plugins/name/validation.py::NUMBER_WORD/DECIMAL` |
| F4 | 理由原文“,}”被改写 | `without_trailing_commas` 逐字扫描，跳过字符串和转义，只删字符串外、紧挨闭括号的逗号；修补成功的行同时保存 `unrepaired_reply` | `scripts/live_week23.py` |
| — | r11 Dream chased_to_exam#1 的修复请求没有引句 | 单句找不到时，再试同一字段里相邻的两句，只认完全相同的问题文本 | `pipeline/runner.py::triggering` |

## 2. 测试

| 测试 | `cff1f61` | 本次 |
| --- | --- | --- |
| F1：6 种外层否定写法仍拒；其中 2 种走完整提交，不进入成稿 | 7 项失败 | 通过 |
| F1：r10 的“没有预示什么”“不作诊断或预兆/预示解读”仍放行 | 通过 | 通过 |
| F2：阳性上升、阴性上升、“信心上升，你的上升是白羊座”仍拒 | 2 项失败 | 通过 |
| F2：交际活跃度上升、信心上升、人气上升、压力有所上升、收入有上升空间放行 | 1 项失败（压力有所上升） | 通过 |
| F3：人格 / 数理二十四点五、人格一点五、人格二十五点五、人格25.5 都修复一次 | 5 项失败 | 通过 |
| F3：一套、一些、“人格一点也不差”“人格25，点评如下”放行 | 通过 | 通过 |
| F4：字符串里的“,}”和转义引号保持原样，并保存原始回复 | 失败 | 通过 |
| 修复引句：r11 跨句原文引出相邻两句 | 失败 | 通过 |

在 `cff1f61` 上，新增测试共 17 项失败，其余守卫两边都通过。r10、r11 已有的测试和负责人此前的守卫全部保留，照旧通过。CI 范围的 `ruff check`、`ruff format --check` 通过。全量测试结果见 PR。

## 3. 重跑 r12

PR #53 合并后，在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，开跑前先检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r12 --snapshot . --baseline . --publish docs/verification/p2/pilot-r12
```

`docs/verification/p2/pilot-r12/pricing.yaml` 已放好，内容与 r11 相同。

**判定（2026-11-06 口径）：**以下各项全部满足，就冻结代码：

- 三个流水线都是已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3；
- 流水线事实类编造 0，六组计数表都是“完整”；
- 流水线中没有造成降级、失答或质量失败的可定位误拒；
- 被测代码没有已知的放过。

冻结范围是源码指纹覆盖的路径：agents/、app.py、common/、config.yaml、evals/、harness/、knowledge/、memory/、pipeline/、plugins/、scripts/、uv.lock。冻结后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```
