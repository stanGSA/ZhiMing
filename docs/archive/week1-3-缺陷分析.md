# 整改依据：Week1–3缺陷分析（复核修订版）

来源：PR #1，abbee95d；2026-10-13经代码与27项探针复核。保留D1–D20编号用于追踪。本文是整改依据，不是修复完成声明；实时状态见[整改清单](pr1-整改清单.md)。原始PR历史保持不变。

# 第 1–3 周实施缺陷分析

日期：2026-10-13。对照《占卜Agent项目计划书》、第 1–3 周验收与评审修复报告、`reports/` 真实调用记录及 `docs/verification/` 证据，结合代码阅读与本地探针脚本整理。本文只记录缺陷与建议，未修改任何代码。

## 结论

第 1–3 周计划规定的三个计算关口确实达成，已在本地复现。但存在三类问题：

- **真实使用**：最常见的中文日期写法会被拦截；画像存不住性别与出生信息；海外出生的八字默认按北京时间排日柱、时柱。
- **第 5 周的基础**：信号层的主题倾向值基本为空，horizon 取值不统一，会卡住跨体系合并与张力检测。
- **测试证据**：“14/14”由多次运行的最新结果拼成；测试题带强提示；评审模型与被测模型相同。现有结果不能说明稳定性。

## 验证方式

- 阅读计划书、`docs/` 下各周报告、`reports/` 两份真实调用记录、`docs/verification/` 下全部汇总 JSON。
- 按 `uv.lock` 安装依赖，执行 `knowledge.build`、`scripts.doctor` 与全量 `pytest`：188 项中 163 项通过；其余 14 项失败、11 项报错，原因全部是本环境网络策略拦截了 GeoNames 与 JPL 数据下载（`FileNotFoundError`），与代码逻辑无关。
- 下列每条缺陷均用脚本直接调用项目函数验证，复现方法见文末附录。

## 关口达成情况

| 周 | 计划关口 | 状态 |
|---|---|---|
| 1 | 三张牌跑通、塔罗条目全覆盖 | 达成（163/163） |
| 2 | 黄经误差 < 0.01° | 达成，11/11 已复现；Skyfield 对照因 JPL 文件无法下载未复现 |
| 3 | 50 个边界用例全部排对 | 达成，50/50 已复现；起运、大运部分的标准答案与实现同出 lunar_python（见 D14） |

## 缺陷总表

| 编号 | 严重度 | 类别 | 缺陷 | 位置 |
|---|---|---|---|---|
| D1 | 高 | 功能 | 出生日期、时刻只认 `YYYY-MM-DD HH:MM` 字面写法 | `plugins/context.py:65-67` |
| D2 | 高 | 功能 | 画像存不住性别与出生信息，跨会话必然重复追问 | `common/tools.py:71`、`plugins/bazi/tools.py:168` |
| D3 | 高 | 功能 | 海外出生的八字默认按北京时间排日柱、时柱 | `plugins/bazi/tools.py:20` |
| D4 | 高 | 功能 | 事实校验被模型实际输出格式绕过，行运事实不校验 | `common/facts.py:90` |
| D5 | 中 | 设计 | 信号层主题倾向值基本为 0，horizon 取值不统一 | `knowledge/sources/*`、`plugins/*/tools.py` |
| D6 | 中 | 设计 | 行运 `orb` 参数不起作用，在容许度内的慢星相位会漏报 | `plugins/astro/calculator.py:285` |
| D7 | 中 | 设计 | 行运时区默认 `Asia/Shanghai`，不是本命盘时区 | `plugins/astro/tools.py:22` |
| D8 | 中 | 内容 | 知识条目模板拼接，文字有语病 | `knowledge/sources/astro/entries.yaml` |
| D9 | 中 | 设计 | 回答完整性校验按测试题关键词写死 | `common/validation.py:48`、`common/facts.py:19-34`、`common/tools.py:54` |
| D10 | 中 | 功能 | 日期区间校验误拒与漏检 | `plugins/context.py:104` |
| D11 | 中 | 测试 | 真实测试题带强引导 | `scripts/live_week23.py` |
| D12 | 中 | 测试 | “14/14”拼接自不同批次和代码版本，无稳定性数据 | `docs/verification/week23/live-attempts.json` |
| D13 | 中 | 测试 | 评审模型即被测模型，无人工校准 | `scripts/live_week23.py` |
| D14 | 中 | 测试 | 八字起运、大运等字段的金标与实现同源 | `evals/generators/gen_bazi.py` |
| D15 | 中 | 工程 | CI 一定失败，数据快照无法复现 | `.github/workflows/ci.yml:19`、`scripts/data_manifest.yaml` |
| D16 | 低 | 工程 | Windows 跨盘符失败，`os.chdir` 并行不安全 | `plugins/astro/calculator.py:83-92` |
| D17 | 低 | 工程 | 工具参数 JSON 解析错误中断整轮；并行配置未使用 | `harness/llm.py:66`、`config.yaml` |
| D18 | 中 | 工程 | 单 agent 的 token 与时延已远超计划预算 | `config.yaml` |
| D19 | 低 | 文档 | 已撤回报告未标注、证据链接是死链、表述过时 | `reports/`、`docs/` |
| D20 | 低 | 设计 | 输出校验集中在公共代码，插件接口未完全定型 | `common/facts.py`、`common/validation.py` |

## 一、影响真实使用的缺陷（高）

### D1 出生日期、时刻只认 `YYYY-MM-DD HH:MM` 字面写法

位置：`plugins/context.py:65-67`（`birth_provenance`）

校验只把“年 / 月 / . /”替换成“-”，不补零，也不解析中文时刻，再要求 `1993-08-17`、`23:20` 原样出现在用户原话里。

| 用户输入 | 结果 |
|---|---|
| 1993-08-17 23:20 | 通过 |
| 1993年08月17日 23:20 | 通过 |
| 1993年8月17日 23:20 | 被拒：出生日期必须来自用户原话或已有画像 |
| 1993年8月17日晚上11点20分 | 被拒 |
| 1993/8/17 23:20 | 被拒 |

影响：占星、八字主流程对最常见的中文表述不可用。14 道真实测试题全部使用“公历YYYY-MM-DD HH:MM”，README 也引导用户这样输入，因此测试从未覆盖。

建议：先用确定性解析器把用户原话规范化为日期时刻，再与工具参数比对；保留原话片段作为证据。

### D2 画像存不住性别与出生信息

位置：`common/tools.py:71`（`profile_validator`）、`plugins/bazi/tools.py:168`、`plugins/bazi/calculator.py`（`compute_bazi` 性别检查）、`common/schemas.py`（`ProfileInput`）

- `update_profile` 要求字段值是原话子串：保存 `male`（原话“我是男性”）被拒。
- 改存“男”能成功，但随后 `compute_bazi` 从画像读到“男”，返回 `needs_input / invalid_gender`。
- 新会话中模型显式传 `gender="male"`，又被“性别必须来自用户原话或画像”拦截。
- “我1990年5月3日早上8点出生”无法以 `1990-05-03 08:00` 存入 `birth_local_dt`。
- `ProfileInput` 没有 `lat`、`lon` 字段。

影响：中文出生信息及性别规范化失败时，跨会话可能重复追问；ISO/英文枚举和读取原记录路径不受此概括影响，第 5 周“重复询问率 = 0”的目标没有基础。

建议：画像字段存规范化值（性别枚举、ISO 时刻、地点 ID 与经纬度），校验改为“原话经同义词表或解析器能推出该值”。

### D3 海外出生的八字默认按北京时间排日柱、时柱

位置：`plugins/bazi/tools.py:20`（`true_solar_time: bool = False`）、`plugins/bazi/calculator.py`（`civil_time`）、`agents/orchestrator.py`（提示词默认 `true_solar_time=false`）

| 出生 | 默认结果 | 说明 |
|---|---|---|
| 纽约 1995-12-31 23:45 | 时柱丙午 | 按北京 1996-01-01 12:45 计算；打开真太阳时为庚子 |
| 伦敦 1990-06-15 14:00 | 时柱己亥 | 按北京 21:00 计算 |

伦敦下午 4 点以后出生的，换算到北京已是次日，按UTC+8口径的日柱可能与出生地民用日口径相差一天；这是需要明确的流派选择，不能无前提断言计算错误。计划书配置写的是 `bazi.true_solar_time: true`，实现与提示词默认为 false。测试里的纽约人设只测了占星，没测八字。

建议：非中国时区出生时默认使用出生地当地时间或真太阳时，或至少先追问口径并在回答中披露。

### D4 事实校验被模型实际输出格式绕过

位置：`common/facts.py:90`（宫位正则）、`common/facts.py` 行运部分

| 文本 | 校验结果 |
|---|---|
| 水星摩羯第9宫（实际第4宫） | 拦截 |
| 水星摩羯、第9宫 | **放行** |
| 水星（摩羯，第9宫） | **放行** |
| 水星在第九宫 | **放行** |
| 时辰未知时“太阳落十宫代表事业心” | **放行** |
| 时辰未知时“你的上升星座偏向天秤” | **放行** |

“水星摩羯、第4宫”正是模型在真实回答中使用的格式。行运的相位类型、日期、容许度完全不校验。报告中的“无编造”实际主要依靠同一模型评审，代码层未实现计划书 guard 第 6 条“提到的每个行星位置都必须存在于工具结果中”。

建议：正则容忍标点与中文数字；对行运事件建实体表（行运星、相位、本命点、日期）逐项比对。

## 二、会卡住第 4–5 周的设计问题（中）

### D5 信号层主题倾向值基本为 0，horizon 取值不统一

- 占星 280 条中 276 条 `theme_map` 全为 0，仅 4 种相位类型（对分、六分、四分、三分）有非零值；所有条目只有 `self`、`career` 两个主题。
- 八字 141 条中，每条 `self` 与 `career` 的值完全相同，主题维度等于没有。
- horizon：占星、八字使用 `long_term` / `short_term`，塔罗使用 `moment`，计划书定义为 `trait / timing / moment / psyche`。`plugins/base.py` 中 `Signal.horizon` 是自由字符串，无枚举约束。

影响：第 5 周按 horizon 分组、按主题合并时，占星大部分原子条目为中性，但本命相位仍可产生非零信号，几乎不可能与八字形成“张力”；感情、财务类问题拿不到占星和八字信号。周报所说“第三个体系接入时定型插件接口”实际未定型。

建议：在拆多 agent 之前用 `Literal` 统一 horizon 与主题集合，并给条目填入有区分度的倾向值。

### D6 精确行运事件与容许度窗口语义需要区分

位置：`plugins/astro/calculator.py:285`（`allowed_orb_deg=orb` 仅透传）

- 算法只寻找精确成相时刻。1993-08-17 23:20 北京出生的盘，2026-11-01 至 2026-11-30 区间，`orb=1` 与 `orb=8` 都得到 112 个事件，`orb_deg` 均在 1e-10 量级。
- 强度公式中“越紧越强”一项因此在精确相位处接近满分（本命相位不受此概括影响），与 README“占星信号按容许度与速度确定强度”不符。
- 慢行星整段时间都在容许度内、但精确成相不在区间内的情况会漏报，而这正是“下个月适不适合”最该看的情况。

建议：输出“入相 / 精确 / 出相”时间窗口，让容许度真正参与筛选与强度计算。

### D7 行运时区默认 `Asia/Shanghai`

位置：`plugins/astro/tools.py:22`（`TransitInput.tz`）

模型漏传 `tz` 时，海外用户的区间边界与事件日期会被静默按北京时间计算。建议明确咨询区间时区；出生时区不等于当前咨询时区，缺少依据时追问。

### D8 知识条目模板拼接，文字有语病

- 120 条“行星×星座”只有 10 种职业建议句：每颗行星一句，与星座无关。例如任何星座的火星都是“可把任务推进、交付与流程改善作为小任务探索方向”。
- 首句机械拼接，例如“火星落巨蟹，可将行动与竞争与关注归属感，表达需求而非期待别人猜一起反思”。
- 这些文字会直接作为“依据”展示给用户。审核率 0% 已披露，但模板化与语病未披露，人工审核工作量被低估；真实测试中“结论有引用支持”的评审结果也因此带有循环性。

### D9 回答完整性校验按测试题关键词写死

位置：`common/validation.py:48`、`common/facts.py:19-34`、`common/tools.py:54`

只有问题中出现 `下个月.*跳槽`、`日主`、`起运日期|起运时间|什么时候起运`、`首步大运|首运`、`二选一|决策牌阵|A/B` 等关键词时才触发检查。“11月适合换工作吗”“我什么时候开始走大运”就不检查。这是对测试集过拟合；计划书中的“直接作答率”应由通用规则加评审衡量。

### D10 日期区间校验误拒与漏检

位置：`plugins/context.py:104`（`range_provenance`）

- “请看2026-11-01至2026-11-30求职，我生于1993-08-17 23:20”被误拒，因为代码取原话中最后两个 ISO 日期作为区间。
- “看看2026年11月适合求职吗”这类中文区间完全不校验，模型填任意区间都能通过。
- 比对范围是整个会话的全部用户消息，而不只是当前问题。

## 三、测试证据的可信度（中）

### D11 真实测试题带强引导

`scripts/live_week23.py` 中主流程多给出标准格式日期（缺资料、农历及追问题除外），并把期望行为写进问题，例如“按23点换日、不用真太阳时、不下喜用神结论”“不能把相位日期当录用日期”“我还没确认是回拨前还是回拨后”“我还没确认是否闰月”。这测的是指令遵从，而不是默认行为。

### D12 “14/14”拼接自不同批次和代码版本

- 11 次运行共 88 个场景：38 个通过，50 个失败。
- 核心题历史通过率：三体系时机 1/6、占星时机 1/6、占星工作方向 2/9；修复后每题只验证一次。
- 最终 14 题来自三个批次。地名校验收紧发生在 12 题所在批次之后，最终代码从未完整跑过一轮。
- 计划书要求的自一致性（同题 10 次，方向一致率 ≥ 90%）未测。

### D13 评审模型即被测模型

评审与被测都是 `gpt-6.1-sol`，也未做计划书要求的 20 条人工抽查校准。计划书明确建议评审模型与 agent 模型不同。

### D14 八字部分字段的金标与实现同源

`evals/generators/gen_bazi.py` 中的独立实现只校验四柱与十神；起运日期、大运序列、纳音、藏干的标准答案与实现都来自 lunar_python `getYun` 流派 1，50/50 中这部分属于自证。计划书建议的“抽 10 条与权威万年历比对”未做（第三周报告已披露）。

另：第 1–3 周没有真实模型的路由数据。50 题轨迹按标注路线回放，F1 = 1.000 来自 demo 模式（已披露），不能当作路由能力。

## 四、工程、CI 与文档

### D15 CI缺数据已确认，GeoNames固定快照存在可重取性风险（中）

- `.github/workflows/ci.yml` 不下载数据，但 `scripts.doctor` 把 `de440s.bsp`、`cities15000.zip` 标为必需；本地复现 doctor 退出码为 1，CI 会停在 doctor 这一步。
- 另有 25 项测试依赖下载数据。
- `scripts/data_manifest.yaml` 中 GeoNames 地址未固定版本，文件每日更新，更新后可能哈希失配；需固定可重新取得的快照，不能未经下载核验就断言当前源已失配。
- 远程CI已运行：main和本PR的Ubuntu均在doctor缺数据处失败，Windows被取消；不能声称远程尚未运行。

建议：CI 增加下载与缓存步骤，或把依赖下载数据的测试单独标记；固定 GeoNames 快照（自建镜像或提交裁剪子集）。

### D16 Windows 跨盘符失败，`os.chdir` 并行不安全（低）

`plugins/astro/calculator.py:83` 的 `os.path.relpath(EPHE, cwd)` 在当前目录与项目不在同一盘符时抛 `ValueError`，所有占星计算失败。`os.chdir` 切换进程工作目录，到第 4 周专家并行时不安全（第二周报告已自述）。

### D17 工具参数 JSON 解析错误中断整轮；并行配置未使用（低）

- 模型返回不合法的工具参数 JSON 时，`harness/llm.py:66` 的 `json.loads` 异常使整轮返回 `model_error`，没有把错误回给模型自我修正，违背计划书 guard 第 1 条“返回错误让 LLM 自我修正，而不是抛异常”的原则。
- `config.yaml` 中的 `max_parallel_tools: 5` 没有任何代码使用，工具实际串行执行。
- 服务未返回 usage 时记为 0 token，预算检查会失效。

### D18 单 agent 的 token 与时延已远超计划预算（中）

- 单 agent 三体系一次约 5 万输入 token、86 秒；最慢一次 148 秒。
- token 预算已从计划的 60000 提到 180000，单次超时从 30 秒提到 90 秒（重试 3 次，最坏约 270 秒）。
- 第 4 周拆专家、第 5 周加审校会叠加，计划中的 `specialist_timeout_s: 30`、`request_token_budget: 60000` 需要现在重新估算。

### D19 文档问题（低）

- `reports/live-gpt-6.1-sol.md` 开头仍写“通过：9/9”，其中“跨会话追问”带工具错误却标为通过，文件内未标注已撤回。
- `reports/live-gpt-6.1-sol-week23.md` 中原始 JSON 与 trace 链接指向被 `.gitignore` 忽略的文件，在仓库中是死链。
- `docs/week2-验收报告.md` 与 `docs/verification/week23/README.md` 中“未提交、未推送”的表述已过时。

### D20 输出校验集中在公共代码，插件接口未完全定型（低）

`common/facts.py`、`common/validation.py` 直接引用塔罗牌名与占星常量，新增体系需要改公共代码，与“新增占术只加插件目录和知识分区”的设计目标不一致。`plugins/astro/evals/`、`plugins/bazi/evals/` 只有 README，没有插件自带用例。

## 做得好的地方

- 确定性计算扎实、可复现：11 张参考盘、50 例八字边界在本地全部通过；三体系真实回答中的落座、宫位、相位日期与重新计算的结果一致。
- `harness/` 不引用任何插件或知识库代码。
- 失败记录、撤回旧结论、“未验证事项”都写得坦诚；0% 审核率没有被包装成通过。

## 第 4 周开工前的修复建议

1. **先修 D1–D4**：日期解析、画像存储、海外八字时间口径、事实校验格式覆盖。这几项决定真实用户能不能用。
2. **统一信号格式（D5–D7）**：拆多 agent 之前定好 horizon 枚举与主题集合，给 `theme_map` 填入真实值；行运改为“入相 / 精确 / 出相”窗口，默认使用本命盘时区。
3. **去掉写死的关键词（D9、D10）**：换成通用的回答完整性检查与区间解析。
4. **重建测试证据（D11–D14）**：补一组不带提示的自然语言题（中文日期、海外出生、跨会话）；在最终代码上整批跑 5–10 次统计稳定性；换用不同的评审模型并做人工抽检；抽 10 条八字与权威万年历比对。
5. **修 CI 与文档（D15、D19）**：增加数据下载与缓存，固定 GeoNames 快照；给旧报告加撤回说明，修正死链与过时表述。
6. **重估预算（D18）**：按实测 token 与时延重新设定多 agent 的超时与预算。

## 附录：复现方法

在仓库根目录执行 `uv sync --locked --extra llm`、`uv run python -m scripts.fetch_data`、`uv run python -m knowledge.build` 后，用 `uv run python -c "..."` 运行以下片段。

**D1、D10 日期与区间校验**

```python
from types import SimpleNamespace as NS
from plugins.context import birth_provenance, range_provenance

def session(text):
    return NS(user_messages=[text], profile={}, state={})

def birth(value):
    return NS(birth_local=value, location_id=None, tz=None, lat=None, lon=None,
              time_known=True, fold=None)

print(birth_provenance(birth("1993-08-17T23:20:00"), session("我1993年8月17日 23:20生于北京")))
print(range_provenance(NS(start="2026-11-01", end="2026-11-30"),
                       session("请看2026-11-01至2026-11-30求职，我生于1993-08-17 23:20")))
```

**D3 海外出生八字**

```python
from plugins.bazi.calculator import compute_bazi

print(compute_bazi("1990-06-15T14:00:00", "Europe/London", -0.1276, gender="male")["pillars"])
```

**D4 事实校验绕过**

```python
from types import SimpleNamespace as NS
from common.facts import validate_calculation_facts

natal = {"time_known": True, "axes": None,
         "planets": [{"body_zh": "水星", "sign_zh": "摩羯", "house": 4}]}
state = {"natal_result": natal, "signals": [], "question": "工作方向"}
for text in ("水星摩羯第9宫", "水星摩羯、第9宫"):
    reading = NS(summary=text, evidence=[], advice=[], timeline=[],
                 question_type="trait", systems_used=["astro"])
    print(text, validate_calculation_facts(reading, state))
```

**D6 行运 orb 无效**

```python
from plugins.astro.calculator import natal_chart, transits

chart = natal_chart("1993-08-17T23:20:00", "Asia/Shanghai", 39.9075, 116.39723)
for orb in (1.0, 8.0):
    print(orb, len(transits(chart, "2026-11-01", "2026-11-30", "Asia/Shanghai", orb)["events"]))
```

**D2 画像存储**：按 `tests/conftest.py` 的 `project` 夹具创建 demo 运行时，依次调用 `update_profile(field="gender", value="male"/"男", evidence="我是男性")` 与不带 `gender` 的 `compute_bazi`，可见前者被拒、后者返回 `invalid_gender`。

**D5、D8 知识条目统计**：读取 `knowledge/sources/astro/entries.yaml`，统计 `theme_map` 非零的条目（仅 4 条），以及 `planet_sign` 条目末句的去重数量（10 种）。

**D15 CI**：不下载数据时执行 `uv run python -m scripts.doctor; echo $?`，退出码为 1。
