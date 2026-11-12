# P3 八字调参集 r10 复核：不满足 B，按约定配置重跑 r11

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot-r10 结果（`ad93e34`）：[execution.md](execution.md)、[comparison.md](comparison.md)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[paired.json](paired.json)、[fabrication-counts.md](fabrication-counts.md)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[failures-Bazi-pipeline.md](failures-Bazi-pipeline.md)、[failures-Bazi-single.md](failures-Bazi-single.md) |
| 被测代码 | `9def1016a177d145c859f452e851dfac3d06f417`，即 PR #69 合并（`a23660e`）后加负责人的测试修正；源码与 `edd728d` 相同。源码指纹 `5101e0d82358fd8f0bf196aa190b76efe0f4307cacf06dfb63bbda2b937c9957` |
| 实验配置 | **`124e1324…`，不是约定的 `3dfa2e81…`**（§2.1） |
| 方法 | 离线：重算指纹，逐文件对照 `9def101`；核对模型、raw_sha256、评分完整性和 pipeline-problems-raw.md。本轮没有发布回答原文、评委理由、被拒草稿和 evidence-manifest，归因、已知放过和编造分类都无法核对（§2.2）。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-12 |

## 1. 结论

**本轮不能作为冻结依据，B 不满足，代码不改，按约定配置重跑 r11。** 原因有三条，都不是代码缺陷：

- **配置不是约定的 `3dfa2e81…`**：r10 用的是另一份本机配置，SHA256 为 `124e1324…`，`pipeline.systems` 为 `[tarot, bazi]`，其他参数也来自那份配置。约定配置是负责人保存的基础配置 `248e6db0…`，只在 `pipeline.systems` 末尾加 `bazi`（见 bazi-pilot/execution.md），r1–r9 都用它。
- **single 有 3 行未评分**：评委两次请求都返回空内容，输出 token 用到 16,384 的上限。按约定，未评分行保留、不补评，“两组完整”因此不满足。
- **编造分类没有完成，已知放过无法核对**：计数表 single 待判 5 条、pipeline 待判 2 条；回答原文和评委理由都没有发布，我无法判类别，也无法逐份看投资题和时机题正文。

单看已发布的数字，流水线本轮很好：

- 提交 18/18，调用最多 2 次，修复 2、降级 0；
- 已提交质量 16/18，同批 single 为 2/13，其中 10 条已评分、3 条未评分；
- 两次修复都是真问题，没有误拒的迹象（§3）。

这些数字是在非约定配置下得到的，只作参考。

| B 条件 | r10 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；工程检查 18/18；最多 2 次，共 20 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | single 3 行未评分；两组共 7 条待判（§2.2） |
| 没有造成降级、失答或质量失败的可定位误拒 | 已发布部分没有发现 | 2 次修复都是真问题，降级 0（§3） |
| 没有已知放过 | **无法核对** | 回答原文没有发布 |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 16/18 对 2/13 |
| （前提）约定配置 `3dfa2e81…` | **不满足** | 实际 `124e1324…`（§2.1） |

| §5 指标（参考，非约定配置） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 待判（2 条编造失败） | 待判（5 条编造失败，另 3 行未评分） |
| 降级比例（≤ 10%，监控项） | 0/18 | — |
| 每题模型调用（≤ 3） | 约 1.11（20/18），最多 2 | 6.0（108/18），最多 9 |
| 每题输入 token（≤ 20,000） | 约 5,397（97,147/18）；投资 #3 一题 20,442 | 约 37,989（683,798/18） |
| P95 耗时（≤ 90 秒） | 21.8 秒 | 52.3 秒 |

## 2. 证据核对

| 核对项 | 结果 |
| --- | --- |
| 源码指纹 | 两份 source-hashes 字节相同，183 项；按 `sha256(json.dumps(hashes, sort_keys=True))` 重算得 `5101e0d8…`，与两份 summary 一致 |
| 被测提交 | 183 项都在 `9def101` 的 worktree 中，除 config.yaml 外 182 项逐文件一致；取样范围（`scripts/live_week23.py`）没有漏取样的文件。`edd728d..9def101` 只改了 `tests/pipeline/test_bazi_pilot_r10.py`，不在取样范围内；`9def101..ad93e34` 只改了 `docs/verification/p3/bazi-pilot-r10/` |
| 配置 | source-hashes 中 config.yaml 为 `124e1324…`，与 execution.md 一致，**不是 `3dfa2e81…`** |
| pricing.yaml | `d6d6cb2c…`，与 r9 逐字节相同 |
| 模型 | 两组 36 行的运行请求和返回都是 `deepseek-v4.1-flash`；有评分的行 requested/returned 也都是 `deepseek-v4.1-flash` |
| raw 与发布文件 | 两组 summary 的 raw_sha256 与 raw-manifest 一致，run_id 与路径一致。本轮没有 evidence-manifest、trace-manifest、integrity.json，发布文件的哈希无从对照 |
| 提交状态 | 流水线 18 条全部 submit_reading，0 次工具错误。single 13 条提交，4 条 ask_user（海外 #1–#3、下个月事业 #2），1 条 retry_limit（性格 #3） |

### 2.1 配置

execution.md 写明：本地工作区、提交历史和 stash 里都找不到 `3dfa2e81…`，负责人确认后改用当前配置，只把 `pipeline.systems` 从 `[tarot]` 扩成 `[tarot, bazi]`。我核对了仓库里 `config.yaml` 的全部历史版本，也没有 `3dfa2e81…`、`248e6db0…` 或 `124e1324…`。约定配置从来都是负责人本机的包装器（`reports/run_bazi_pilot*.py`）用保存的基础配置字节生成的，不在仓库里。

两份配置除 `pipeline.systems` 外还有什么不同，我看不到。single 的 3 行未评分，都是评委输出用满 16,384 token、正文为空。r3–r9 在约定配置下两组都是 36/36 完成评分，但我不能确认这次的空回复与配置有关。

### 2.2 评分完整性与缺失的证据

| 组 | 行 | 原因 |
| --- | --- | --- |
| single | 下个月事业 #1 | 评委两次请求都返回空内容（“评委回复中没有可解析的JSON对象”），输出 16,384 token |
| single | 大运 #2 | 同上；第二次返回了被截断的 JSON 开头 |
| single | 投资 #2 | 同上 |

三行都按服务故障保留，没有补评。流水线 18/18 都有评分。

以下文件本轮没有发布，前几轮复核依赖它们，所以无法核对：

| 缺少的文件 | 影响 |
| --- | --- |
| quality-reasons-with-answers.md（回答原文和评委理由） | 无法判 7 条编造失败的类别（流水线：大运 #1、海外 #2；single：性格 #2、文字出生 #2、下个月事业 #3、文字出生 #3、投资 #3）；无法逐份看投资题有无积极推荐、时机题正文时间有无错写 |
| repair-evidence.json、repair-quotes.json | 无法逐句重放被拒草稿 |
| evidence-manifest.json、integrity.json | 无法对照发布文件的哈希 |

## 3. 修复（流水线 2 次）

| 稿件 | 问题 | 核对 |
| --- | --- | --- |
| 大运 #2 | 正文留了字面的 R 编号；“日主为日主乙木” | 重复标签有原句，是真问题。字面编号的原句没有发布，但这条检查自 r3 以来没有误拒记录 |
| 投资 #3 | “年中前后”标题配 2 月 4 日至 3 月 6 日的流月壬寅 | 真问题：年中是 5–8 月 |

都一次修好，没有降级。r9 的日期区间标题本轮没有再被误拒（pipeline-problems-raw.md 里没有这类问题）。

## 4. PR #69 的评审修正

负责人在 `9def101` 修了我 r10 测试里的一处依赖：`session_at` 原本让文字出生题从问题文字里读出生地，需要本机的 GeoNames 数据；隔离快照里没有这份数据，测试就失败了。现在改为直接写入画像（`TYPED_PROFILE`）。修正正确，在本环境 33 passed。

## 5. r11（负责人本机）

代码不改，在当前 `claude_modify_model` 上**用约定配置**重跑。`docs/verification/p3/bazi-pilot-r11/pricing.yaml` 已放好，与 r10 逐字节相同（`d6d6cb2c…`）。

运行前请先确认工作区 `config.yaml` 是约定配置（基础配置 `248e6db0…` 只在 `pipeline.systems` 末尾加 `bazi`），输出应为 `3DFA2E81873C876568582D1B3138E802AA7E1D7C59DD60E03A52C94A87557D1B`：

```powershell
(Get-FileHash config.yaml -Algorithm SHA256).Hash
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r11 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r11
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r11/Bazi-single reports/p3-bazi-r11/Bazi-pipeline --answers --output reports/p3-bazi-r11/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r11/Bazi-single reports/p3-bazi-r11/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r11/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r11/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r11/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r11/pipeline-problems-raw.md
```

请照 r9 的范围发布证据：

- `quality-reasons-with-answers.md`（即上面 `--answers` 的输出）；
- repair-evidence.json、repair-quotes.json；
- fabrication-reviewed.yaml、fabrication-attribution.md；
- evidence-manifest.json、integrity.json、trace-manifest.json。

评委误读的条目按常规口径直接写成叙述类。如果评委连接出错或返回空内容，照约定保留、不补评。

如果 r11 满足 B，复核会给出最终验收集的命令。

## 6. 已知局限

| 局限 | 处理 |
| --- | --- |
| r10 的流水线结果在非约定配置下得到，不能和 r1–r9 直接比较 | 只作参考，冻结判断以 r11 为准 |
| 约定配置只存在负责人本机，仓库无法复原 | r11 运行前先核对哈希 |
| r9 复核 §8 列的局限（单独日期按整月读、“稳赚”引语只认质疑框架、安全回复本身不作答、绕开词表的积极推荐、共用 `certainty_claim` 的误拒） | 不变 |
