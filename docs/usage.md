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
- 问答、八字、星盘与运势使用本次出生表单快照：程序同步画像并绑定计算输入；模型省略参数时采用当前表单，显式传入旧日期、地点或口径会被拒绝。未知时辰不沿用旧时刻，未选地点不沿用旧地点。出生资料仍作为用户证据提供，不绕开原有验证。塔罗、解梦与姓名不发送出生资料；塔罗可选择单张、三张或二选一牌阵。
- 各功能分别保存对话、未完成解读、排盘、执行锁和进度流；塔罗未完成时可继续使用八字。切换模型模式或「开启新对话」仅重置当前功能。出生档案和历史解读仍共用；修改生辰会失效已有页面排盘。「清除我的记录」删除所有功能的数据，任一功能正在处理时须先等待结束。危机确认状态仍跨功能保留。
- 出生资料具有独立版本：修改生辰后，依赖旧生辰的当前解读、计算上下文和缓存一并失效，旧对话标注为「旧生辰记录」；历史解读保留原始资料，可继续基于原记录追问。八字、星盘、运势或综合咨询正在处理时，须等本轮结束再改生辰；其他功能仍可使用相同生辰，独立塔罗任务不阻止改档。综合咨询尚未完成的塔罗牌面会保留。
- 多个标签页共享生辰。其他页面修改后，无草稿的表单会自动同步；有未提交修改时保留草稿，可选择「载入最新生辰」或「保留本页修改并重新确认」。过期表单提交会提示冲突，不会覆盖新资料。浏览器不支持标签页通知时，返回页面会检查资料版本。
- 解读区展示实际返回的定调、分层分析、建议、时间线、收尾、依据和置信度，支持复制和继续追问。塔罗页以拱顶牌面展示抽出的牌，解梦页列出识别到的意象与未收录词，运势页在详解后显示每日一牌与行运相位。页眉「足迹」可回看原解读及「历次追问」；点击「继续这份解读」后，问题绑定该历史记录，使用原牌面、计算和知识库版本，不重新计算。仅打开历史记录不改变当前对话。
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

## MCP server：确定性插件

排盘、流期、抽牌、姓名五格、解梦意象匹配、每日运势和释义查询也包成了 [MCP](https://modelcontextprotocol.io) server，Claude Desktop 等 MCP 客户端可以直接调用。全程不经过语言模型：结果由代码计算，同样的输入得到同样的结果（塔罗传入 `seed` 才能复现）；每条释义带 `ref_id`、正文和审核级别，`review.confidence_cap` 是按所用释义的最低审核级别得出的置信度上限，与对话中的解读同一口径。

### 安装与运行

```bash
uv sync --locked --extra mcp          # 可与 --extra llm --extra web 一起装
uv run python -m scripts.fetch_data   # 星历、地名与 Unihan 数据
uv run python -m knowledge.build      # 知识库
uv run python -m mcp_server           # stdio 传输：通常由 MCP 客户端启动，手动运行会一直等待输入
```

依赖为官方 Python SDK `mcp` 的 FastMCP，版本范围 `mcp>=1.30.0,<2`（mcp 2 把 FastMCP 改名为 MCPServer 并调整了接口）。Windows 用 `setup.ps1` 安装过的环境，把第一行换成 `& .\.bootstrap\Scripts\uv.exe sync --locked --extra llm --extra web --extra mcp`。

### Claude Desktop 配置

在 Claude Desktop 的「设置 → 开发者 → 编辑配置」打开 `claude_desktop_config.json`（macOS 位于 `~/Library/Application Support/Claude/`，Windows 位于 `%APPDATA%\Claude\`），加入下面一段，把路径换成自己的，保存后重启 Claude Desktop。`command` 请写 uv 的绝对路径，图形界面程序不一定继承终端的 PATH（macOS 用 `which uv` 查看）。`--extra mcp` 保证每次启动时依赖齐全，即使之后重新同步过环境。

macOS：

```json
{
  "mcpServers": {
    "zhiming": {
      "command": "/Users/<用户名>/.local/bin/uv",
      "args": ["--directory", "/Users/<用户名>/ZhiMing", "run", "--extra", "mcp", "python", "-m", "mcp_server"]
    }
  }
}
```

Windows（`setup.ps1` 把 uv 装在仓库的 `.bootstrap` 里；自行安装的 uv 用 `where.exe uv` 查看路径）：

```json
{
  "mcpServers": {
    "zhiming": {
      "command": "C:\\Users\\<用户名>\\ZhiMing\\.bootstrap\\Scripts\\uv.exe",
      "args": ["--directory", "C:\\Users\\<用户名>\\ZhiMing", "run", "--extra", "mcp", "python", "-m", "mcp_server"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

连接成功后，对话输入框的工具菜单里会出现 `zhiming` 的十个工具。启动失败时，Claude Desktop 的 MCP 日志（macOS `~/Library/Logs/Claude/`，Windows `%APPDATA%\Claude\logs\`）会显示原因，最常见的是还没有构建知识库。

### 工具

| 工具 | 作用 | 主要参数 |
| --- | --- | --- |
| `resolve_location` | 解析出生地，返回 `location_id`、经纬度与时区；同名地点返回候选 | `query`、`country`、`admin1`、`candidate_id` |
| `compute_natal_chart` | 本命盘：行星落座与宫位、四轴、相位 | `birth` |
| `compute_transits` | 区间内行运对本命的精确相位 | `birth`、`start`、`end`、`tz`、`orb`、`bodies` |
| `compute_bazi` | 八字四柱、十神、藏干、纳音、五行计数、大运 | `birth`、`gender`、`true_solar_time`、`zishi_rule`、`calendar`、`lunar_date`、`leap_month` 等 |
| `compute_bazi_period` | 流年、节气流月或流日，与原局的十神与冲合刑害 | `birth`、`start`、`end`、`tz`、`granularity` 等 |
| `draw_tarot` | 抽牌（单张、三张、二选一） | `question`、`spread`、`seed`、`picks` |
| `analyze_name` | 康熙笔画、五格数理、三才五行 | `surname`、`given`、`forms` |
| `lookup_dream_symbols` | 梦境意象与知识库匹配，未收录的不解读 | `symbols` |
| `daily_fortune` | 当天行运相位、流日干支与十神、每日一牌 | `birth`、`date`、`tz`、`user_key` 等 |
| `lookup_meaning` | 按 system/kind/key 精确查释义 | `system`、`kind`、`key` |

`birth` 包括 `birth_local`（出生地当地钟表时间，`YYYY-MM-DD HH:MM`）、`time_known`，以及地点：`resolve_location` 返回的 `location_id`（新疆另填 `clock_tz`），或直接给出 `tz` 与 `lon`（星盘另需 `lat`）；夏令时重复时刻用 `fold`。`compute_transits`、`compute_bazi_period`、`daily_fortune` 的 `tz` 是咨询日期所用的时区，不一定是出生地时区。

### 与对话运行时的区别

- **来源校验**：对话里出生资料必须来自用户原话，这是 Guard 的来源校验，用来防止模型编造。MCP 调用方直接给出结构化参数，没有原话可以核对，所以 MCP 走与会话无关的计算入口 `plugins/direct.py`（与网页「直接排盘」共用出生资料换算），不建会话，不调用运行时的工具，也不经过 Guard；运行时的校验一处没改。请只把用户本人提供的资料传给这些工具。
- **需要本人决定的事项**仍返回 `status: needs_input` 和要转问的问题：同名地点、新疆出生钟表、海外出生是否用真太阳时、节气当天时辰未知、无法确定笔画的字等。
- **参数错误**返回错误结果，结构化内容为 `{"ok": false, "code": "invalid_arguments", "error": "…", "details": [{"field": "birth.lat", "message": "…"}]}`；其他错误码有 `unknown_location`、`missing_entry`、`data_missing`。
- **不保存数据**：没有画像、记录和缓存。`chart_id`、`bazi_id`、`draw_id` 是输入的哈希，同样输入编号相同，与对话运行时数据库中的记录无关。每日一牌由 `user_key`（省略时由出生资料生成）和日期决定。
- 不传 `seed` 的抽牌随机生成一个小于 2^53 的种子并随结果返回，JSON 客户端可以原样传回复现同一组牌。

### 许可与对外服务

星盘计算依赖 Swiss Ephemeris（`pyswisseph` 与 `sepl_18.se1`、`semo_18.se1` 星历文件），它采用 AGPL-3.0 与 Swiss Ephemeris 商业许可（Astrodienst AG）双许可。在自己电脑上通过 stdio 自用不涉及向他人提供服务。若把这个 MCP server 或网页版部署成供他人通过网络使用的服务：

- 按 AGPL-3.0 第 13 条，须向通过网络与服务交互的用户提供完整的对应源代码（含你的修改），整体以 AGPL 兼容的条款提供；不愿公开源码则需向 Astrodienst 购买商业许可；
- 把程序或修改版分发给他人时，同样须附源码并保留许可声明；
- 本仓库目前没有 LICENSE 文件（《项目完善计划书》F6），对外提供服务前应先确定项目许可；
- 其他数据：GeoNames 地名为 CC BY 4.0，须署名；Unicode Unihan 按 Unicode License；JPL DE440s 为美国政府公开数据。

以上是使用时的注意事项，不是法律意见。

## 隐私、当前限制和后续工作

用户数据落盘在本地；真实模型 API 会收到执行任务需要的对话、画像与工具结果。`/forget` 删除当前用户在应用数据库、trace 和内存中的数据，并压缩 SQLite；不能删除第三方模型服务留存、系统备份或已导出的报告。

网页身份 cookie 随每次通过认证及来源检查的访问续期，有效期为最后访问后12小时。持续使用不会因首次创建超过12小时换身份。闲置到期后自动删除该浏览器身份的画像、历史记录、排盘/每日缓存、专家报告、审校意见和应用 trace；服务在线时每分钟清理，并在请求前检查，忙碌请求结束后再清理。先删 trace、后删业务记录与清理期限；任一步失败会记录日志并保留期限，下一次清理重试，不影响其他请求和后台清理。清理期限保存在业务库中，重启后仍会执行；本版本尚不恢复重启前的浏览器会话，已失去会话映射的资料会在原期限到达时清理。升级前没有清理期限的 `web-` 用户记录，在新版本启动时补登，从首次启动起给予12小时宽限；只有 trace、没有业务记录的旧目录不在补登范围内。CLI 用户不受这项自动清理影响。数据库备份与手工导出的文件需另行处理。

每轮重新获取当前时刻，“今天/明天”优先按画像 `consultation_tz`，其次出生 `tz`，均无则按 `Asia/Shanghai` 解析；画像中无效的旧时区值会被跳过，不会中断对话，新写入的 `tz` 与 `consultation_tz` 都必须是有效 IANA 时区。日期基准同时传入编排者与专家。出生表单或原话中的“出生钟表时区”“出生时区”“出生采用北京时间”等描述只作为出生资料，不会覆盖已保存的咨询时区；明确说明当前居住地或本次按某地时间咨询时，才作为咨询时区证据。每日运势只按日历基准所用时区计算：用户在对话中说明了咨询时区、或出生时区只来自本轮解析的地点时，工具会先要求把该时区保存进画像，刷新日历后再按新的日期计算，不会出现“今天”按一个时区、运势按另一个时区算。

第一周的规则只能检查结构化引用、显式牌名与部分位置及方向事实，不能证明每一句自然语言都受引用支持。健康、法律、投资、生死问题有基础标注规则；识别到明确自伤表达会停止占卜。更完整的语义安全、事实支持与审校评估留到第五至七周。

当前支持原数据集中的五个危机场景及中途危机转折。隐晦的消失/永远睡去等表达先由同一模型分类，分类失败则暂停占卜并确认安全。危机状态在同一会话中保留；继续索要占卜、CLI `/new`、网页新对话或直接排盘均不能跳过确认。用户需按回复中的提示单独确认当前安全、没有自伤/伤人打算且未受到威胁；确认语忽略全半角、空格、外围引号与句末标点，但附加请求或其他内容仍不会解除暂停。确认轮只回应支持，下一轮才可恢复咨询。危机状态只保存在当前进程的会话中：服务或 CLI 重启、浏览器换新身份后不会保留。网页先在入口做一次安全检查，同一条消息不会再交给模型重复分类。

危机联系方式按已填写的咨询时区、出生时区选择；网页尚未保存画像时也读取出生地点表单。当前配置大陆12356、110/120和美国988、911；均以“若你目前在该地区”为前提。未知或未配置地区使用通用当地紧急服务提示，不根据中文或默认日历时区猜地区。来源与2026-10-20核实记录见[热线核实](verification/stage0/hotlines.md)；12356各地服务时间可能不同，不承诺24小时接通。

抽牌直接返回版本固定的精确释义，新解读通常3轮模型调用，原牌追问2轮。完整信号仍保存到SQLite与trace，给模型传递精简工具结果；已完成轮次的工具JSON从后续对话上下文移除，跨会话从数据库恢复。未完成轮次上下文超过64,000字符时，程序以有界快照保留当前记录、原牌面、计算ID、可用引用和最近错误；完整事实仍在运行状态中，不能据快照缺失细节猜测。每次请求预算重新建立。错误回复分别说明步数上限、请求token预算、单次输出上限、服务限流、认证和超时，只有确有牌面或计算时才提示保留。稳定系统提示与工具结构保持前缀稳定，缓存是否命中以接口usage为准。

第二周已接入本命盘和行运，第三周已接入八字，第四周已实现多 Agent 编排，第五周已实现交叉合并与审校，第六周已接入姓名、解梦与每日运势（第四周真实模型已测试，整体关口未通过；第五、六周验收状态见各周报告）；第七周完整评估。当前不把后续能力声明为已实现。
