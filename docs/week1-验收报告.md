# 第一周搭建与验收

日期：2026-10-13（Asia/Shanghai）

第一周工程及评审修复已完成，最新结果与门禁证据以 [评审修复报告](week1-评审修复报告.md) 为准。旧脚本的“9/9”因断言不足撤回作为验收结论，保留以下历史记录供对照。知识释义尚未经人工审核，仍然使用低置信度。

## 交付范围

| 计划工作 | 实现与状态 |
|---|---|
| 环境搭建 | Python 3.11.17、项目隔离环境、uv.lock、setup.ps1 一键搭建，脚本复跑通过 |
| 模型适配 | OpenAI 兼容接口与 Anthropic SDK，统一工具调用、消息历史、token 统计、瞬态错误重试与资源关闭 |
| 主循环 | 异步工具执行，结构化错误反馈，终止工具处理，步数及 token 上限；计算后须经过提交校验 |
| 工具注册与插件接口 | 通用 Registry / Tool，Pydantic 输入 schema，独立 TarotPlugin，harness 不导入应用层 |
| Guard | 参数、角色权限、知识分区、前置画像、依赖归属、重复缓存、单次抽牌、原话证据、输出引用与基础事实校验 |
| Trace | 用户分目录 JSONL，session / parent_session / reading 标识，调用参数、结果、错误、耗时与 token |
| 业务库 | SQLite WAL，画像及版本历史、reading；专家报告、审校、daily 和排盘缓存预建表 |
| 塔罗插件 | 78 张牌，正逆位；单张、三张、A/B 决策牌阵；版本化确定性抽牌及代码生成信号 |
| 知识库 | 156 个牌面状态 + 7 个牌位，共163条；精确查找与同义词，完整覆盖检查，不可变历史快照 |
| 数据下载与自检 | HTTPS / SHA256 / 缓存 / 路径边界检查；第一周外部数据清单为空；doctor 必需项全通过 |
| 中文 CLI | 单次 JSON 输出、多轮对话、原牌追问、/new、/redraw、/profile、/forget、/quit |
| 评估与 CI | 导入原有数据集，第一周离线评估 runner，Windows / Linux CI 配置；远程 CI 未执行 |

## 实测结果

| 检查 | 结果 | 说明 |
|---|---|---|
| 自动化测试 | 最新85/85通过 | 原始65项结果保留；新增回归见reports/review-fix-tests.xml |
| 第一周轨迹用例 | 12/12 通过 | 原80题中的塔罗适用用例；另外68题跳过 |
| 离线工具集合 F1 | 1.000 | demo 模式的流程指标，不是实际 LLM 的调度成绩 |
| 塔罗知识覆盖 | 100% | 156牌面状态及7牌位，无缺条目 |
| 固定 seed | 通过 | 三种牌阵各重复100次、跨进程复现及固定向量检查 |
| 代码规范与格式 | 通过 | Ruff check 与 format --check |
| 一键搭建脚本 | 通过 | 锁定依赖同步、建库、数据清单、自检均成功 |
| CLI 多轮冒烟测试 | 通过 | 抽牌→第二张牌追问→/forget→退出 |
| SDK 适配协议 | 通过 | 本地 HTTP MockTransport 验证两家 SDK，没有外部网络推理 |
| 真实 API 调用 | 使用新的17场景严格验收 | 结果见评审修复报告；历史9/9宽松计分已撤回；Anthropic未做远程验收 |
| 人工条目审核率 | 0% | 全部如实保留 reviewed=false，强制低置信度 |

测试还覆盖无效引用、未抽出牌面、错误方向、编造干支和行星位置、专家越权、跨分区请求、画像证据不符、依赖归属、重复抽牌、预算耗尽、模型异常脱敏、历史知识库不变、用户隔离及删除数据。

原评估数据集的 `draft_needs_review` 状态得到保留。计算型星盘、八字和姓名用例要等对应插件实现后再执行；没有把跳过项计为通过。

## 复现命令

```powershell
$env:PYTHONUTF8 = '1'
powershell -ExecutionPolicy Bypass -File .\setup.ps1
& .\.venv\Scripts\python.exe cli.py draw --question '下个月适合跳槽吗？' --spread three_card --seed 42
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/week1-tests.xml
& .\.venv\Scripts\python.exe -m evals.run --suite week1
& .\.venv\Scripts\ruff.exe check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
& .\.venv\Scripts\ruff.exe format --check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
```

本机已配置用户提供的 OpenAI 兼容连接，默认模型为 `gpt-6.1-sol`。密钥只存本地 `.env`，不纳入 Git。`--provider demo` 可以切换为离线演示。

## 旧版 gpt-6.1-sol 测试历史（不作为当前门禁结论）

服务模型列表返回 `gpt-6.1-sol`，验收期间的响应模型标识也均为 `gpt-6.1-sol`。

旧脚本曾把三张牌、同会话追问、跨会话追问、明确重抽、单张牌、二选一、投资边界、画像原话写入，以及本地危机中止检查计为通过。评审确认：跨会话追问未持久化、固定seed重抽不独立，不能依据当时的9/9判定验收通过。

跨会话追问曾因缺少 `active_reading_id` 被Guard拦截，最终文本还暴露内部保存错误。新实现恢复原记录全部依赖，并将追问保存到reading_responses；任何工具错误现在都使测试失败。原始trace与旧报告保持不变。

验收脚本报告的输入 token 为 219390、输出 token 为 4797；这组数字只统计脚本的9个场景，不包含之前单独进行的三张牌连通测试。真实三张牌耗时33.617秒、单张29.739秒、二选一44.725秒。固定seed仍控制牌面随机性，模型解释来自实际服务。

原始数据与响应见 `reports/live-gpt-6.1-sol.json`、`reports/live-gpt-6.1-sol.md`，每个场景关联自己的 JSONL trace。复现命令：

```powershell
& .\.venv\Scripts\python.exe -m scripts.live_test --model gpt-6.1-sol
```

密钥检查覆盖 Git 管理文件、报告与 trace，未发现凭据泄漏。pytest 夹具强制离线运行，避免默认模型配置引发意外的外部 API 调用。

## 已修复的环境问题及剩余边界

- 系统现有 uv Python 管理目录不完整，改用项目自己的 `.python-runtimes`，未替换系统 Python。
- Windows 不允许重命名仍被 SQLite 连接占用的文件，知识库构建现在显式关闭连接再替换。
- 系统已有 pytest 临时目录存在访问问题，测试改用项目内每次新建的目录，不修改系统目录权限。
- 原评估生成器保持原样，尚未接入的生成器不纳入第一周代码格式验收。

自然语言事实与安全校验目前是基础规则，不能证明所有解释都受引用支持；第五周仍需语义审校，第七周仍需真实模型质量评估。当前功能是工程原型，尚未达到计划要求的 ≥95% 人工释义审核发布标准。
