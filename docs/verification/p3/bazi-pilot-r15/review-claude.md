# P3 八字调参集 r15：中断记录复核与开跑前探针

负责人发布的 [execution.md](execution.md) 和各次探针记录不改。

| 项目 | 内容 |
| --- | --- |
| 复核对象 | `737aa58` 发布的 r15 中断记录：[execution.md](execution.md)、[preflight-probe-attempt-1.json](preflight-probe-attempt-1.json) 至 [preflight-probe-attempt-5.json](preflight-probe-attempt-5.json)、[preflight-probe.json](preflight-probe.json) |
| 待测代码 | `b6610ec`（PR #74 合并，含负责人的 `d9d0c74`） |
| 日期 | 2026-11-14 |

## 1. 结论

**r15 没有可复核的实验结果，B 无从判定，也不能冻结。** single 只跑了 3/18 就中断，pipeline 没有启动，部分记录只能用于诊断。负责人的处理正确：探针放行后，实际运行与探针不符就中断，没有补评、重跑或改写样本。

服务端仍未恢复到 r13 以前的行为：

- 前 3 条 single 里，2 条把推理文字当回答返回，1 条达到 12 次调用上限，和 r14 一样。
- 部分评委输出 753—1,256 token，r13 的中位数是 337。
- 第 5 次探针“仅回复OK”用了 31 个输出 token。

**§7 里我给的 20 token 阈值定得太宽，这是我的错。** 一个“OK”只需要一两个 token；第 4 次探针 16 个 token 就已经说明服务端在后台推理，却被阈值放行了。而且那条探针只测纯文本回复，不经过 r14 出问题的工具调用和评委这两条路径。

## 2. 新的开跑前探针（本 PR）

`scripts/service_probe.py` 发三次请求。服务端真不推理时，每次只需要几个 token：

| 探针 | 内容 | 不通过的条件 |
| --- | --- | --- |
| `runtime_reply` | 运行模型“仅回复OK” | 回复不是 OK；输出超过 3 token；有 reasoning_tokens 或 reasoning_content；没有 usage |
| `runtime_tool_call` | 运行模型调用无参数工具 `get_profile`，不写正文 | 不是恰好一次 get_profile；参数不是空对象（如 r14 的 `_placeholder`）；返回了正文（如 r14 把推理当回答）；输出超过 40 token；有推理内容 |
| `judge_<名字>_reply` | 评委按 `eval_judges` 的请求参数（thinking=disabled、max_tokens=8192）“仅回复OK” | 同 `runtime_reply` |

- 任一探针不通过，退出码 1。结果写到 `reports/connectivity/service-probe.json`，不含密钥、地址或请求头；出错时只记错误类型和状态码。
- 测试在 `tests/tooling/test_service_probe.py`：用 r15 第 4、5 次探针的 16、31 token，以及 r14 的推理当回答、`_placeholder` 参数、评委 5,304 token 构造反例，都判为不通过；正常回复（“OK”1—2 token、空参数的工具调用）判为通过。
- 探针通过也不能保证整轮正常。所以开跑后仍请像这次一样盯着前几条，发现推理当回答就中断。

被测的八字代码没有改。`scripts/` 在源码指纹的取样范围内，所以 r15 的被测提交和指纹会换成本 PR 合并后的版本。

## 3. 负责人的 `d9d0c74`

`以……分批……为主`前面写“不建议 / 并不适合 / 不太适合……”时按否定放行，“不是不建议……”仍拒。我核对了：原有的 `DENIED_BEFORE` 只认紧挨推荐词的否定，`BATCH_PRINCIPLE` 的“以”前面隔着“建议 / 适合”，补一层是对的；新增的 3 个用例在合并后的版本上通过。

## 4. r15 重跑（负责人本机）

在本 PR 合并后的 `claude_modify_model` 上运行。`pricing.yaml` 不变（`d6d6cb2c…`）。

```powershell
Copy-Item config.yaml reports/config.personal.before-r15.yaml
```

```powershell
Copy-Item reports/p3-bazi-r9/config.experiment.yaml config.yaml
```

```powershell
if ((Get-FileHash config.yaml -Algorithm SHA256).Hash -ne '3DFA2E81873C876568582D1B3138E802AA7E1D7C59DD60E03A52C94A87557D1B') { throw 'config.yaml 不是约定配置 3dfa2e81' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.service_probe --judge pro
```

```powershell
if ($LASTEXITCODE -ne 0) { Copy-Item reports/config.personal.before-r15.yaml config.yaml; throw '服务端探针未通过，暂停 r15' }
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r15 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r15
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r15/Bazi-single reports/p3-bazi-r15/Bazi-pipeline --answers --output reports/p3-bazi-r15/quality-reasons.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r15/Bazi-single reports/p3-bazi-r15/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r15/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r15/fabrication-counts.md
```

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r15/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r15/pipeline-problems-raw.md
```

```powershell
Copy-Item reports/config.personal.before-r15.yaml config.yaml
```

- r15 的 `p1_campaign` 会接着写 `reports/p3-bazi-r15`。这次中断留下的部分运行目录和检查点，请先移到别处保存，比如 `reports/p3-bazi-r15-interrupted-1`，再开跑，以免续跑旧检查点。
- 请照 r14 的范围首发证据：36 份全文、repair-evidence.json、repair-quotes.json；evidence-manifest 按入库后的字节生成。
- 请把探针结果 `service-probe.json` 一并发布，并报两组评委和运行的输出 token 中位数。

## 5. 服务端一直不恢复时

探针一直不通过，或通过后运行仍出现推理当回答，那么在这个服务上跑出的结果都不能作冻结依据。可以选的方向（负责人决定）：

- 等服务恢复，每次开跑前跑探针。
- 换一个能遵循 thinking=disabled 的同模型接入。模型和评委仍是 `deepseek-v4.1-flash`，但要在 execution.md 里记下接入的变化。
- 改评委或运行模型的设置。这会改动已拍板的口径，需要负责人另行决定。
