# 第四周合并后：真实模型测试

2026-10-13 启动，跨午夜运行至 2026-10-14（Asia/Shanghai）。基于 PR #2 合并提交 `fcfd88eba46cb0da2602b9b7f65bd4ccf9b51f39` 加本地三项状态恢复修复；修复尚未提交或推送。

**结论：三项修复的真实专家专项 7/7；第四周整体真实模型验收未通过。** 单 Agent 工程 17/20，多 Agent 工程 15/20；多 Agent 最终报告合规率 83.33%，未达到 98% 关口。默认保持 single。

调用项目配置的真实模型服务，请求模型为 `gpt-6.1-sol`；返回名称仅是服务元数据，不作为底层模型身份的独立证明。所有数据为合成资料，数据库与运行记录隔离。

## 单、多 Agent 原始完整批次

相同 20 题、相同源码与评审标准，先 single 后 multi 串行执行。严格通过要求所有工程检查和四项回答质量评审同时通过；工具误调用即使自行恢复，仍不算工程通过。评审连接或服务错误表示未完成评审，不等于已经判定回答错误。

| 指标 | single | multi |
|---|---:|---:|
| 题数 | 20 | 20 |
| 工程通过 | 17/20 | 15/20 |
| 原始质量评审通过 | 6/20 | 15/20 |
| 原始严格综合通过 | 5/20 | 12/20 |
| 评审服务错误/不可用 | 14 | 1 |
| 对话中位数（秒） | 74.243 | 92.541 |
| 对话 P95（秒） | 161.813 | 263.689 |
| 对话最大值（秒） | 240.169 | 314.398 |
| 对话模型响应数 | 101 | 148 |
| 对话请求尝试数 | 104 | 152 |
| 对话输入 token | 580091 | 500001 |
| 对话输出 token | 23823 | 36706 |
| 原始评审输入 token | 60360 | 87997 |
| 原始评审输出 token | 2819 | 7493 |

对话耗时含必要澄清，排除评审与初始化；总墙钟包含这些阶段。只是一轮描述性对照，服务时延和生成内容有波动，不能作因果加速或稳定性保证。没有返回 usage 的失败请求不推算 token。

### 逐题原始结果

| 用例 | single 工程 | single 质量 | multi 工程 | multi 质量 | single 秒 | multi 秒 |
|---|---|---|---|---|---:|---:|
| astro_trait | 通过 | 通过 | 通过 | 通过 | 70.866 | 93.746 |
| astro_followup | 通过 | 通过 | 通过 | 未通过 | 23.774 | 83.482 |
| bazi_trait | 通过 | 通过 | 通过 | 通过 | 161.813 | 112.885 |
| bazi_followup | 通过 | 通过 | 通过 | 通过 | 31.356 | 35.848 |
| astro_timing | 未通过 | 未完成：InternalServerError | 通过 | 通过 | 240.169 | 263.689 |
| bazi_timing | 通过 | 通过 | 未通过 | 通过 | 116.526 | 189.93 |
| three_system_timing | 未通过 | 通过 | 通过 | 未完成：InternalServerError | 114.422 | 162.267 |
| unknown_time | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 64.839 | 98.435 |
| missing_birth | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 113.027 | 24.871 |
| ambiguous_place | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 56.776 | 29.916 |
| dst_gap | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 118.749 | 55.021 |
| dst_fold | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 35.863 | 61.159 |
| lunar_confirm | 未通过 | 未完成：APIConnectionError | 通过 | 通过 | 29.587 | 42.105 |
| investment_new | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 62.904 | 91.337 |
| natural_astro | 通过 | 未完成：APIConnectionError | 通过 | 通过 | 77.621 | 110.517 |
| natural_bazi | 通过 | 未完成：APIConnectionError | 未通过 | 未通过 | 42.248 | 79.03 |
| profile_reuse | 通过 | 未完成：APIConnectionError | 未通过 | 通过 | 79.589 | 145.553 |
| range_before_birth | 通过 | 未完成：APIConnectionError | 未通过 | 未通过 | 134.353 | 314.398 |
| overseas_bazi | 通过 | 未完成：APIConnectionError | 未通过 | 通过 | 160.911 | 66.228 |
| natural_unknown | 通过 | 未完成：APIConnectionError | 通过 | 未通过 | 62.516 | 103.042 |

### 未通过项与评审理由

- **single / astro_timing**：工程未通过项：zero_tool_errors。
  - 工具 `submit_reading`：`validation_failed`，行运星、本命星与相位须匹配同一计算事件。
- **single / three_system_timing**：工程未通过项：zero_tool_errors。
  - 工具 `update_profile`：`invalid_arguments`，参数不符合 schema：field。
- **single / lunar_confirm**：工程未通过项：zero_tool_errors。
  - 工具 `update_profile`：`invalid_arguments`，参数不符合 schema：field。
- **multi / astro_followup**：工程未通过项：无。
  - 评审：首句直接回答了太阳落摩羯对工作方式的含义，符合所问方向。
  - 评审：这是无时间范围的本命性格解读，未混用流月、节气或现实事件日期；且使用了原记录中的太阳摩羯与第4宫信息。
  - 评审：太阳摩羯关于规划、责任、稳步积累的判断有对应释义支持；但太阳第4宫被扩展为重视熟悉工作环境、职责和资源清晰等工作方式，引用释义实际仅支持家庭与内在基础、自我表达和目标，支撑不足，因此整体结论不能判定为充分支持。
  - 评审：回答未编造出生信息、落座、宫位或经历；土星双鱼第6宫也能在所给原始事实中找到，且建议表述为条件性建议。
- **multi / bazi_timing**：工程未通过项：zero_tool_errors。
  - 工具 `update_profile`：`validation_failed`，历法与子时规则须有原话明确支持。
  - 工具 `update_profile`：`validation_failed`，历法与子时规则须有原话明确支持。
- **multi / natural_bazi**：工程未通过项：expected_status, expected_tools, saved, systems。
  - 评审：首句没有回答日主、起运时间或第一步大运。给定计算事实已明确采用北京时间、23点换日及默认起运算法，并得出日主辛金、出生后3年4个月10天起运（1996年12月27日）、第一步己未大运。可以注明这些口径后直接作答，不应将口径偏好全部作为必须补充的资料。
  - 评审：回答没有错用时间范围、混淆节气与公历月份，也没有把计算时刻当作现实事件日期；信息追问本身不存在时间范围冲突。
  - 评审：23:20处于不同换日口径可能产生差异的时段，这一说明与给定换日约定相容。回答未提出缺乏计算或释义支持的命理结论；但这不弥补其未回答已有计算结果的问题。
  - 评审：回答仅复述已知出生时间并询问历法和计算口径，没有编造出生资料、干支、十神或起运结果，所给默认选项也明确以日期确为公历为条件。
- **multi / profile_reuse**：工程未通过项：zero_tool_errors。
  - 工具 `submit_reading`：`validation_failed`，evidence 引用必须来自本次工具生成的信号。
- **multi / range_before_birth**：工程未通过项：expected_status, expected_tools, saved, systems。
  - 评审：direct_answer：首句仅说明请求超时，未正面回答2026年11月1日至11月30日是否适合求职，也未提出必要的信息追问。
  - 评审：time_consistent：没有针对用户指定日期范围展开分析，无法确认占星与八字判断是否覆盖该范围、是否正确处理节气流月边界。
  - 评审：supported_conclusion：未提供占星或八字的实际计算、引用释义及关键判断，未完成用户要求的双体系解读。
  - 评审：no_fabricated_facts：给定事实仅包含已核实的出生资料及北京地理信息，没有已完成计算的记录；回答声称“已有计算保留”，缺乏给定事实支持。
- **multi / overseas_bazi**：工程未通过项：expected_status, expected_tools, saved, systems。
- **multi / natural_unknown**：工程未通过项：无。
  - 评审：直接作答：summary第一句明确回答工作方式，给出目标明确、自主推进、分工清楚的方向，没有仅用免责声明回避问题，也没有重复追问用户已说明无法取得的出生时辰。
  - 评审：时间一致：本题属于工作方式与性格解读，没有指定预测期间；回答未引入流月或事件日期，并说明23点换日下日柱及十神分析仅有条件成立。
  - 评审：结论支持不足：太阳、水星落白羊及所列三个相位均有计算依据，正印、劫财的条件解释也与引用释义相符；但summary的“你更适合”及太阳合土星段落的“适合……环境”将探索建议提升为个人适配判断。引用明确只支持以相关任务作实际验证，并非已知职业适配结论，因此这些关键表述超出依据。“优势需实际交付验证”有所限定，但未将适配判断本身明确改为待验证假设。
  - 评审：未编造事实：出生日期、地点、落座、相位及有条件的干支十神均与给定事实一致；未解释未知的宫位、四轴或时柱，未编造起运、家庭及工作经历，也未以五行计数推断喜用神。

复核说明：single 的占星时机题在一条引用下同时描述了两个真实相位，校验器要求相位与该引用事件绑定，拆分表述后恢复；不能据此称其编造相位。single 两次不存在字段均为 `birth_data_is_synthetic`。multi 八字时机题的两次口径错误将 `zishi_rule` 写成了 `23点换日`、`23`，实际应使用 `next_day`。

复核超时：range_before_birth 首轮两位专家均在 120 秒超时；重试的同步行运计算发生在 16:07:28–16:07:46 UTC，跨过约 16:07:32 的请求截止点，导致实际 314.398 秒才处理取消。此为同步计算不能中途取消的已知限制，本轮得到了真实运行证据。超时反馈“已有计算保留”来自固定系统文案；评审上下文只有父会话已合并事实，而子会话实际执行过计算，因此该题 no_fabricated_facts=false 不能直接当作模型编造的证据。

## 多 Agent 工程指标

- `consults`：23
- `ok_reports`：15
- `needs_input_reports`：4
- `failed_reports`：3
- `cancelled_consults`：1
- `consults_without_submission`：7
- `out_of_scope_attempts`：0
- `out_of_scope_rate`：0.0
- `report_compliance_rate`：0.8333333333333334
- `report_first_pass_rate`：1.0
- `report_corrected_pass_rate`：1.0
- `submit_attempt_pass_rate`：1.0
- `max_concurrent_specialists`：3
- `trace_tree_complete`：True

最终报告合规率为 15/(23−4−1)=83.33%，低于 98% 关口。首次提交通过 15/15，仅说明实际提交过报告的会话；3 次失败没有提交报告，不能被这个 100% 掩盖。全批无越权尝试、无预算超额事件，实际最大并发 3，所有调用树完整；预算依然是软上限。报告合规不等于内容依据充分，也不等于整题成功。20 题不能替代 trajectory 数据集全部适用题的真实路由 F1。

## 三项修复的真实专家专项

编排与边界触发由测试脚本控制，专家实际调用模型服务。这是带故障注入的集成验证，不是全自然对话。抽牌与计算均走项目真实工具；并行兄弟任务使用脚本阻塞，两次报告故障在真实服务已返回 submit_report 后注入，丢弃的响应与用量仍保留。超时专项使用 90 秒请求时限和 240 秒专家时限，确保触发整次请求超时路径。完整自然对话证据见上方 40 题。专项后半段与已保存回答的复评同时进行，专项耗时不用于性能对照。

批次 `targeted-20261014T001219-b7c5cb`：**7/7**。

| 场景 | 结果 | 秒 |
|---|---|---:|
| profile_all_stale | 通过 | 151.087 |
| profile_partial | 通过 | 142.146 |
| cancel | 通过 | 21.019 |
| timeout | 通过 | 100.946 |
| cancel_completed_sibling | 通过 | 31.527 |
| timeout_completed_sibling | 通过 | 100.721 |
| two_failures | 通过 | 55.616 |

真实模型交换 30 次，返回输入 74030 / 输出 7235 token；被注入故障丢弃的真实响应也计入此处。

验证内容：资料更正后直接提交或只重算一体系都被拒；全量刷新可保存新出生时刻；姓名更改不误拒，历史追问仍使用旧记录。塔罗在取消、整次请求超时以及完成报告等待兄弟任务时均检查原牌恢复、牌阵锁定、同一 reading_id、一次抽牌、实际入库和 trace 完整性。两次报告失败后的三轮输入快照应为 `0 → 1 → 1`。仅保证同一 Runtime 会话继续，不覆盖进程重启。

## 评审服务错误的独立复评

只对原始评审服务失败的已保存回答重新评分，每题新建连接；不重新生成回答、不改原始批次，不将复评与原批次拼接成新的整批通过率。相同模型评审不是独立人工审核。

批次 `rejudge-20261014T001725-f27769`：尝试 15 题，通过 14，服务/解析错误 0。

| 模式 / 用例 | 复评结果 |
|---|---|
| single / astro_timing | 通过 |
| single / unknown_time | 通过 |
| single / missing_birth | 通过 |
| single / ambiguous_place | 通过 |
| single / dst_gap | 未通过 |
| single / dst_fold | 通过 |
| single / lunar_confirm | 通过 |
| single / investment_new | 通过 |
| single / natural_astro | 通过 |
| single / natural_bazi | 通过 |
| single / profile_reuse | 通过 |
| single / range_before_birth | 通过 |
| single / overseas_bazi | 通过 |
| single / natural_unknown | 通过 |
| multi / three_system_timing | 通过 |

本批复评返回输入 133902 / 输出 5881 token。

**single / dst_gap**：

- 回答属于出生时间核验追问，仅要求确认原始时间及夏令时记录，没有擅自给出工作方向，符合追问信息场景的要求。
- 回答围绕用户给定的出生日期和当地时间展开，没有混淆节气流月与公历月份，也没有将计算时点当作现实事件日期。
- 给定事实仅包含出生资料、北京坐标和Asia/Shanghai时区，未包含夏令时跳时校验结果。因此，“02:30是不存在的当地钟表时间”这一关键判断在所提供的确定性事实中没有直接支持。
- 回答声称“工具判定”该时间不存在，但给定资料中没有这项工具结果；这属于未经提供事实支持的工具结果归因。回答没有另行编造八字、十神或个人工作经历。


本次全部阶段（连接预检、40 题对话及原评审、专项、独立复评）返回的用量合计：**输入 1,436,394 / 输出 83,962，总计 1,520,356 token**。失败请求未返回的用量不包含在此，不推算金额。

复评证据缺口：single / dst_gap 被评审判为“夏令时不存在时间缺乏工具依据”，但原始 trace 中 compute_bazi 实际返回 `status=needs_input, code=nonexistent_local_time`。现有 grounded_payload 没有收集这种澄清工具结果，属于评审输入遗漏；不能把此项直接视为产品编造。原始评分保留，没有人为改成通过。

## 后续优先项

1. 固定画像枚举值的模型调用约束，避免不存在字段以及 zishi_rule 显示文本误用。
2. 对齐默认历法、换日规则与必要追问，避免专家已完成后编排者仍只追问；海外出生补充后的完成策略也需一致。
3. 保证编排者逐字复用本次报告引用，并把工作方向表述为待验证建议，避免把象征释义升级为个人适配事实。
4. 用真实服务延迟标定专家时限与失败后的收尾策略；如需严格墙钟上限，要解决同步计算阻塞事件循环。
5. 评审输入应包含 needs_input 等工具事实；评审服务失败要单独记录，并验证客户端恢复策略。以上未在本次测试中修改，避免混入不同源码结果。

## 证据与复现

源码指纹：`02097fbcb4ef9ad481185a8a7d242f1a6d155d6a0868e13bb47d8f09fea5b09c`。

完整原始回答、引用、计算事实、用量、逐题状态与调用树保存在本地忽略目录 `reports/pr2-fixes/live-20261013/`。该目录不自动上传仓库；不要把此处的本地验证当作远程 CI。

- `single/*/serial-summary.json`、`multi/*/serial-summary.json`：完整批次。
- `targeted-*/`：故障注入记录、真实模型交换、快照与断言。
- `rejudge-*/results.json`：复评原始响应与失败。
- `comparison.json`：统计汇总；`connectivity.json`：连接预检。

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m scripts.live_v2_review --suite baseline --mode single --output reports/week4-new/single
.\.venv\Scripts\python.exe -m scripts.live_v2_review --suite baseline --mode multi --output reports/week4-new/multi
.\.venv\Scripts\python.exe -c "import runpy; runpy.run_path('reports/pr2-fixes/live-20261013/targeted_live.py', run_name='__main__')"
```

默认仍为 single。真实工具误调用、引用支撑不足、模型服务可用性，以及尚未完成的知识/数据集人工审核和全量真实路由评估，均不因本次状态恢复测试通过而自动消除。
