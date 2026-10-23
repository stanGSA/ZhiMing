# 使用指南

本文由 2026-10-23 之前的 README 拆出，命令以 Windows PowerShell 为主；Linux / macOS 的等价命令见 [README](../README.md#快速开始)。文中数字为当时记录，当前状态以 README 为准。

## 快速开始（Windows PowerShell）

### 网页版

网页版提供入口页、问道首页和六个功能页，适配电脑和手机屏幕，每一页按其主题单独设计：入口为玄金罗盘，问道为千里江山青绿，八字为朱漆描金四柱，星盘为天文台星图，塔罗为暗紫鎏金拱顶牌，姓名为碑拓金石与五格剖象图，解梦为月雾与梦笺，运势为今日黄历。各页地址为 `/ask`、`/bazi`、`/astro`、`/tarot`、`/name`、`/dream`、`/daily`；设计与验证见[网页界面改版](web-ui-改版.md)。

已有本地环境时运行：

```powershell
& .\.bootstrap\Scripts\uv.exe sync --locked --extra llm --extra web
& .\.venv\Scripts\python.exe web.py
```

打开 http://127.0.0.1:8765 。端口占用时可使用 `python web.py --port 8766`。首次安装先执行下方 `setup.ps1`，它会安装网页依赖并准备知识库。

- 默认使用 `config.yaml` 与 `.env` 中的模型配置，网页不接触密钥。入口页可选「入内」（真实模型）或「离线演示」，各页底部也可切换。八字、星盘的排盘，姓名的康熙笔画与五格，以及运势页的流日干支与十神，都由程序直接计算，不依赖模型；深度解读仍需真实模型。离线演示只抽塔罗，解梦、姓名与运势的解读会提示切换真实模型，不会用牌面代答。切换运行模式会开启新对话，保留已有解读。
- 出生地点通过国家/地区→省/州→城市→县/区联动选择，服务端从固定数据集取得坐标和时区。中国大陆包含 2,938 个县级行政区域；海外只展示实际收录层级，缺少区县时明确注明城市中心。数据来源、精度和范围见 [地点数据说明](../common/region_data/README.md)。
- 填写公历生辰后可点击「排出我的八字」或「绘制本命星图」直接查看结果。八字显示四柱牌匾（十神、藏干、纳音）、日主、五行计数和大运；星盘显示按上升定向的本命盘、宫位、相位线与行星度数表。未知时辰不输出时柱、上升或宫位；新疆要求选择出生钟表时间制，夏令时重叠等不确定情况保留追问。生辰保存一次，各页共用。
- 出生资料随问答、八字、星盘与运势的问题一起提供给 Agent，日期与时刻序列化为同一句话，以通过原有证据校验，不会绕开出生资料验证。塔罗、解梦与姓名不发送出生资料；塔罗可选择单张、三张或二选一牌阵。
- 解读区展示实际返回的定调、分层分析、建议、时间线、收尾、依据和置信度，支持复制和继续追问。塔罗页以拱顶牌面展示抽出的牌，解梦页列出识别到的意象与未收录词，运势页在详解后显示每日一牌与行运相位。页眉「足迹」用于回看当前浏览器身份的历史解读。
- 当前是本机单进程版本，仅监听 `127.0.0.1`。同一浏览器刷新会恢复本轮对话，每次合法访问都会续期 12 小时。服务重启后会生成新身份，旧记录保留至原闲置期限；闲置到期后自动清除该身份的业务记录和应用 trace，不会关联到新身份。会话有效期间也可点击「清除我的记录」立即删除。入口页的账号登录标注为筹备中，尚未提供账号登录和跨设备同步；会话仍在时访问 `/` 会直接回到问道首页。

网页接口与行政区测试（全部离线）：`& .\.venv\Scripts\python.exe -m pytest tests/web/test_web_api.py tests/runtime/test_regions.py -q`。塔罗页的浏览器回归测试 `tests/web/test_web_browser.py` 需要先执行一次 `uv run playwright install chromium`，未安装浏览器时自动跳过。

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

运行日志位于 `reports/web-share/`，目录已被 Git 忽略。分享相关离线测试：`& .\.venv\Scripts\python.exe -m pytest tests/web/test_web_api.py tests/web/test_web_share.py tests/runtime/test_regions.py -q`。

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

## 隐私、当前限制和后续工作

用户数据落盘在本地；真实模型 API 会收到执行任务需要的对话、画像与工具结果。`/forget` 删除当前用户在应用数据库、trace 和内存中的数据，并压缩 SQLite；不能删除第三方模型服务留存、系统备份或已导出的报告。

网页身份 cookie 随每次通过认证及来源检查的访问续期，有效期为最后访问后12小时。持续使用不会因首次创建超过12小时换身份。闲置到期后自动删除该浏览器身份的画像、历史记录、排盘/每日缓存、专家报告、审校意见和应用 trace；服务在线时每分钟清理，并在请求前检查，忙碌请求结束后再清理。先删 trace、后删业务记录与清理期限；任一步失败会记录日志并保留期限，下一次清理重试，不影响其他请求和后台清理。清理期限保存在业务库中，重启后仍会执行；本版本尚不恢复重启前的浏览器会话，已失去会话映射的资料会在原期限到达时清理。升级前没有清理期限的 `web-` 用户记录，在新版本启动时补登，从首次启动起给予12小时宽限；只有 trace、没有业务记录的旧目录不在补登范围内。CLI 用户不受这项自动清理影响。数据库备份与手工导出的文件需另行处理。

每轮重新获取当前时刻，“今天/明天”优先按画像 `consultation_tz`，其次出生 `tz`，均无则按 `Asia/Shanghai` 解析；画像中无效的旧时区值会被跳过，不会中断对话，新写入的 `tz` 与 `consultation_tz` 都必须是有效 IANA 时区。日期基准同时传入编排者与专家。出生表单或原话中的“出生钟表时区”“出生时区”“出生采用北京时间”等描述只作为出生资料，不会覆盖已保存的咨询时区；明确说明当前居住地或本次按某地时间咨询时，才作为咨询时区证据。每日运势只按日历基准所用时区计算：用户在对话中说明了咨询时区、或出生时区只来自本轮解析的地点时，工具会先要求把该时区保存进画像，刷新日历后再按新的日期计算，不会出现“今天”按一个时区、运势按另一个时区算。

第一周的规则只能检查结构化引用、显式牌名与部分位置及方向事实，不能证明每一句自然语言都受引用支持。健康、法律、投资、生死问题有基础标注规则；识别到明确自伤表达会停止占卜。更完整的语义安全、事实支持与审校评估留到第五至七周。

当前支持原数据集中的五个危机场景及中途危机转折。隐晦的消失/永远睡去等表达先由同一模型分类，分类失败则暂停占卜并确认安全。危机状态在同一会话中保留；继续索要占卜、CLI `/new`、网页新对话或直接排盘均不能跳过确认。用户需按回复中的提示单独确认当前安全、没有自伤/伤人打算且未受到威胁；确认语忽略全半角、空格、外围引号与句末标点，但附加请求或其他内容仍不会解除暂停。确认轮只回应支持，下一轮才可恢复咨询。危机状态只保存在当前进程的会话中：服务或 CLI 重启、浏览器换新身份后不会保留。网页先在入口做一次安全检查，同一条消息不会再交给模型重复分类。

危机联系方式按已填写的咨询时区、出生时区选择；网页尚未保存画像时也读取出生地点表单。当前配置大陆12356、110/120和美国988、911；均以“若你目前在该地区”为前提。未知或未配置地区使用通用当地紧急服务提示，不根据中文或默认日历时区猜地区。来源与2026-10-20核实记录见[热线核实](verification/stage0/hotlines.md)；12356各地服务时间可能不同，不承诺24小时接通。

抽牌直接返回版本固定的精确释义，新解读通常3轮模型调用，原牌追问2轮。完整信号仍保存到SQLite与trace，给模型传递精简工具结果；已完成轮次的工具JSON从后续对话上下文移除，跨会话从数据库恢复。稳定系统提示与工具结构保持前缀稳定，缓存是否命中以接口usage为准。

第二周已接入本命盘和行运，第三周已接入八字，第四周已实现多 Agent 编排，第五周已实现交叉合并与审校，第六周已接入姓名、解梦与每日运势（第四周真实模型已测试，整体关口未通过；第五、六周验收状态见各周报告）；第七周完整评估。当前不把后续能力声明为已实现。
