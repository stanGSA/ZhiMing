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
| `dream_teeth_falling#3` | 你梦见牙齿一颗一颗掉下来。 | 这次命中的是“掉牙”，绑定的原话正是“牙齿一颗一颗掉下来”。但输出校验把原话里的“牙齿”拆出来，当成另一个没命中的意象 | 新增 `phrase_hits`：命中意象的完整原话整体算作该命中，原话里的其他别名不再单独核对 |
| `dream_late_grandmother#1` | ……不妨给自己留一点像“回家吃饭”那样的松弛时刻…… | “回家吃饭”不是别名，却经模糊匹配成了“吃饭”，而且只因为加了引号就拒 | 只有 「」 引号里的词才做模糊匹配，因为这是意象的渲染格式；“”《》【】 里必须是确切的别名，才算在提这个意象。引号里的别名照常按位置核对 |

**生效范围：**

- `phrase_hits` 和负责人在 `aa36146` 里加的 `phrase_aliases` 一样，只在流水线提交（`pipeline_run`）和流水线的提交前检查里生效；single 和之后的 agent 回合保持原规则。
- 引号的修改不区分模式。这是只放宽、不收紧的修正，single 也会少一种误拒。

## 3. 测试（`tests/pipeline/test_runner_dream.py`）

| 测试 | `ee05a1d` | 本 PR |
| --- | --- | --- |
| r3 两句原文都走完整提交：0 次修复、不降级、只提交一次 | 失败 | 通过 |
| 原话之外单独写“牙齿”并解读，仍拒 | 通过 | 通过 |
| 梦里的“吃饭”（确切别名加引号）仍拒 | 通过 | 通过 |
| 「回家吃饭」（「」里的近似词）仍拒 | 通过 | 通过 |
| “梦见吃饭，说明……”仍拒 | 通过 | 通过 |
| single 的校验器不认流水线的原话映射 | 通过 | 通过 |

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
