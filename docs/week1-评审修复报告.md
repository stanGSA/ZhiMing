# 第一周评审修复与复测报告

日期：2026-10-13。仓库归档的是脱敏汇总；原始报告、trace和数据库仅保存在本地。已落实用户提供的《第一周测试评审.md》，工程门禁通过；知识释义仍未人工审核，尚不满足上线审核标准。

## 最终结果

| 检查 | 实测结果 | 证据 |
|---|---|---|
| 自动化回归 | 85/85通过；比原65项新增20项 | [JUnit](verification/pytest-summary.json) |
| 原第一周离线轨迹 | 12/12通过，其余68题属于后续体系 | [离线报告](verification/offline-summary.json) |
| gpt-6.1-sol严格测试 | 17/17通过，零工具错误；10个场景调用真实模型，7个危机场景由应用拦截 | [场景汇总](verification/README.md) · [断言汇总](verification/live-final-summary.json) |
| 门禁与trace重放 | 所有门禁通过，23次工具调用重放通过 | [门禁](verification/gate-summary.json) · [回放汇总](verification/gate-summary.json) |
| 知识覆盖 | 156牌面状态+7牌位=163条，覆盖100%，审核率0% | [build、自检、SQLite/API证据](verification/gate-summary.json) |
| Ruff与Git差异空白检查 | check、format --check、diff --check通过 | 按README命令可复现 |
| 凭据检查 | 工作文件、报告与trace未发现真实密钥，.env不纳入Git | [归档范围说明](verification/README.md) |

## 对照评审落实的改动

1. **种子与重抽**：生产原本已有随机默认值，问题来自旧测试给所有会话注入42。新真实测试不注入固定seed；显式fixture只控制首次抽牌。每次新记录/重抽使用secrets.randbits，记录seed并核对parent_reading_id。纯函数固定seed仍可复现。100次独立生产抽牌和不同seed分布均通过，分布指标见[分布汇总](verification/gate-summary.json)。
2. **追问持久化**：read_reading恢复原reading、seed、牌面、信号、facts、引用范围和原KB版本。submit_reading将追问单独保存到新增reading_responses，保留原结论；同会话/跨会话均复用原记录，无start或draw。原记录归属检查、追问用户隔离与forget删除均通过。已有SQLite自动增建表，实际9张业务表，schema版本2。
3. **严格断言**：每题保存原问题、全部命名断言、seed、reading/parent/response标识、结构化输出及trace路径。任何工具错误或模型失败都会判失败，即使最终文本看似可用；核对实际数据库值，不能只检查有文字。用户明确指定牌阵时，start返回requested_spread且Guard禁止替换。
4. **正面回答与呈现**：决策第一句须明确A/B暂定倾向与现实前提；跳槽时机第一句须直接回应下个月是否适合。提示词要求围绕用户问题解释牌面并给可执行步骤。内部审核原因仍保存在confidence.reason，正常正文只显示低置信度；无高风险时隐藏多余safety说明。免责声明只由渲染层添加一次，正文包含内部保存错误或重复免责声明会被拦截。
5. **调用与上下文**：抽牌直接返回版本固定的精确释义，通常start→draw→submit三轮；原牌追问read→submit两轮。给模型传递精简结果，完整信号保留在DB/trace；完成轮次的工具JSON从后续上下文移除，原牌从数据库恢复。稳定系统提示与工具结构维持稳定前缀，按服务usage记录缓存命中，缺失记为未知，没有新增假定第三方支持的缓存参数。
6. **危机路由**：补齐原数据集5个危机场景和mt-11；消失/永远睡去等隐晦表达先用同一个gpt-6.1-sol分类，不调用占卜工具，分类失败则暂停并确认安全。回复询问是否安全、联系可信的人、当地紧急服务并继续支持。safety.region默认空，可配置CN/US及真实紧急渠道，不把中文等同于中国大陆。
7. **画像原话**：问题确为“我叫测试林晓。请只保存我的姓名，其他信息先不填写。”预期值为“测试林晓”，已核对证据为连续原话、只写name、其他字段不填。没有错误删去姓名中的“测试”。
8. **门禁证据**：包括build覆盖、三种牌阵同seed各重复100次、不同seed与100次独立生产分布、重复draw拦截/依赖/伪造画像证据回归、逐次trace重放、实际表结构/完整性，以及Python3.11.17、SQLite3.53.1/FTS5、IANA时区与API200自检。发现Windows缺少时区数据后添加并锁定tzdata2026.5，验证1988年上海夏令时UTC+9/冬季UTC+8。星历、Swiss Ephemeris、GeoNames、Unihan、embedding属后续周，仍如实显示未安装。

## 是否正面回答用户的问题

以下为最终真实响应的首句，完整依据与建议已在本地逐条核对，仓库只保存[脱敏验收摘要](verification/README.md)：

> 跳槽：下个月有条件适合跳槽：先确认新岗位能改善负担与管理方式，拿到书面录用并核实薪酬、职责后再辞职。

> A/B选择：暂更倾向B，前提是新岗位能满足你的真实需求；A的成本是继续处理协作问题，B则需承担适应成本。

> 全仓投资：不建议把全部积蓄买入一只股票。先保留应急和必要支出资金，再评估可承受的投资金额与分散方案。

同会话和跨会话追问均直接解释原第二张“星币六逆位”，位置为现在；原seed、牌面和结论一致，追问各自入库，没有暴露内部错误。

## 性能实测

最终17场景统计：输入146431、输出4483 token，共25轮有响应的模型调用。接口已知报告的cached_input_tokens合计85888；部分响应未提供该字段，此总数仅统计已报告部分。

按与旧测试相同的8个真实模型场景对照，输入从219390降至124652，减少43.2%。两个新增真实模型场景是跳槽时机和隐晦危机分类，未混入该同比。调用轮数和输入减少，不保证每题延迟都降低。

| 场景 | 旧模型轮数/秒 | 新模型轮数/秒 |
|---|---|---|
| 三张牌 | 4/33.617 | 3/29.651 |
| 同会话追问 | 3/25.864 | 2/23.468 |
| 跨会话追问 | 4/36.346 | 2/21.566 |
| 单张牌 | 4/29.739 | 3/18.943 |
| 二选一 | 4/44.725 | 3/48.853 |
| 投资边界 | 4/34.959 | 3/44.781 |

## 失败记录与复测

旧“9/9”结论已撤回：跨会话追问没有保存结构化回答，固定42重抽没有独立随机性，旧断言漏检。旧JSON/trace保持原样供复核。

本次第一轮严格测试为15/17：[失败结果](verification/live-initial-summary.json)。投资题指定三张却被模型改成decision；跳槽题提交阶段APITimeoutError，未形成解读。补上显式牌阵约束与提示，并将可配置单次超时从30秒调整为90秒后，完整复测17/17。第一轮证据包正确判为[门禁失败](verification/gate-summary.json)，最终证据包通过；没有覆写失败或降低通过标准。

本次两轮测试返回usage合计输入285806、输出8624 token。统计只包含实际返回的usage，不计算服务未返回usage的超时请求；费用取决于第三方计费。

## 复现

```powershell
$env:PYTHONUTF8 = '1'
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/review-fix-tests.xml
& .\.venv\Scripts\python.exe -m evals.run --suite week1 --output reports/review-fix-offline
& .\.venv\Scripts\python.exe -m scripts.doctor --api
& .\.venv\Scripts\python.exe -m scripts.live_test --model gpt-6.1-sol
$taskLiveReport = Get-ChildItem -LiteralPath .\reports\review-fix -Filter live.json -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
& .\.venv\Scripts\python.exe -m scripts.gate_evidence --live $taskLiveReport --api
```

新的live_test每次生成独立run_id；上述命令选择最新live.json进行门禁回放。API凭据从本地.env读取，报告不包含密钥。

## 当前边界

第一周工程门禁通过不等于发布标准通过：163条释义的人工审核率仍为0%，要求≥95%的人工审核尚待完成。语义事实支持与危机识别仍是有限样本和基础规则/分类器验证；未运行全体系80题或全部30条安全题。服务返回模型标识全部为gpt-6.1-sol，但不能独立核验第三方底层模型。远程CI、Anthropic远程调用和后续体系尚未验收。
