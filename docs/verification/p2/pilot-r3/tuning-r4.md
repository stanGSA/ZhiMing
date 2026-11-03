# 解梦 r4：修复 r3 定位的两条误拒

| 项目 | 内容 |
| --- | --- |
| 依据 | [r3 复核](assessment.md)、[逐次修复归因](dream-attribution.md)、[误拒重放](false-rejection-replay.json)（负责人） |
| 被测代码 | r3 为 `b38eb2a`（源码指纹 `bc318e86…`）；本 PR 基于 `ee05a1d`（只多了文档） |
| 方法 | 离线，用 r3 的原句和实际命中构造测试；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-03 |

## 1. 为什么还要跑一轮

r3 的结果：

- 三个体系都满足 P1 四条；
- 54 条流水线回答没有编造失败；
- 六组计数表都是“完整”。

但负责人按事先约定的 B 标准，复现了两条能定位到代码的误拒。B 规定这种情况下“修完再跑一轮，但不再为没有归因的单条失败继续调参”。本 PR 只修这两条，不动提示词，不动其他检查。

## 2. 两条误拒和修法

两条都在 `plugins/dream/validation.py::ungrounded`。

| 回答 | 原句 | 原因 | 修法 |
| --- | --- | --- | --- |
| `dream_teeth_falling#3` | 你梦见牙齿一颗一颗掉下来。 | 这次命中的是“掉牙”，绑定的原话正是“牙齿一颗一颗掉下来”。但输出校验把原话里的“牙齿”拆出来，当成另一个没命中的意象 | `phrase_hits` 仅绑定原话中由已有 `NORMALISATIONS` 规则识别的片段；片段内按该命中核对，原话中的其他独立意象仍须检查 |
| `dream_late_grandmother#1` | ……不妨给自己留一点像“回家吃饭”那样的松弛时刻…… | “回家吃饭”不是别名，却经模糊匹配成了“吃饭”，而且只因为加了引号就拒 | 日常建议中的普通引号不作整词模糊匹配；「」或被用作解读主语、明确引为梦境内容的引号仍按意象检查，包含内部别名 |

**生效范围：**

- `phrase_hits` 和负责人在 `aa36146` 里加的 `phrase_aliases` 一样，只在流水线提交（`pipeline_run`）和流水线的提交前检查里生效；single 和之后的 agent 回合保持原规则。
- `phrase_aliases` 的后缀必须处于该命中的确切词典别名内；例如“梦到去世的奶奶”中的“奶奶”可指该命中，“蛇和猫”中的“猫”不能因此获得“蛇”的授权。
- 引号的修改不区分模式；保留日常建议，同时拒绝用普通引号包裹未命中意象后进行解读。

## 3. 测试（`tests/pipeline/test_runner_dream.py`）

| 测试 | `ee05a1d` | 本 PR |
| --- | --- | --- |
| r3 两句原文都走完整提交：0 次修复、不降级、只提交一次 | 失败 | 通过 |
| 原话之外单独写“牙齿”并解读，仍拒 | 通过 | 通过 |
| 梦里的“吃饭”（确切别名加引号）仍拒 | 通过 | 通过 |
| 「回家吃饭」（「」里的近似词）仍拒 | 通过 | 通过 |
| “梦见吃饭，说明……”仍拒 | 通过 | 通过 |
| single 的校验器不认流水线的原话映射 | 通过 | 通过 |

### 合并审查后的边界修复

PR #46 合并提交为 `387a066`。审查发现原修法会放过“梦里的‘回家吃饭’象征被照顾”，以及只命中“蛇”后解读“猫和蛇”的回答。补充修复按上表收窄授权，并保留复合引号中的各个独立意象，避免整词模糊匹配覆盖内部其他意象。

新增 15 项离线回归覆盖：普通引号的梦境/解释语境、不能整词匹配的引号、混合意象、过宽原话及后缀、规范化片段的独立复述、有效别名的后缀，以及 single/pipeline 提交校验的一致性。原有 r3 两句接受测试继续保留。这些离线测试不等于完成 r4 实验，B 标准与原始 r3 证据不变。

验证使用隔离检出中的仓库配置，以及本机既有的 Unihan、星历和地名数据；主工作区配置未改动。结果：

- `pytest tests/pipeline/test_runner_dream.py tests/plugins/test_name_dream_daily.py tests/plugins/test_name_dream_daily_accept_paths.py tests/plugins/test_name_dream_daily_disclosures.py -q`：195 passed。
- `pytest tests/validation/test_accept_paths_generated.py -k dream -q`：4 passed，45 deselected。
- CI 所列源码路径的 `ruff check`、`ruff format --check` 通过；`git diff --check` 通过。

## 4. 重跑 r4

按 B 标准，这是修完定位缺陷后的一轮。合并后在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 r3 的实验配置 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r4 --snapshot . --baseline . --publish docs/verification/p2/pilot-r4
```

`docs/verification/p2/pilot-r4/pricing.yaml` 已放好，与前几轮逐字节相同。后续命令同 r3 的 [reproduction.md](reproduction.md)，把 `p2-r3` 换成 `p2-r4`。

**判定（B 标准，不变）：**

- 三个流水线都是已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3；
- 事实类编造 0，六组计数表都是“完整”；
- 每条质量失败、每次修复和降级都已对照原句归因，没有能定位到代码或提示词的误拒或缺陷；
- 第四条照常计算，如实报告。

全部满足就宣布代码冻结，冻结范围是源码指纹覆盖的路径，然后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```
