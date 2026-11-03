# r5：修复 r4 定位的三处误拒

| 项目 | 内容 |
| --- | --- |
| 依据 | [r4 复核](assessment.md)、[解梦重放](false-rejection-replay.json)、[姓名重放](name-false-rejection-replay.json)、[否定句重放](certainty-false-rejection-replay.json)、[姓名归因](name-attribution.md)（负责人） |
| 被测代码 | r4 为 `0357a99`（源码指纹 `07482587…`）；本 PR 基于 `fb4813b`（只多了文档） |
| 方法 | 离线，用 r4 的原句构造测试；未调用模型，未读三个 `*_final.yaml` |
| 日期 | 2026-11-03 |

## 1. r4 为什么没通过 B

| 原因 | 性质 | 本 PR |
| --- | --- | --- |
| 解梦 pipeline 一条模型服务超时，提交 17/18 | 服务故障，不是代码缺陷；按负责人的处理保留，不剔除 | 不改代码。只有重跑才能确认 18/18 |
| 解梦 single 一条已提交回答没有评分，计数表“不完整” | 评委请求超时，同上 | 同上 |
| 解梦：“牙齿一颗颗掉下来”被拒 | **定位误拒** | 修 |
| 姓名：“五格”“三项”“一项”“一份”“四吉”里的数字被读成格数或数理 | **定位误拒**（single 4 次重试耗尽，pipeline 2 次降级里占 1 次） | 修 |
| 共用措辞：“而不是把它理解成必然的坎坷”被拒 | **定位误拒**（pipeline 2 次降级里占 1 次） | 修 |

## 2. 三处修法

| 位置 | 修法 | 生效范围 |
| --- | --- | --- |
| `plugins/dream/match.py::NORMALISATIONS`“掉牙” | 允许“一颗颗”“一粒粒”，与“一颗一颗”同义 | 词典查询与校验共用，single 和流水线都受影响 |
| `plugins/dream/validation.py::ungrounded` | 已靠规则命中的意象（`phrase_hits` 绑定的键），正文中符合同一条规则的其他写法也算该命中，不再只认原话里的字面片段 | 与 `phrase_hits` 相同，只在流水线提交时生效 |
| `plugins/name/validation.py::GRID/SHULI` | 中文数字后面紧跟“格、项、个、份、位、种、吉、凶、行……”时，表示计数而不是格数，不再核对；后面紧跟数字时也不截短重读。阿拉伯数字不变（“人格23吉”照样核对） | 姓名的 single 和流水线 |
| `common/output_policy.py::NEGATED_NOUN` | “不必/不要/别/不用/不是/并不是/并非 + 把…（最多 8 字）+ 理解为/理解成/看作/看成/当作/当成/视为/想成/解读为/解读成”否定其后的确定性词 | 共用，所有体系 |

**守卫：** “它必然遭遇坎坷”“不要把钱都投进去，理解成必然的收益”（中间隔了逗号）“这不是把它理解成必然，而是你一定会成功”照样拒；“另外人格24也很好”“人格是二十四”“人格24吉”“总格五”照样核对；原话之外单独解读“牙齿”照样拒。

## 3. 测试

| 测试 | `fb4813b` | 本 PR |
| --- | --- | --- |
| `test_runner_dream`：“梦里牙齿一颗颗掉下来……”走完整提交，0 次修复 | 失败 | 通过 |
| `test_runner_name`：r4 的 6 句计数一起写进稿件，0 次修复、不降级 | 失败 | 通过 |
| `test_runner_name`：计数旁边的 4 种错误格数照样被拦 | 通过 | 通过 |
| `test_negation_and_dates`：3 种否定宿命论的写法放行 | 失败 | 通过 |
| `test_negation_and_dates`：3 种确定性断言照样拒 | 通过 | 通过 |

解梦和姓名插件的三份测试文件、`test_runner_dream.py` 合计 196 项通过；全量结果见 PR。

## 4. 重跑 r5

合并后在本机拉到最新的 `claude_modify_model`，`config.yaml` 保持 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。r4 首次尝试曾因服务不可用中断，运行中也出现过超时，开跑前请先按 r4 的做法检查一次接口：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r5 --snapshot . --baseline . --publish docs/verification/p2/pilot-r5
```

`docs/verification/p2/pilot-r5/pricing.yaml` 已放好，与前几轮逐字节相同。后续命令同 r4 的 [reproduction.md](reproduction.md)，把 `p2-r4` 换成 `p2-r5`。

判定沿用 B 标准，不变。全部满足就宣布代码冻结，冻结范围是源码指纹覆盖的路径，然后运行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2-final --root reports/p2-final --snapshot . --baseline . --publish docs/verification/p2/final
```

**如果 r5 又出现服务超时或评委未评分：** 按 r4 的做法保留，不剔除，所以这一轮仍然不满足 B。如果到时候代码侧已经没有可定位的缺陷，要不要只为服务故障再跑一轮，由负责人决定；我不会为此改动代码。
