# P3 八字调参集 r10 复核：不满足 B，r11 修顺逆排漏拦后按约定配置重跑

| 项目 | 内容 |
| --- | --- |
| 复核对象 | 负责人发布的 bazi-pilot-r10 结果（`ad93e34`）：[execution.md](execution.md)、[comparison.md](comparison.md)、两组 summary 与 source-hashes、[raw-manifest.json](raw-manifest.json)、[paired.json](paired.json)、[fabrication-counts.md](fabrication-counts.md)、[pipeline-problems-raw.md](pipeline-problems-raw.md)、[failures-Bazi-pipeline.md](failures-Bazi-pipeline.md)、[failures-Bazi-single.md](failures-Bazi-single.md) |
| 被测代码 | `9def1016a177d145c859f452e851dfac3d06f417`，即 PR #69 合并（`a23660e`）后加负责人的测试修正；源码与 `edd728d` 相同。源码指纹 `5101e0d82358fd8f0bf196aa190b76efe0f4307cacf06dfb63bbda2b937c9957` |
| 实验配置 | **`124e1324…`，不是约定的 `3dfa2e81…`**（§2.1） |
| 方法 | 离线：重算指纹，逐文件对照 `9def101`；核对模型、raw_sha256、评分完整性和 pipeline-problems-raw.md。本轮没有发布回答原文、评委理由、被拒草稿和 evidence-manifest，归因、已知放过和编造分类大多无法核对（§2.2）。大运 #1 的顺逆排错误和配置差异来自负责人在 PR #70 评审里引用的本机原始记录（§3.1、§2.1）。r11 的新检查用 r1–r9 全部 204 份归档回答在两个版本上重放，并用两组回答里提到顺逆排的 34 句按各自命盘核对。没有调用模型，没有改动负责人发布的文件 |
| 日期 | 2026-11-12 |

## 1. 结论

**本轮不能作为冻结依据，B 不满足。r11 先修大运顺逆排的漏拦，再用约定配置重跑。** 原因有四条：

- **已知放过：大运 #1 把顺排写成逆排**（负责人在 PR #70 评审里指出）。计算结果 `dayun.forward = true`，正文却写“按出生到节令的时间来定，逆排从上一个‘节’数到出生”。评委判 supported、fabricated 都是 false，稿件没有修复、直接提交。现有检查不核对顺逆排，事实表也没写这份命盘用哪一种（§3.1）。这是可核验事实写错，流水线事实类不为 0。
- **配置不是约定的 `3dfa2e81…`**：r10 用的是另一份本机配置 `124e1324…`。差异包括 `pipeline.systems`，还有评委打开了思考模式（§2.1）。约定配置是负责人保存的基础配置 `248e6db0…` 只在 `pipeline.systems` 末尾加 `bazi`（见 bazi-pilot/execution.md），r1–r9 都用它。
- **single 有 3 行未评分**：两次评分尝试后仍无法解析（§2.2）。按约定，未评分行保留、不补评，“两组完整”因此不满足。
- **编造分类没有完成，其余已知放过无法核对**：计数表 single 待判 5 条、pipeline 待判 2 条。大运 #1 按上面的事实错误判事实类；其余 6 条和投资题、时机题正文，因回答原文和评委理由没有发布，我无法核对。

单看已发布的数字，流水线本轮很好：

- 提交 18/18，调用最多 2 次，修复 2、降级 0；
- 已提交质量 16/18，同批 single 为 2/13，其中 10 条已评分、3 条未评分；
- 两次修复都是真问题，没有误拒的迹象（§3.2）。

这些数字是在非约定配置下得到的，只作参考。

| B 条件 | r10 | 依据 |
| --- | --- | --- |
| 流水线已提交 18/18、步数和预算失败 0、每轮调用 ≤ 3 | 满足 | 18/18；工程检查 18/18；最多 2 次，共 20 次 |
| 事实类编造 0，两组计数表“完整” | **不满足** | 流水线大运 #1 顺逆排写错（事实类）；single 3 行未评分；其余 6 条待判（§2.2） |
| 没有造成降级、失答或质量失败的可定位误拒 | 已发布部分没有发现 | 2 次修复都是真问题，降级 0（§3.2） |
| 没有已知放过 | **不满足** | 大运 #1 顺逆排（§3.1）；其余回答原文没有发布，无法核对 |
| 已提交质量 ≥ 同批 single（只报告） | 满足 | 16/18 对 2/13 |
| （前提）约定配置 `3dfa2e81…` | **不满足** | 实际 `124e1324…`（§2.1） |

| §5 指标（参考，非约定配置） | 流水线 | single |
| --- | --- | --- |
| 可核验事实编造（目标 0） | 至少 1（大运 #1）；海外 #2 待判 | 待判（5 条编造失败，另 3 行未评分） |
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

execution.md 写明：本地工作区、提交历史和 stash 里都找不到 `3dfa2e81…`，负责人确认后改用当前配置，只把 `pipeline.systems` 从 `[tarot]` 扩成 `[tarot, bazi]`。仓库里 `config.yaml` 的全部历史版本中也没有 `3dfa2e81…`、`248e6db0…` 或 `124e1324…`，约定配置从来都是负责人本机的包装器（`reports/run_bazi_pilot*.py`）用保存的基础配置字节生成的。

负责人在 PR #70 评审里核对了本机文件：`reports/p3-bazi-r9/config.experiment.yaml` 的 SHA256 正是 `3dfa2e81…`，r1–r9 也都保留了同哈希的备份。它与 r10 实际配置的差异如下（引自评审，我无法直接查看这两份文件）：

| 参数 | 约定配置 `3dfa2e81…` | r10 实际配置 `124e1324…` |
| --- | --- | --- |
| `pipeline.systems` | `[tarot, dream, name, daily, astro, bazi]` | `[tarot, bazi]` |
| `eval_judges.pro.thinking` | `disabled` | `enabled` |
| `eval_judges.pro.reasoning_effort` | 未设置 | `high` |

两边的评委模型都是 `deepseek-v4.1-flash`，`max_tokens` 都是 8192。r10 的评委开了思考模式，这是排查空正文和截断的重要线索；但现有证据不足以确认因果。r3–r9 在约定配置下两组都是 36/36 完成评分。r10 执行记录已写明，是负责人确认后改用替代配置的。

### 2.2 评分完整性与缺失的证据

三行都是两次评分尝试后仍解析失败（“评委回复中没有可解析的JSON对象”）。`judge_answer` 把两次请求的 usage 相加，单次输出上限是 8192，下表是两次的累计输出：

| 组 | 行 | 保存的正文 | 两次累计输出 token |
| --- | --- | --- | ---: |
| single | 下个月事业 #1 | 两次都为空 | 16,384 |
| single | 大运 #2 | 第一次为空，第二次是不完整的 JSON | 15,931 |
| single | 投资 #2 | 两次都为空 | 16,384 |

三行都按服务故障保留，没有补评。流水线 18/18 都有评分。

以下文件本轮没有发布，前几轮复核依赖它们，所以无法核对：

| 缺少的文件 | 影响 |
| --- | --- |
| quality-reasons-with-answers.md（回答原文和评委理由） | 除大运 #1（§3.1）外，无法判其余 6 条编造失败的类别（流水线：海外 #2；single：性格 #2、文字出生 #2、下个月事业 #3、文字出生 #3、投资 #3）；无法逐份看投资题有无积极推荐、时机题正文时间有无错写 |
| repair-evidence.json、repair-quotes.json | 无法逐句重放被拒草稿 |
| evidence-manifest.json、integrity.json | 无法对照发布文件的哈希 |

## 3. 归因

### 3.1 已知放过：大运 #1 把顺排写成逆排

负责人在 PR #70 评审里引用了本机原始记录 `Bazi-pipeline/20261111T133204-493a5b80/live.json`（SHA256 `de550680…`，与发布的 summary、raw-manifest 一致）：

- 计算结果：`calculated_facts.bazi_result.dayun.forward = true`，顺排；
- 最终回答：“按出生到节令的时间来定，逆排从上一个‘节’数到出生。”；
- 评委：顺逆排矛盾，supported_conclusion=false、no_fabricated_facts=false；
- 运行：`submit_reading`，没有修复、没有降级。

在 `9def101` 上，这句交给 `Bazi.problems` 和 `reading_problems` 都返回空。根因有两层：

- `dayun_problems` 只核对首步大运、当前大运、交运年份、起运日期和岁数，不核对顺逆排；
- 写作者看不到这份命盘用哪一种。大运释义同时写了“顺排……逆排……”两种规则，关键词也同时列着“顺排”“逆排”，上下文没有说明。

这是可核验事实写错，计**事实类**，流水线事实类因此不为 0。

### 3.2 修复（流水线 2 次）

| 稿件 | 问题 | 核对 |
| --- | --- | --- |
| 大运 #2 | 正文留了字面的 R 编号；“日主为日主乙木” | 重复标签有原句，是真问题。字面编号的原句没有发布，但这条检查自 r3 以来没有误拒记录 |
| 投资 #3 | “年中前后”标题配 2 月 4 日至 3 月 6 日的流月壬寅 | 真问题：年中是 5–8 月 |

都一次修好，没有降级。r9 的日期区间标题本轮没有再被误拒（pipeline-problems-raw.md 里没有这类问题）。

## 4. 评审与修正

### 4.1 PR #69 的测试修正

负责人在 `9def101` 修了我 r10 测试里的一处依赖：`session_at` 原本让文字出生题从问题文字里读出生地，需要本机的 GeoNames 数据；隔离快照里没有这份数据，测试就失败了。现在改为直接写入画像（`TYPED_PROFILE`）。修正正确，在本环境 33 passed。

### 4.2 PR #70 的评审（负责人 2026-11-12）

| 意见 | 处理 |
| --- | --- |
| [P1] 大运 #1 顺逆排写错，现有校验放过；“代码不改”的安排要重新评估 | 同意。§1、§3.1 改为已知放过、事实类；r11 增加顺逆排检查，事实表写明方向（§5） |
| 配置差异有可核对结果，应补评委参数变化；r11 要给出明确的配置恢复来源、断言哈希、保留并恢复个人配置、记录评委参数和源码指纹 | 同意。§2.1 补差异表；§6 改为从 `reports/p3-bazi-r9/config.experiment.yaml` 恢复，哈希不符就停止，运行后恢复个人配置 |
| [P3] 16,384 是两次请求的累计输出，单次上限 8192 | 同意。§1、§2.2 改为“两次评分尝试后仍解析失败”，分列正文和累计输出 |
| 先补齐 r10 回答、评委理由、修复证据与 manifest 并完成分类 | 这些文件在负责人本机，需要负责人发布；本 PR 只能列出缺口（§2.2） |

### 4.3 后续评审修复

针对 `b38706a` 的后续评审发现两处边界问题，已补充守卫并修复：

- 顺排命盘上的“大运采用逆排，顺排只是另一种排法”被当作一般规则，零修复提交；现在逐分句识别条件规则、定义和本命断言，省略主语的“大运采用……”以及“此八字……”照样核对。单纯提到另一种排法不能豁免错误断言。
- 逆排女命上的“阳年男命顺排”是正确的一般规则，却在两稿后降级为关键词；现在单独介绍一种条件规则或定义也放行，不再要求一句里必须同时出现两种排法。

两种命盘均补了端到端测试：错误断言修复一次后提交，一般规则一次提交且不降级。新增用例在修复前有 20 项断言失败；修复后本文件的顺逆排测试共 49 项通过。原有否定、双重否定、程度词和转折守卫保留。

补充离线重放：读取本机 r1–r9 两组的最后完整批次，对含有大运方向计算事实的 320 份可用回答比较 `b38706a` 与修订后的方向检查，结果没有变化。该数包含 single 与 pipeline，与 §5 原复核的 204 份归档范围不同；没有重新调用模型或修改评分。

## 5. r11 的改动（本 PR）

| 改动 | 内容 |
| --- | --- |
| 顺逆排检查（`Bazi.direction_problems`） | 正文描述本命排法时与 `dayun.forward` 核对，包括省略主语的“大运采用……”和“此八字……”；同句提到另一种方向不豁免。按分句识别“阳年男命顺排”这类条件规则、“逆排的规则是……”这类定义、“顺排从……，逆排从……”这类成对定义和“顺排则相反”这类对照说明；只介绍一种规则也放行。否认错误的排法放行；否认正确的、含糊其辞的照拒 |
| 事实表写明方向（`Bazi.context`） | 上下文加一行“这份命盘的大运顺排：起运时间从出生数到下一个‘节’。正文提到排法时只能写顺排。”（逆排同理） |
| 关键词（`direction_keywords`） | 大运释义的关键词只留这份命盘用的那一种，事实表和关键词降级稿都去掉另一种 |

题集、rubric、评委配置、`*_final.yaml` 都没有改；既有断言保留，新增上述边界回归。

**仍须拒的守卫**（`tests/pipeline/test_bazi_pilot_r11.py`，顺排命盘上）：

| 类别 | 例句（都要拒） |
| --- | --- |
| 同句其他意象 | 你的大运逆排，顺排则相反。／首步大运丙辰，大运逆排。 |
| 先否定后肯定 | 不是顺排，而是逆排。 |
| 外层否定 | 不能说不是逆排。 |
| 程度词插入 | 你的大运不完全是顺排。 |
| 双重否定 | 并非不是逆排。 |
| 转折后重新肯定 | 不是逆排，但其实是逆排。 |
| 否认正确的排法 | 这份命盘不是顺排。／是逆排，不是顺排。 |

逆排命盘（性格题的女命，甲戌阳年）上，“你的大运是顺排”同样要拒。

**仍放行**：“你的大运是顺排”“不是逆排，而是顺排”“这份命盘不是逆排”“根本不是逆排”；两种命盘上的“顺排从出生数到下一个节，逆排从上一个节数到出生”“阳年男命顺排、阴年男命逆排”；逆排命盘上的“你的大运逆排，顺排则相反”。

**端到端**（脚本写作者，不调用真实服务）：

- 大运题首稿写 r10 原句：修复 1 次、调用 2 次、不降级，修复请求引出原句；第二稿写“顺排从出生数到下一个‘节’”后提交。
- 只写正确方向：调用 1 次，不修复。
- 顺排、逆排两种命盘的事实表都写明方向，起运一行的关键词只留对应的一种。

**在评审版本上失败、在修订版上通过**：

- 把测试文件和 `tests/pipeline/fixtures/bazi_pilot_r10_review.json` 放进 `9def101` 的独立 worktree 运行：5 项中 4 项以断言失败（AssertionError，没有导入错误），1 项（只写正确方向、不修复）两边都通过。
- 修订版 5 passed。

**对历史回答的影响**：

- r1–r9 全部 204 份归档在两个版本上逐句、逐层重放，结果完全相同。
- 两组回答里提到顺逆排的 34 句，按各题实际命盘核对，新检查一句都没有拒。

## 6. r11（负责人本机）

在 r11 合并后的 `claude_modify_model` 上**用约定配置**重跑。`docs/verification/p3/bazi-pilot-r11/pricing.yaml` 已放好，与 r10 逐字节相同（`d6d6cb2c…`）。

先核对 r9 备份的哈希，再备份个人配置。用 `finally` 在运行结束或失败后按原字节恢复配置；备份已存在时停止，避免重跑覆盖：

```powershell
$experimentConfig = 'reports/p3-bazi-r9/config.experiment.yaml'
$expectedConfigHash = '3DFA2E81873C876568582D1B3138E802AA7E1D7C59DD60E03A52C94A87557D1B'
if ((Get-FileHash -LiteralPath $experimentConfig -Algorithm SHA256 -ErrorAction Stop).Hash -ne $expectedConfigHash) { throw '实验配置不是约定配置 3dfa2e81' }
$personalBackup = 'reports/config.personal.before-r11.yaml'
if (Test-Path -LiteralPath $personalBackup) { throw '个人配置备份已存在，请先核对，不能覆盖' }
$configPath = (Resolve-Path config.yaml).Path
$personalConfigBytes = [System.IO.File]::ReadAllBytes($configPath)
[System.IO.File]::WriteAllBytes((Join-Path (Get-Location).Path $personalBackup), $personalConfigBytes)
try {
    Copy-Item -LiteralPath $experimentConfig -Destination $configPath -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -ne $expectedConfigHash) { throw '运行配置哈希不符' }
    .venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r11 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r11
    if ($LASTEXITCODE -ne 0) { throw "Campaign 退出码：$LASTEXITCODE，请检查结果" }
} finally {
    [System.IO.File]::WriteAllBytes($configPath, $personalConfigBytes)
}
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

execution.md 请记录：配置恢复来源和哈希、评委的 `thinking` 与 `reasoning_effort` 实际取值、源码指纹、被测提交。

请照 r9 的范围发布证据：

- `quality-reasons-with-answers.md`（即上面 `--answers` 的输出）；
- repair-evidence.json、repair-quotes.json；
- fabrication-reviewed.yaml、fabrication-attribution.md；
- evidence-manifest.json、integrity.json、trace-manifest.json。

评委误读的条目按常规口径直接写成叙述类。如果评委连接出错或返回空内容，照约定保留、不补评。

如果 r11 满足 B，复核会给出最终验收集的命令。

## 7. 已知局限

| 局限 | 处理 |
| --- | --- |
| r10 的流水线结果在非约定配置下得到，不能和 r1–r9 直接比较 | 只作参考，冻结判断以 r11 为准 |
| 约定配置只存在负责人本机，仓库无法复原 | r11 从 `reports/p3-bazi-r9/config.experiment.yaml` 恢复，运行前断言哈希 |
| 顺逆排检查只认“顺排 / 逆排 / 顺行 / 逆行 / 顺推 / 逆推 / 顺数 / 逆数 / 倒排 / 倒推” | “往前数”“往后推”这类口语不核对；事实表已写明方向 |
| r9 复核 §8 列的局限（单独日期按整月读、“稳赚”引语只认质疑框架、安全回复本身不作答、绕开词表的积极推荐、共用 `certainty_claim` 的误拒） | 不变 |
