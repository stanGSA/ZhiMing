# 知命 · 占卜 Agent Harness

2026-10-20 阶段0修复与DeepSeek回归已归档：日期/时区刷新、网页身份续期与到期清理、危机安全确认及按资料匹配热线已实现，离线验证通过。充值后服务恢复，multi分批覆盖20题，工程3/20、质量9/20、严格综合2/20通过；另保留一次评估中断及重试记录。端到端关口尚未通过，默认保持single。详见[阶段0验收](docs/verification/stage0/README.md)；独立复核后的修复见[阶段0复核修复](docs/verification/stage0/review-fixes.md)。

真实模型质量后续按[独立验收任务](docs/verification/real-model-quality-task.md)推进，保留上述失败基线；出生／咨询时区的工程修复不代表真实模型质量已经达标。

阶段1（知识库模型交叉审核与主题方向）：审核三态、账本与审核脚本已合并；占星落座落宫与八字十神的感情、财务方向初稿已补齐（全部仍是草稿），每日运势条目保持中性。两家模型的真实交叉审核尚未运行，知识库关口未通过。详见[阶段1验收](docs/verification/stage1/README.md)。

PR #5 合并后的日期恢复、解梦来源与输出检查、姓名歧义可见披露修复，见[第六周合并后五项修复](docs/week6-合并后五项修复.md)。

回答第一句先表态、前提放第二句，分层收紧为 2-3 层，正文不再向用户解释写作边界，见[回答先表态与精简](docs/回答先表态与精简.md)。

回答改为说白话：结论、小标题和建议不用术语，正文术语附白话解释，不讲起运折算等推算方法；模型写出的 `<br>` 自动换成换行，见[回答说白话](docs/回答说白话.md)。

回答改为分层解读：定调、分层分析（sections）、行动建议、收尾；依据作为附录，回复中只显示条数（`/evidence` 或网页面板查看）。校验改为事实层严格、表达层自动修正，见[分层解读与表达层放宽](docs/分层解读与表达层放宽.md)；评审整改与真实模型对照工具见[评审整改与验收](docs/分层解读-评审整改验收.md)。

当前已接入计划中的六个占术插件：塔罗、西方占星、八字，以及第六周新增的姓名五格、解梦和每日运势。第四周新增多 Agent 模式（编排者 + 体系专家并行，第六周起为五位专家）。第五周新增跨体系信号合并与张力检测、宽松审校 agent 和画像复用。第六周的两个确定性关口离线通过：笔画 200/200 与规则数据集一致、同日运势工具结果 10/10 一致；PR #5 评审指出的 8 项问题已修复（见 [第六周验收](docs/week6-验收报告.md)）。第四周已进行真实模型测试，但**整体关口尚未通过**；第五、六周的真实模型验收状态见各周报告，因此默认仍为单 Agent（`mode: single`）。第二周与第三周的确定性计算关口已通过；真实回答质量、工程检查和发布前人工审核分别记录。见 [第四周验收](docs/week4-验收报告.md)、[第五周验收](docs/week5-验收报告.md)。

第四周合并后真实专家状态恢复专项 7/7；同题单、多 Agent 工程检查分别为 17/20、15/20，专家最终报告合规率 83.33%，低于 98% 关口。见 [第四周真实模型测试](docs/week4-真实模型测试.md)与[原 PR 阶段验收](docs/week4-验收报告.md)。

第二周：11/11 参考盘通过，最大黄经误差 **0.000110364°**；Skyfield/JPL 独立交叉验证最大差 **0.000000611°**。第三周：**50/50 边界用例、57 个规则或追问变体通过**。占星280条、八字141条、塔罗163条均为原创草稿，覆盖率100%，人工审核率0%。详见 [第二周验收](docs/week2-验收报告.md)、[第三周验收](docs/week3-验收报告.md) 与 [联合测试证据](docs/verification/week23/README.md)。第一周原报告和原始失败记录保留。

[项目计划](docs/占卜Agent项目计划书.md) · [评估数据集说明](evals/README.md) · [脱敏验收材料](docs/verification/README.md)

当前配置使用 DeepSeek 官方 OpenAI 兼容接口、模型 `deepseek-flash`，显式关闭思考模式。凭据保存在本地 `.env` 的 `DEEPSEEK_API_KEY`，地址为 `https://api.deepseek.com`；不读取旧的 `OPENAI_API_KEY`。使用 `--provider demo` 可以切换到离线规则演示。离线测试数字不能代表真实模型的工具选择或解读质量。

## 快速开始（Windows PowerShell）

### 网页版

网页版提供聊天、出生信息填写、确定性排盘、结构化解读和历史回看，适配电脑和手机屏幕。综合问道采用宣纸松绿；八字采用暖金四柱命盘；占星采用深蓝星空与行星图；塔罗采用紫金牌阵，不同栏目有独立的引导和提问显示。

已有本地环境时运行：

```powershell
& .\.bootstrap\Scripts\uv.exe sync --locked --extra llm --extra web
& .\.venv\Scripts\python.exe web.py
```

打开 http://127.0.0.1:8765 。端口占用时可使用 `python web.py --port 8766`。首次安装先执行下方 `setup.ps1`，它会安装网页依赖并准备知识库。

- 默认使用 `config.yaml` 与 `.env` 中的模型配置，网页不接触密钥。页面底部可切换「离线排盘与塔罗演示」；八字和占星的基础排盘由现有历法与星历程序完成，不依赖模型调用，深度解读仍需真实模型。切换运行模式会开启新对话，保留已有解读。
- 出生地点通过国家/地区→省/州→城市→县/区联动选择，服务端从固定数据集取得坐标和时区。中国大陆包含 2,938 个县级行政区域；海外只展示实际收录层级，缺少区县时明确注明城市中心。数据来源、精度和范围见 [地点数据说明](common/region_data/README.md)。
- 填写公历生辰后可点击「排出我的八字」或「绘制本命星图」直接查看结果。八字显示四柱、日主、五行计数和大运；占星显示黄道经度示意、行星落座、上升与宫位。未知时辰不输出时柱或上升宫位；新疆要求选择出生钟表时间制，夏令时重叠等不确定情况保留追问。
- 出生资料随问题一起提供给 Agent，日期与时刻序列化为同一句话，以通过原有证据校验，不会绕开出生资料验证。塔罗不要求出生信息，可选择单张、三张或二选一牌阵。
- 解读区展示实际返回的定调、塔罗牌、分层分析、建议、时间线、收尾、依据和置信度，支持复制和继续追问。左侧足迹用于回看当前浏览器身份的历史解读。
- 当前是本机单进程版本，仅监听 `127.0.0.1`。同一浏览器刷新会恢复本轮对话，每次合法访问都会续期 12 小时。服务重启后会生成新身份，旧记录保留至原闲置期限；闲置到期后自动清除该身份的业务记录和应用 trace，不会关联到新身份。会话有效期间也可点击「清除我的记录」立即删除。尚未提供账号登录和跨设备同步。

网页接口与行政区测试（全部离线）：`& .\.venv\Scripts\python.exe -m pytest tests/test_web.py tests/test_regions.py -q`。

### 给朋友临时体验

安装 [Cloudflare Tunnel 客户端](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)，将 `cloudflared` 加入 PATH，或在 Windows 下将官方程序保存为 `.bootstrap/cloudflared.exe`。已有本地环境和知识库后运行：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m scripts.share_web
```

程序在本机 `8766` 端口启动独立的体验服务，申请随机 HTTPS 地址。链接、用户名 `friend` 和随机访问口令保存在本地 `reports/web-share/invitation.txt`，将这些信息发给朋友即可。浏览器会提示输入用户名和口令；页面、静态资源和 API 均需要验证。口令不放进网址或 Git，默认本机 `8765` 启动方式不变。没有新增调用次数或费用限额，真实解读使用分享者配置的模型和额度，原有会话容量与模型执行预算仍然有效。

电脑需要保持开机联网、避免休眠；隧道重启会生成新链接和口令。此方式用于临时体验，公网连通性取决于双方网络及隧道服务，启动提示后应从外网实际测试。出生资料与聊天记录保存在分享者电脑上，真实解读会发送相关内容到所配置的模型服务。当前没有账号和跨设备同步，重启后不会自动恢复旧浏览器身份。

在运行窗口按 Ctrl+C，或在另一个终端执行下面的命令，可同时关闭体验服务和隧道：

```powershell
& .\.venv\Scripts\python.exe -X utf8 -m scripts.share_web --stop
```

运行日志位于 `reports/web-share/`，目录已被 Git 忽略。分享相关离线测试：`& .\.venv\Scripts\python.exe -m pytest tests/test_web.py tests/test_web_share.py tests/test_regions.py -q`。

### 命令行与首次安装

在项目目录运行一次：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本将 uv 放在 `.bootstrap`、Python 3.11 放在 `.python-runtimes`、项目环境放在 `.venv`，不改变系统 Python。依赖版本通过 `uv.lock` 锁定。现在会下载并校验 Swiss 星历、JPL DE440s、GeoNames 和 Unihan 18.0 的三个单字段文件；不安装 embedding 或 PyTorch。

```powershell
$env:PYTHONUTF8 = '1'
& .\.venv\Scripts\python.exe cli.py draw --question '下个月适合跳槽吗？' --spread three_card --seed 42
& .\.venv\Scripts\python.exe cli.py draw --question 'A 公司还是 B 公司？' --spread decision --seed 42 --json-output
& .\.venv\Scripts\python.exe cli.py chat
```

固定 seed 只注入会话的首次抽牌，用于测试复现；不传 seed 时每个新 reading 使用系统随机种子。后续重抽始终生成新 seed，并记录 parent_reading_id；纯函数 draw_tarot 的相同 seed 仍能完全复现。同一次 reading 重复同参数抽牌返回缓存，改变参数再抽会被拒绝。

对话命令：`/profile` 查看画像，`/evidence` 查看上一份解读的完整依据（分层解读的回复只显示依据条数），`/new` 开始新问题，`/redraw` 明确重抽，`/forget` 删除当前用户数据，`/quit` 退出。询问“第二张牌具体什么意思？”会恢复原记录和原知识库版本，不重抽；结构化追问单独保存到 reading_responses，原解读保留。

Linux / 已安装 uv 的环境：`uv sync --locked --extra llm`，然后 `uv run python -m knowledge.build`、`uv run python cli.py chat`。

## 接入真实模型

复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`，即可使用当前 Flash 配置。其他 OpenAI 兼容服务需设置 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 并选择对应 provider；Anthropic 使用 `ANTHROPIC_API_KEY`。

```powershell
& .\.venv\Scripts\python.exe cli.py chat --provider deepseek --model deepseek-flash
& .\.venv\Scripts\python.exe cli.py chat --provider anthropic --model <你的模型名>
```

适配器统一 tool calling、消息历史与 token 统计，针对瞬态连接、限流和服务器错误最多尝试三次；当前单次超时90秒，可在config.yaml调整。SDK HTTP 协议有本地 MockTransport 测试；显式运行 `python -m scripts.live_test --model deepseek-flash` 执行17个严格场景，每次结果保存在 reports/review-fix/独立run_id，保留失败记录。任何工具错误使场景失败，并核对实际入库、种子与引用；同样记录接口返回的cached_tokens，缺失记为未知。自动化 pytest 强制离线，不会调用付费模型。

## 运行路径与约束

```mermaid
flowchart LR
    CLI --> Loop[Harness 主循环]
    Loop --> Model[Demo / OpenAI / Anthropic]
    Model --> Guard[权限 / 参数 / 依赖 / 幂等 / 引用校验]
    Guard --> Tools[公共工具 / 塔罗 / 占星 / 八字]
    Tools --> KB[只读知识库与不可变版本]
    Tools --> DB[业务库 WAL]
    Loop --> Trace[用户分目录 JSONL]
```

`harness/` 不引用领域插件、知识库或数据库。应用在 `app.py` 显式注册工具。塔罗计算使用版本化 SHA256 排序，不使用 Python 内建 `hash()`，可跨进程复现；抽出的牌不重复。种子由 harness 提供，模型不能换 seed 重抽。

工具错误作为结构化结果返给模型；模型故障、步数和 token 上限返回明确失败状态。计算后不能用普通文本绕过 `submit_reading`。同一批工具中终止工具后的调用不执行，但仍补齐工具响应，保持两家模型的协议完整。

基础工具：`start_reading`、`get_profile`、`update_profile`、`read_reading`、`lookup_meaning`、`draw_tarot`、`ask_user`、`submit_reading`。用户身份由会话注入，模型不能通过参数指定其他用户。画像写入检查原话证据与字段值，支持中文日期、时刻、性别及排盘口径规范化。

## 知识库与数据

- `knowledge/sources/tarot/cards.yaml`：78 张牌 × 正逆位 = 156 条，加 7 条牌位说明，共 163 条自写草稿。
- `knowledge/sources/astro/entries.yaml`：280条占星草稿；`knowledge/sources/bazi/entries.yaml`：141条八字草稿。两个体系规则独立版本化，组合组件引用随历史记录保存。两份文件由 `scripts/draft_week23.py` 生成；感情、财务方向按传统规则起草：七颗传统行星在庙旺落陷星座及第2、5、7、8宫的落点（占星60条），十神与柱位十神（八字50条，不分性别的简化），有方向的条目同时写明对应文字。外行星与其余落点保持无方向。
- `knowledge/rules/tarot.yaml`：信号时间属性与牌位强度规则。倾向值来自条目的 `theme_map`，信号由代码产生。
- `knowledge/rules/merge.yaml`：跨体系合并的阈值（方向阈值、张力与共振强度、权重区间），和其它规则一样计入知识库版本。
- `python -m knowledge.build`：检查 schema、id、key、同义词唯一性、许可、数值范围与完整覆盖；构建只读 SQLite 和覆盖率报告（按体系统计三级审核状态）。确定性说法（排除“不代表事件必然发生”等否定式免责声明）和塔罗正逆位同号等代码检查结果写入 `data/kb.checks.json`，作为待审队列，不使构建失败。
- `data/kb_versions/<版本>.sqlite`：保留不可变条目与规则快照。版本摘要同时包含源文件、规则与审核账本（`knowledge/reviews/`）；旧 reading 的查询使用旧快照，旧快照与旧记录里没有审核级别的条目和信号按 `reviewed` 读作草稿。
- **审核状态分三级：`draft`（草稿）、`model_reviewed`（经模型交叉审核，未经人工审核）、`human_reviewed`（人工审核）。** `reviewed` 只表示人工审核，任何代码与脚本都不写它；模型交叉审核记在 `knowledge/reviews/<体系>.yaml` 账本里，按条目内容哈希绑定，内容一改即回到草稿。解读的置信度按用到的最低级别设上限：草稿为 low，说明“释义未经审核”；经模型交叉审核最高 medium（阶段1待确认），说明“释义经模型交叉审核，未经人工审核”；人工审核不设上限。**当前 1171 条全部是草稿，人工审核率 0%，模型交叉审核率 0%，解读仍强制低置信度。** 知识库关口按《项目完善计划书》4.8 的模型交叉审核指标验收（`scripts/model_review_kb.py`），尚未运行真实审核。审核方不能与起草条目的模型同厂商：感情、财务方向由 Anthropic Claude 起草，`kb_review.drafter_vendors` 记为 `anthropic`，审核脚本据此拒绝 Anthropic 审核方。
- `data/app.db`：画像与历史版本、readings、reading_responses、daily，以及后续专家、审校和排盘缓存的表结构。当前启用画像、三体系reading与追问回答、专家报告、审校意见（review_notes）和chart_id/bazi_id缓存；readings 另存保存时的跨体系合并表（merge_json）。自动迁移至schema版本4，旧行与知识版本保留。
- `runs/<用户摘要>/<会话>.jsonl`：工具参数、结果、错误、时间和 token 使用量；模型异常只记录异常类别，避免 SDK 错误文本泄露凭据。
- `evals/cases/` 和 `evals/generators/` 从用户提供的评估数据集复制，保留原稿状态，不改参考答案。

SQLite FTS5 已构建并检查可用；第一周精确查找不依赖分词或向量检索。解梦意象另建字二元组 FTS5 表（`dream_fts`）做 BM25；jieba 分词与 sqlite-vec 向量检索尚未使用。`scripts/fetch_data.py` 支持 HTTPS、SHA256 校验、缓存与目录边界检查；清单已固定七项数据（第六周新增三个 Unihan 文件）的来源、许可、版本与SHA256。地名数据改用geonamescache 3.0.2发布归档中的GeoNames cities15000固定快照（只读取JSON，不安装或执行归档代码），固定URL与SHA256；旧快照仍保留本地。CI先下载并核验全部数据，再运行doctor和测试。

## 测试和验收

```powershell
& .\.venv\Scripts\python.exe -m scripts.doctor
& .\.venv\Scripts\python.exe -m scripts.doctor --api
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/week1-tests.xml
& .\.venv\Scripts\python.exe -m evals.run --suite week1
& .\.venv\Scripts\ruff.exe check harness agents common plugins knowledge memory signals scripts tests evals app.py cli.py
& .\.venv\Scripts\ruff.exe format --check harness agents common plugins knowledge memory signals scripts tests evals app.py cli.py
```

测试覆盖确定性抽牌、完整释义、知识库历史版本、权限与分区、依赖、画像证据、重复调用、输出引用和事实检查、预算、异常、追问、用户隔离、删除数据，以及两家 SDK 的 HTTP 协议。

`evals.run --suite week1` 只跑原 80 题中适用于已接入塔罗的 12 题，其余 68 题跳过；自动保留每题 trace。工具集合 F1 是离线演示模式的流程指标，原数据集仍需人工审核。报告输出到 `reports/week1-eval.md` 与 JSON。跨平台 GitHub Actions 配置已添加，运行结果以仓库 Actions 为准。本地生成的 reports/、runs/ 和 data/ 不纳入版本控制；随源码归档的脱敏汇总位于 docs/verification/。

## 隐私、当前限制和后续工作

用户数据落盘在本地；真实模型 API 会收到执行任务需要的对话、画像与工具结果。`/forget` 删除当前用户在应用数据库、trace 和内存中的数据，并压缩 SQLite；不能删除第三方模型服务留存、系统备份或已导出的报告。

网页身份 cookie 随每次通过认证及来源检查的访问续期，有效期为最后访问后12小时。持续使用不会因首次创建超过12小时换身份。闲置到期后自动删除该浏览器身份的画像、历史记录、排盘/每日缓存、专家报告、审校意见和应用 trace；服务在线时每分钟清理，并在请求前检查，忙碌请求结束后再清理。先删 trace、后删业务记录与清理期限；任一步失败会记录日志并保留期限，下一次清理重试，不影响其他请求和后台清理。清理期限保存在业务库中，重启后仍会执行；本版本尚不恢复重启前的浏览器会话，已失去会话映射的资料会在原期限到达时清理。升级前没有清理期限的 `web-` 用户记录，在新版本启动时补登，从首次启动起给予12小时宽限；只有 trace、没有业务记录的旧目录不在补登范围内。CLI 用户不受这项自动清理影响。数据库备份与手工导出的文件需另行处理。

每轮重新获取当前时刻，“今天/明天”优先按画像 `consultation_tz`，其次出生 `tz`，均无则按 `Asia/Shanghai` 解析；画像中无效的旧时区值会被跳过，不会中断对话，新写入的 `tz` 与 `consultation_tz` 都必须是有效 IANA 时区。日期基准同时传入编排者与专家。出生表单或原话中的“出生钟表时区”“出生时区”“出生采用北京时间”等描述只作为出生资料，不会覆盖已保存的咨询时区；明确说明当前居住地或本次按某地时间咨询时，才作为咨询时区证据。每日运势只按日历基准所用时区计算：用户在对话中说明了咨询时区、或出生时区只来自本轮解析的地点时，工具会先要求把该时区保存进画像，刷新日历后再按新的日期计算，不会出现“今天”按一个时区、运势按另一个时区算。

第一周的规则只能检查结构化引用、显式牌名与部分位置及方向事实，不能证明每一句自然语言都受引用支持。健康、法律、投资、生死问题有基础标注规则；识别到明确自伤表达会停止占卜。更完整的语义安全、事实支持与审校评估留到第五至七周。

当前支持原数据集中的五个危机场景及中途危机转折。隐晦的消失/永远睡去等表达先由同一模型分类，分类失败则暂停占卜并确认安全。危机状态在同一会话中保留；继续索要占卜、CLI `/new`、网页新对话或直接排盘均不能跳过确认。用户需按回复中的提示单独确认当前安全、没有自伤/伤人打算且未受到威胁；确认语忽略全半角、空格、外围引号与句末标点，但附加请求或其他内容仍不会解除暂停。确认轮只回应支持，下一轮才可恢复咨询。危机状态只保存在当前进程的会话中：服务或 CLI 重启、浏览器换新身份后不会保留。网页先在入口做一次安全检查，同一条消息不会再交给模型重复分类。

危机联系方式按已填写的咨询时区、出生时区选择；网页尚未保存画像时也读取出生地点表单。当前配置大陆12356、110/120和美国988、911；均以“若你目前在该地区”为前提。未知或未配置地区使用通用当地紧急服务提示，不根据中文或默认日历时区猜地区。来源与2026-10-20核实记录见[热线核实](docs/verification/stage0/hotlines.md)；12356各地服务时间可能不同，不承诺24小时接通。

抽牌直接返回版本固定的精确释义，新解读通常3轮模型调用，原牌追问2轮。完整信号仍保存到SQLite与trace，给模型传递精简工具结果；已完成轮次的工具JSON从后续对话上下文移除，跨会话从数据库恢复。稳定系统提示与工具结构保持前缀稳定，缓存是否命中以接口usage为准。

第二周已接入本命盘和行运，第三周已接入八字，第四周已实现多 Agent 编排，第五周已实现交叉合并与审校，第六周已接入姓名、解梦与每日运势（第四周真实模型已测试，整体关口未通过；第五、六周验收状态见各周报告）；第七周完整评估。当前不把后续能力声明为已实现。

## 第四周：多 Agent 模式

`config.yaml` 的 `mode` 可选 `single` 或 `multi`，命令行用 `--mode` 覆盖：

```powershell
& .\.venv\Scripts\python.exe cli.py chat --mode multi
& .\.venv\Scripts\python.exe cli.py draw --question 'A 公司还是 B 公司？' --spread decision --mode multi --provider demo
```

- **分工**：编排者负责读画像、解析地点、选择专家、合并追问和写最终回答，自己不能调用任何排盘或抽牌工具。占星、八字、塔罗专家各在隔离子会话中只用本插件工具和本分区释义，用 `submit_report` 返回结构化报告（answer、带 ref_id 的 points、missing、confidence）。信号由 harness 从计算结果附加，专家改不了。
- **并行**：编排者在同一步发出的多个 `consult_specialist` 并发执行（上限 `max_parallel_specialists`），结果按调用顺序并入当前记录。readings 和 specialist_reports 只由编排者写入。
- **约束**：
  - 编排者写的子问题不算用户原话，出生资料仍按用户原话核验；
  - 专家需要补充资料时由编排者统一追问，追问结果不缓存；
  - 专家超时、异常或预算用尽时返回失败报告，最终回答不能把该体系列入 `systems_used`，必须在置信度说明里写明缺少哪个体系；
  - 同一体系重试失败时保留仍有效的报告（标记 `retained_previous`）。新解读提交前核对专家所依赖的画像字段快照，出生资料等依赖更正后必须重新咨询所有受影响的专家；只更新姓名不使排盘失效。成功报告按体系原子替换信号、引用和计算事实，历史记录追问继续使用原快照；
  - 塔罗在同一记录内只抽一次：抽牌成功即在当前会话保留牌面和牌阵，随后报告失败、请求取消或超时都不能换牌阵重抽。连续重试沿用原计算快照；未提交的会话状态不提供进程重启恢复。见[合并后状态恢复修复](docs/week4-合并后状态恢复修复.md)；
  - `read_reading` 恢复历史记录时同时恢复该记录的专家报告，不带入当前记录的状态；
  - 追问原记录不再咨询专家。
- **预算**：一次请求一个预算（`request_token_budget`），编排者与专家共享；每位专家另有 `specialist_token_budget`、`specialist_timeout_s`、`specialist_max_steps`。当前数值是初值，需按真实运行重新标定。
  - 多 Agent 模式采用准入控制：每次模型调用前按输入估算加 2048 输出额度预占，并发专家不能合计超出剩余额度，也不能占用 `orchestrator_reserve_tokens`；返回后按实际用量结算。这是软上限：实际用量超过估算的部分记为 `budget_overrun`，只有这部分超额可能挤占保留额度。单 Agent 模式不做估算，与前三周相同。
  - 多 Agent 模式的 `request_timeout_s` 是整次请求的墙钟上限：等待中的模型调用、专家执行与排队、异步工具都在到期时取消，到期后返回的响应不执行工具，结果为 `timeout`。排盘等同步计算不能中途打断，算完后才响应取消。单 Agent 模式不加墙钟上限。
- **trace**：子会话写各自的 JSONL，带 `parent_session_id` 和 `parent_call_id`，创建即记 `session_started`，正常、超时或取消都记 `session_finished`；父会话记录 `specialist_queued`、`specialist_started`（获得并发许可后）和 `specialist_finished`。`python -m scripts.trace_tree --user <用户> --reading <记录>` 重建调用树并检查完整性。
- **评估**：
  - `python -m evals.run --suite week1 --mode multi` 是 demo 模型的离线流程回放；
  - `python -m scripts.live_v2_review --suite baseline --mode multi` 用真实模型串行跑 20 题，结果附带专家越权、报告合规率（≥98% 关口口径）、首次通过率、修正后通过率、实际并发度、排队时间和调用树完整性。指标口径见 [第四周验收](docs/week4-验收报告.md)，原始完整批次、评审服务错误和独立复评见[真实模型测试](docs/week4-真实模型测试.md)，不拼接通过率。


## 第五周：交叉解读与审校

- **信号合并（`signals/merge.py`）**：
  - 先按 horizon 分组，再按主题合并；不同 horizon 不互相抵消。
  - 每个体系在组内按 strength 加权求平均倾向；`theme_map` 里的 0 表示“无方向”，不参与平均。
  - 两体系方向相反、且两边同向信号强度都 ≥ `tension_strength` 时记为张力；至少两个体系同向记为共振。
  - timing 信号按实际时刻区间求交集再比较：节气流月在节气当刻换月，行运按当天，不按“11 月”这类标签对齐。
  - 同一主题、同一组方向是一条张力（编号如 `tension:timing:career:astro+/bazi-`），下面列出所有窗口；方向反过来的日期是另一条。
  - 相邻窗口合并时，数值按时长加权，每段原值保留在 `segments`。
  - 画像里的 `system_weights`（如 `{"bazi": 1.5}`）只改变综合倾向，不改变是否存在张力。
  - 权重必须有原话支持：原话按分句判断，每个体系只看提到它的分句，否定说法（“不更信八字”）不支持任何调整。
- **张力披露（多 Agent 模式，代码检查）**：
  - 编排者用 `merge_signals` 查看合并表。
  - `submit_reading` 时，表里每条张力都必须写进 `tensions`：主题对得上，两边体系都要提到，还要有 `how_to_read`。同一主题在不同日期方向相反时，还要写出各自的日期。缺了直接打回，并列出未披露的张力和日期。
  - 合并表随 reading 存入 `merge_json`。追问时 `read_reading` 把它固定为会话快照，`merge_signals` 只返回快照，不按当前权重或规则重算；追问回答也不能丢掉原记录的张力。
  - 单 Agent 模式只保存合并表、不强制披露，作为对照基线。
- **宽松审校（`agents/reviewer.py`，只在多 Agent 模式）**：
  - **自动运行**：`submit_reading` 通过代码校验后，自动交给隔离子会话里的审校，编排者无法跳过。
  - **输入**：审校只看用户原问题、草稿和代码算出的张力/共振表。
  - **结论**：三档，即 `pass`、`pass_with_notes`（不触发重写）、`revise`。`revise` 只能以答非所问、隐瞒张力或安全越界为理由，并须逐字引用草稿原句。
  - **轮次上限**：最多一轮 `revise`，编排者改一次后直接发出。
  - **代码兜底**：要求加免责声明或“措辞更谨慎”的 `revise` 会被拒绝，这类 notes 被丢弃并计数。审校不能要求删掉对问题的回答；没有张力时不能以隐瞒张力打回。
  - **失败放行**：审校超时、出错或预算不足时放行，记为 `unavailable`。
  - **记录**：审校意见写入 `review_notes`，trace 中是 reading 下的子会话。
  - **配置**：`reviewer.strictness` 可设为 `lenient`、`strict` 或 `off`（对照实验用）；`models.reviewer` 可换更小的模型。
  - **追问**：追问不重新审校。
- **画像复用**：
  - 画像已有性别、出生日期或出生地时，`ask_user` 不能再问这些。例外是本轮有工具要求补充资料，或用户正在更正。
  - 跨会话回访用 `start_reading(parent_reading_id=...)` 关联本用户的旧记录，并返回旧结论、时间范围和张力，供对比。
- **评估**：
  - `python -m evals.run --suite reviewer --provider deepseek` 用 `reviewer_drafts.yaml` 45 份草稿测漏拦率（≤10%）和过度干预率（≤5%）。
  - `--provider demo` 是离线关键词基线，只验证流水线，不是关口结果。
  - 多 Agent 真实模型运行的结果附带审校打回率等指标（`scripts.trace_tree.reviewer_metrics`）。

## 第六周：姓名、解梦与每日运势

- **姓名五格（`plugins/name/`，工具 `analyze_name`）**：
  - 笔画：Unicode Unihan 18.0（`kRSUnicode`、`kTraditionalVariant`、`kTotalStrokes`，由 `scripts/fetch_data.py` 按固定提交与 SHA256 下载到 `data/unihan/`）。先取繁体字形（姓氏有繁体惯例覆盖），再按“部首原字笔画 + 余笔”计康熙笔画，氵按水 4 画、艹按艸 6 画、左阝按阜 8 画等由部首号自动体现；数字一至十按数值计。
  - 五格：天格（单姓加假数 1，复姓两字相加）、人格、地格（单名加假数 1）、外格 = 天格 + 地格 − 人格、总格；数理超过 81 减 80。三才按天人地格尾数定五行。常见复姓自动识别，“欧阳子涵”不能被拆成“欧 / 阳子涵”。
  - 写法有歧义的字（杰 / 傑、强 / 強、郁 / 鬱、肖 / 蕭 等 9 个）返回默认写法、备选笔画与 `confirmation_prompts`。只要计算结果里有未确认的写法，回答就必须在实际显示的文字中将各字形与笔画逐一配对、说明默认方案并请用户确认；工具生成的确认文案可直接放入 advice，只写在隐藏的 confidence.reason 不算披露。用户确认后用 `forms` 传入。复姓“万俟”保留“万”（3 画），单姓“万”默认“萬”（15 画）。Unihan 查不到的字返回 needs_input，不猜笔画。
  - 五格、三才和笔画陈述按姓名绑定：evidence 按 ref 对应到具体名字，正文按前面最近写出的全名对应；同时分析两个名字时，没有写明是哪个名字的格数会被打回，不能串用另一个名字的数值。
  - 姓名必须来自用户原话或画像 `name`。用户要求结合八字时传入本记录的 `bazi_id`，把三才五行与原局五行计数放在一起分析；补益五行属传统推断，须说明依据，不作命运断言。
  - 信号只有 `trait`，强度上限 0.35，低于八字和本命盘。天格来自姓氏，不单独产生倾向。起名、合婚属第二阶段。
- **解梦（`plugins/dream/`，工具 `lookup_dream_symbols`）**：
  - 知识库 355 条意象（覆盖 `dream_annotations.yaml` 的 89 个种子意象），每条带同义词；数据集里用作“词典外”探针的无人机、外卖、直播等刻意不收录。
  - 模型从梦境描述抽出意象后调用工具，每项带用户原文的连续片段（`phrase`）和规范意象（`symbol`）。片段必须逐字来自用户描述；规范意象必须由片段写出，或是片段的受控缩写（“牙齿一颗一颗掉下来”→掉牙），词典外的词须照抄原文，“手机”不能报成“飞机”。匹配顺序：同义词表精确命中 → 包含匹配（已知意象须位于短语末尾，例如“大狗”→狗，而“地铁闸机”不算地铁）→ FTS5 BM25（中文按字二元组索引）取候选、Dice 相似度 ≥ 0.75 才接受。向量检索兜底尚未启用（没有安装 embedding 模型），低于阈值一律记为未命中。
  - 代码检查覆盖所有对外文字（含 timeline）：未命中的意象只能说明“未收录、不解读”，该说明只豁免对应意象，不能豁免同句中的其他解读；任何作为解读对象的知识库意象（“梦见X”“X象征/代表/意味……”“「X」”，带不带引号都一样）必须是本次命中的；不能把梦说成预兆或预言（“不预示”“不代表”这类否定说法允许）；只用解梦的回答不写 timeline。
  - 信号只进入 `psyche`，合并时不与时机或运势信号互相抵消。
- **每日运势（`plugins/daily/`，工具 `daily_fortune`）**：
  - 不设专家，编排者直接调用一次；在代码里组合三个插件：当天月亮、太阳、水星、金星、火星对本命行星的精确相位，流日干支与日主的十神和冲合，以及每日一牌（种子为 SHA256(用户编号, 日期) 的前 8 字节）。
  - 结果写入 `data/app.db` 的 `daily` 表，主键 (user_id, date)。同一用户同一天再问直接读缓存，工具返回的计算数据逐字节不变，同时保留当时的知识库版本；出生资料更正后才重新计算。模型据此写的文字不保证逐字相同。
  - 日期必须与用户所问一致（今天、明天、后天或明确日期，按 Asia/Shanghai 日历基准）。本次提问以来的所有用户消息都算：出生资料里的日期（“我出生于1996-05-10”或等于画像生日）不算咨询日期；只补充出生资料不会改变已问的日期，用户明确说新日期才改变；不存在的日期（如 2026-02-30）返回可恢复的校验错误。目标日期保存在本记录的 `daily_target_date`。一周及以上按时机题处理。缺出生资料返回 needs_input。
  - 牌名与正逆位、流日干支和相位分别由塔罗、八字、占星的输出检查核对；每日一牌和普通抽牌一起进入正逆位检查，所有对外文字都查，追问恢复记录后同样适用。幸运色只能说是流日天干五行的传统配色约定。
- **多 Agent**：新增姓名、解梦两位专家，各自只看本插件工具和本分区释义。结合八字看名字时，编排者先咨询八字专家，再咨询姓名专家；姓名专家继承本记录的 `bazi_id`。
- **评估**：
  - `python -m evals.run --suite week6`：200 字笔画、37 个公认姓氏、五格手算样例、每日运势跨会话 10 次一致与同 seed 抽牌 100 次一致、三个新分区的覆盖率，以及解梦词典的离线扫描基线。
  - `python -m evals.run --suite trajectory`：标注路线回放扩展到全部 80 题（含 H_dream 历史）。它不是模型自主选工具的 F1。
  - `python -m scripts.review_week6_datasets`：记录 19 个待定稿字的处理，并对解梦数据集做结构审核（不是人工审核）。

## Week2 / Week3 用法与计算约定

在 `cli.py chat` 中提供合成资料，例如“公历1993-08-17 23:20，北京出生，男性；按23点换日、不用真太阳时，用八字说明日主、起运日期和首步大运”。时机题请给明确区间，例如“2026-11-01至2026-11-30，用占星和八字分析求职安排”。CLI 的 demo 模式仍是塔罗规则演示；三体系自然语言对话需真实模型，确定性计算测试完全离线。

新增工具：`resolve_location`、`compute_natal_chart`、`compute_transits`、`compute_bazi`、`compute_bazi_period`。先解析地点，再凭chart_id/bazi_id计算流期；同名城市、缺少出生资料、农历闰月、DST重复时间均追问。乌鲁木齐等新疆地点须确认北京时间或新疆时间。已有原局可跨会话复用；记录与缓存绑定当前用户。

- 占星：地心视位置、日期回归黄道；TT算行星、UT1算宫位。Placidus无定义时回退Porphyry。未知时辰用中午代理，宫位与四轴为null；月亮和行运精确日期需保留时间不确定性。
- 星历支持1800–2399；独立DE440s覆盖1849–2150，本次独立验收仅声称11个参考盘。行运支持最多3660天，输出精确相位过零/接触事件、残差与允许容许度；不是“任意时刻仍在容许度内”的逐日列表。给模型最多12条事件，完整计算保留本地，明确省略数量。
- 八字验收日期1900–2100：IANA消除夏令时后转固定UTC+8；开启真太阳时再做经度与均时差修正。立春换年、十二节换月依据物理时刻；日时遵循`next_day`（23点换日）或`same_day`（0点换日）。已有画像中的这两个开关可以复用。
- 起运默认沿用参考集的lunar_python getYun流派1及civil修正钟表口径，三天折一年、时辰差折算月日；不同流派可能相差数月。真太阳时钟表跨节气时要求确认`dayun_time_basis=physical`（物理时刻起运）或暂不排大运，不静默改变顺逆。工具返回明确口径。未知时辰不排精确大运，缺性别不排大运；程序不计算喜用神，解读可据月令与五行分布推断喜用倾向并说明依据。
- 流期支持年/月/日；年最多3660天，月/日最多366天。按实际立春、节气与日界分段。日期结束日包含，带时刻的结束点为半开区间。十神与原局冲合刑害破、三合三会是符号关系，不等同于必然事件。
- 占星信号按容许度与速度确定强度；组合释义及所有组件引用固定于知识版本。八字按十神、柱位、冲合规则产出信号。人工审核率0%，仍未达到发布前≥95%审核门槛。

当前 DeepSeek 使用 `llm.system_role: system`，三个角色均为 `deepseek-flash` 非思考模式，单次输出上限分别为8192、4096、2048 token。`model_options` 按角色覆盖 `llm.deepseek` 设置，角色使用独立客户端。适配器保留各轮 `reasoning_content`，trace只记录思考用量和结束原因；输出截断时停止，不执行不完整工具调用。可运行 `python -m scripts.check_model` 核对当前配置。服务返回名称单独记录，不能证明底层模型身份。三体系单轮预算180000个返回usage token、最多12步，超限明确失败；多 Agent 模式下该预算由编排者和专家共享。

## Week2 / Week3 可复现验收

```powershell
$env:PYTHONUTF8 = '1'
& .\.bootstrap\Scripts\uv.exe sync --locked --extra llm
& .\.venv\Scripts\python.exe -m scripts.fetch_data
& .\.venv\Scripts\python.exe -m knowledge.build
& .\.venv\Scripts\python.exe -m scripts.doctor --api
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=reports/week23/pytest-final.xml
& .\.venv\Scripts\python.exe -m scripts.verify_week23
& .\.venv\Scripts\python.exe -m evals.run --suite week1 --output reports/week23/week1-regression
& .\.venv\Scripts\python.exe -m evals.run --suite trajectory --output reports/week23/offline
& .\.venv\Scripts\python.exe -m scripts.live_test --model gpt-6.1-sol --output reports/week23/week1-live
& .\.venv\Scripts\python.exe -m scripts.live_week23
& .\.venv\Scripts\ruff.exe check harness agents common plugins knowledge memory signals scripts tests evals app.py cli.py
& .\.venv\Scripts\ruff.exe format --check harness agents common plugins knowledge memory signals scripts tests evals app.py cli.py
& .\.bootstrap\Scripts\uv.exe build --out-dir reports/week23/dist
& .\.venv\Scripts\python.exe -m scripts.archive_week23
```

真实测试会产生服务调用与费用，原始记录仅在已忽略目录。`live_week23`逐条检查正面作答、时间范围、计算及引用支持、事实编造，评审也使用同一请求模型；不是独立人工审核。`trajectory`只对当前适用的50题做标注路线集成回放，30题因后续工具或解梦历史跳过，不能当作真实模型工具选择F1。没有执行的全80题真实轨迹、完整30题安全集、独立人工万年历抽查和发布审核均不声明通过。


## PR #1 整改

[复核修订的缺陷分析](docs/week1-3-缺陷分析.md)和[整改清单](docs/pr1-整改清单.md)分别记录问题与当前状态。中文日期支持规范化，性别画像使用male/female；新问题区间不再混入出生日期。海外八字需确认日时口径，海外行运需确认咨询时区，后者可保存为consultation_tz。插件负责自身输出事实校验，Signal.horizon统一为trait/timing/moment/psyche并兼容读取旧值。新释义仍为草稿，人审0%；新增感情/财务主题为中性占位，不能当作已审核的领域倾向。行运仍定义为精确事件，orb表示解释容许度而非持续窗口筛选。

```powershell
uv run python -m pytest -q
uv run python -m scripts.verify_week23 --output reports/pr1-remediation/computations.json
uv run python -m scripts.live_week23 --natural --output reports/pr1-remediation/live
uv run python -m scripts.live_pr1
```

真实测试将保存源文件哈希、原始失败和每题问答，报告区分工程与回答质量；服务返回模型名只作元数据。原始JSON/trace在本地忽略目录，不作为GitHub可下载附件。

2026-10-13本地整改结果：确定性回归216/216、占星11/11、八字50例57变体通过；真实完整批次从12/20改善至17/20。重复题四项回答质量10/10、严格综合8/10；另三题复测严格1/3，分别保留而不拼接。详见[整改验收与复现](docs/pr1-整改验收.md)及[真实模型逐题记录](reports/live-gpt-6.1-sol-pr1.md)。占星时机自动评审服务错误、模型工具误调用和评审不一致仍有记录；人工审核率0%；v2（abb5c17）的[Windows和Ubuntu CI均已通过](https://github.com/stanGSA/ZhiMing/actions/runs/38379814078)，不能将数值通过写成全部验收通过。

v2截图复评后的本地修复见[逐项验收](docs/v2-截图整改验收.md)。工具追问不再缓存；确认口径后可用相同参数继续，且口径更正会使依赖原话的缓存失效。咨询时区可说“我现在住在洛杉矶”或“按洛杉矶时间”，先解析地点后保存复用。支持“下下个月”“下午3点一刻”，不会把“8点多”当精确时刻；“长沙”可通过“湖南省”消歧。最终确定性回归257项通过。原20题串行时延基准用`uv run python -m scripts.live_v2_review --suite baseline`运行，截图专项用`--suite screenshots`运行；逐题回答、质量和用量见[本轮真实测试记录](reports/live-gpt-6.1-sol-v2-fixes.md)。本轮新修改尚未推送，其远程CI结果不与v2混用。

真实专项经修复复测由5/9提升至严格7/9，最终四项回答质量9/9；两次模型工具误用在恢复后仍计为失败。20题串行基准为16/20、对话中位数64.551秒，早于最后的提示与评审上下文优化；最终9题为另一源码批次，不拼接通过率，也不声称最终源码已重跑全部20题。所有原始失败与分阶段用量保留。
