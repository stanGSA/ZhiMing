# 阶段 0 执行与验收

日期：2026-10-20（Asia/Shanghai）。按用户指定顺序执行 **F7 → A1/A4 → A2/E4 → E2 → E1 → C1**。任务编号与验收标准取自根目录《项目完善计划书.md》，并参照《占卜Agent项目计划书.md》的架构约束。

**功能修复和离线验证完成；C1 首轮真实回归及充值后的 multi 复测均已归档，端到端关口未通过。** 充值后模型服务恢复，20个题目分批完成评分，严格综合2/20通过。评估脚本中断、修复和重试另行记录。默认仍为 single，没有据本轮数据启用 multi，也没有改动知识库或放宽 guard。

## 已落实的改动

| 编号 | 改动与验收 |
| --- | --- |
| F7 | CLI 帮助、启动语与项目描述列出占星、塔罗、八字、姓名五格、解梦、每日运势六个体系 |
| A1/A4 | 每轮从可注入的时钟刷新当地日期，优先 `consultation_tz`，其次出生 `tz`，均无则 `Asia/Shanghai`；替换系统消息中的旧基准，并传入专家子会话；画像同轮更新时区后同步刷新。每日运势未显式指定咨询时区时采用咨询/出生时区 |
| A2/E4 | 每次合法访问续期12小时；持久化浏览器身份清理期限；到期清除该身份的业务记录和应用trace。重启时及请求前清理，后台每分钟清理；忙碌请求暂缓。升级前已有的 `web-` 用户记录给予12小时宽限；说明已写入README |
| E2 | 危机状态保存在会话独立字段，继续占卜、清空reading、网页新对话和直接排盘不能绕过；独立安全确认轮只回应支持，下一轮才可恢复咨询 |
| E1 | 按用户已填咨询/出生时区选择地区，网页新表单也参与选择。已核实中国大陆12356及110/120、美国988及911；未知或未配置地区使用当地紧急服务提示。来源和日期见[热线核实](hotlines.md) |

`tests/test_stage0.py` 16/16通过。全量pytest收集637项，637/637通过；之后增加的海外实际每日运势测试包含在16项专项中，两次运行去重后638/638通过。JPL DE440s在本机齐备，没有以缺数据跳过替代验收。Ruff lint、修改文件的format检查、`git diff --check`均通过。逐项状态见[测试摘要](pytest-summary.json)。

## DeepSeek 首轮真实回归

使用仓库默认 `deepseek-flash`、关闭思考模式，运行时预算与配置保持原值。四个批次并发启动；每个20题批次内部串行执行。保留首轮结果，不择优替换失败。

| 套件 | 工程通过 | 质量评分通过 | 原严格综合结果 |
| --- | ---: | ---: | ---: |
| 17场景基础验收 | — | — | **14/17** |
| 20题 baseline / single | 4/20 | 9/20 | **2/20** |
| 20题 baseline / multi | 2/20 | 5/20 | **1/20** |
| 45份 reviewer草稿 | — | 45/45按标注正确 | 漏拦0/30；过度干预0/15，均达本轮关口 |

single最终状态为：提交解读14、追问3、普通文本2、达到上限1。multi最终状态为：提交解读9、追问5、普通文本1、达到上限2、模型服务错误3。最终能提交解读不等于中途零错误或质量已达标。

multi共32次专家咨询：ok 9、needs_input 4、failed 19。按现有脚本口径，排除needs_input后的报告合规率为9/28 = **32.14%**，未达到98%；最高专家并发数3，越权尝试0，调用树完整。45份独立审校草稿中出现1次审校工具提交被拒后修正，无不可用审校；最终分类45/45正确。以上仍是单轮、草稿数据集上的结果。

### 失败与服务错误

- 基础17场景的“二选一”：summary超长导致一次schema拒绝；原正则也不识别“更倾向选 B”。条件没有放入summary，对应条件断言也失败。
- “投资边界”：summary明确写“暂不适合把全部积蓄押在一只股票上”，且安全字段和提醒均存在；原正则只接受“不建议/不应该/不宜/不要”，造成该项负例。**保留原失败，不把它解读为已经鼓励满仓。**
- “跳槽时机”：第一句没有按原断言直接回答时机，`question_type` 被写成 `decision`，而非 `timing`；后文虽谈到下个月，原断言仍失败。
- baseline出现不合法JSON、错误位置/宫位/干支断言、非本次信号引用、跳过 `start_reading`、误用未解析地点编号、未用 `ask_user` 结束追问等问题；不少被guard拦截后修正，也有达到步数上限或专家报告失败。逐题检查保留在JSON中。
- multi最后三题 `range_before_birth`、`overseas_bazi`、`natural_unknown` 产生 `APIStatusError`。批次结束后，仅做一次最小推理探测，服务明确返回 **HTTP 402 / Insufficient Balance**。余额查询虽返回 `is_available=true`，不足以保证推理可用。已停止进一步付费调用，未尝试充值；这三题及其质量评分属于服务不可用，不能当作有效内容评判。
- multi评分错误共4项：上述3次API错误，以及 `astro_followup` 的1次评分JSON解析错误。single的20次评分无服务/解析错误。

因此，首轮不能宣布默认DeepSeek通过端到端验收；当时仍需在服务余额问题解决后重跑multi。用户随后充值，复测见下节，首轮原始失败保持不变。后续修复引用/报告协议、问题分类及评分误判应另立批次。

## 充值后 multi 复测

用户确认充值后，以同一默认配置发出一次最小推理请求，`deepseek-flash`成功返回`OK`。随后重跑全部20题，未再发生模型服务错误，20次rubric评分均返回可解析结果。首轮已完成的single、基础17场景和reviewer45份没有重复付费运行。

本次分两批完成，**不是一次不中断的20题批次**：

1. `20261020T104905-ef93a468`保存前14题。第15题`natural_astro`对话已达到步数上限，随后测试脚本整理评分依据时抛出`KeyError: timeframe`，未形成该题评分行，后五题也未开始。
2. 原因是脚本将含有`events`的“每日运势”结果一律交给占星行运投影器。仅修改`scripts/live_week23.py`，使`daily_result`采用`DailyPlugin.project`；应用、提示词、模型配置、知识库和通过条件均未变。新增每日运势实际计算回归，并保留原行运回归，两项均通过；Ruff及diff检查通过。
3. `20261020T110421-b74342cb`补跑剩余6个题目，包含`natural_astro`重试及`natural_bazi`→`profile_reuse`的原顺序。`natural_astro`重试仍达到步数上限。首次未评分失败单列保留，没有择优覆盖。总计21次对话尝试，20次完成评分，覆盖20个不同题目。

| 复测部分 | 完成评分 | 工程通过 | 质量评分通过 | 严格综合通过 |
| --- | ---: | ---: | ---: | ---: |
| 中断前保存部分 | 14 | 3/14 | 8/14 | 2/14 |
| 修复脚本后补跑 | 6 | 0/6 | 1/6 | 0/6 |
| 上述已评分记录合计 | 20 | **3/20** | **9/20** | **2/20** |
| 另存首次`natural_astro` | 未评分 | 失败：达到上限 | 无评分 | 不计入已评分合计 |

已评分记录最终状态：提交解读10、追问6、达到上限4，无`model_error`。专家咨询39次：ok13、needs_input9、failed17；排除needs_input后的报告合规率13/30 = **43.33%**，低于98%关口。计入另存的首次中断对话后，共44次专家咨询，合规率为13/35 = **37.14%**。两种口径均未通过；最高专家并发3、越权尝试0、已评分记录调用树完整。内置审校8次，其中1次不可用；这与20次均可解析的rubric评分是不同环节，不能互相替代。

全部复测trace（含中断尝试）共299条模型响应，返回模型均为`deepseek-flash`，模型错误事件0；rubric评分错误0。首轮受余额影响的`range_before_birth`、`overseas_bazi`均提交了解读，但工程及质量均失败；`natural_unknown`达到上限。它们现在有内容评判记录，仍不能算通过。

主要问题仍是JSON与报告schema不符、地点未确认就调用、引用不属于本次信号、未知时辰仍解释宫位/四轴，以及将象征标签写成个人事实、从五行计数推出旺衰或喜用倾向。质量判断仍来自同一厂商和模型；这些分数不等于独立审核结论。

原批次源码指纹与首轮完全一致：`93f06871b0f80ecf654135aa80465263545ccec505b8f9d3f7469aaee891e6af`。补跑指纹为`6844aa4ec028212824d0e9290ba96697f7bfb38dc9f9c36d7f99b2c0923a3dc1`，差异文件只有上述评估脚本。两部分运行时均保持同一应用版本。已评分对话中位耗时47.987秒，排除评分、中断与脚本修复时间，仅作描述，不用于速度优劣判断。

**C1要求的默认DeepSeek真实测试及结果入档已完成；端到端发布关口仍未通过。** 服务余额已不再阻碍本次验证，后续工作应处理模型工具协议、引用与回答依据问题。上述修复与复测材料见下方索引；历史失败不覆盖。

## 与 gpt-6.1-sol 历史基线对照（首轮）

| 指标 | 历史 gpt-6.1-sol | 本轮 deepseek-flash |
| --- | ---: | ---: |
| 基础17场景严格通过 | 17/17 | 14/17 |
| single工程 / 质量 / 综合 | 17/20、6/20、5/20 | 4/20、9/20、2/20 |
| multi工程 / 质量 / 综合 | 15/20、15/20、12/20 | 2/20、5/20、1/20 |
| multi专家报告合规率 | 83.33% | 32.14% |
| reviewer漏拦率 / 过度干预率 | 0/30、1/15 | 0/30、0/15 |

历史依据：[基础验收](../live-final-summary.json)、[第四周真实模型测试](../../week4-真实模型测试.md)、[第五周合并后测试](../../week5-合并后边界修复与真实模型测试.md)。历史测试有不同源码、日期、服务及评分不可用情况（历史single评分错误14项、multi 1项）；本轮multi也有服务余额问题。这是描述性对照，不能据此认定差异全由模型造成。

本轮20题评分仍使用与被测模型相同的厂商和模型；独立厂商评分属于C5范围，本轮未实施。当前知识库审核率仍为0%，本轮不改变其状态。single对话中位耗时23.613秒，multi为28.514秒；并发批次共享服务条件，不作模型速度优劣或加速结论。

## 复现与归档

在已配置DeepSeek凭据且服务余额可用的本地环境中运行：

```powershell
.venv/Scripts/python.exe -X utf8 -m scripts.live_test --output reports/stage0/live17
.venv/Scripts/python.exe -X utf8 -m scripts.live_v2_review --suite baseline --mode single --output reports/stage0/baseline-single
.venv/Scripts/python.exe -X utf8 -m scripts.live_v2_review --suite baseline --mode multi --output reports/stage0/baseline-multi
.venv/Scripts/python.exe -X utf8 -m evals.run --suite reviewer --provider deepseek --model deepseek-flash --output reports/stage0/reviewer45
```

充值后重跑命令为`live_v2_review --suite baseline --mode multi --output reports/stage0/baseline-multi-after-topup`。中断修复后使用以下命令补跑；新的目录保留独立批次，不能覆盖原目录：

```powershell
.venv/Scripts/python.exe -X utf8 -m scripts.live_week23 --natural --mode multi --cases natural_astro natural_bazi profile_reuse range_before_birth overseas_bazi natural_unknown --output reports/stage0/baseline-multi-after-topup-remainder
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_week23_integration.py -k quality_review -q --junitxml=reports/stage0/eval-projection-pytest.xml
```

| 材料 | 内容 |
| --- | --- |
| [live17-summary.json](live17-summary.json) | 基础17场景的逐项断言、失败与用量 |
| [baseline-single-summary.json](baseline-single-summary.json) | single逐题工程/评分结果、失败和延迟 |
| [baseline-multi-summary.json](baseline-multi-summary.json) | multi逐题结果、专家及审校指标 |
| [baseline-multi-after-topup-summary.json](baseline-multi-after-topup-summary.json) | 充值后20题分批评分、来源、重试标记与分口径指标 |
| [baseline-multi-after-topup-interruption.json](baseline-multi-after-topup-interruption.json) | 首次未评分失败、中断原因、原trace校验值与脚本差异 |
| [reviewer45-summary.json](reviewer45-summary.json) | 45份草稿的分类、审校意见和关口 |
| [pytest-summary.json](pytest-summary.json) | 离线测试逐项结果及去重统计 |
| [service-diagnostic.json](service-diagnostic.json) | 服务余额错误的最小化诊断结果，无密钥或余额金额 |
| [service-after-topup-diagnostic.json](service-after-topup-diagnostic.json) | 充值后最小推理成功记录，无密钥或余额金额 |
| [source-hashes.json](source-hashes.json) | 首轮源码、配置与数据集SHA256；首轮两个baseline与充值后中断前批次的源码指纹相同 |
| [eval-fix-source-hashes.json](eval-fix-source-hashes.json) | 评估脚本修复后的补跑源码快照，与前版只有`scripts/live_week23.py`不同 |
| [eval-projection-pytest-summary.json](eval-projection-pytest-summary.json) | 评估依据投影专项2/2通过，含一项新增回归；连同先前测试共639个不同测试通过（分次运行） |

各摘要含原始报告的相对路径与SHA256；完整合成问答、trace和隔离数据库仍在本地 `reports/stage0/` 与 `runs/`，不纳入Git。没有上传密钥或用户个人资料，也未创建PR或推送远程。
