# PR #1 整改验收

日期：2026-10-13。本次先复核并修订Claude PR #1的缺陷分析，再依据整改清单实施本地修复、确定性测试、工具集成和真实模型复测。报告生成后已按用户要求提交`v2`（`abb5c17`）并推送main；没有改写v1历史。

结论：确定性计算和本地工程回归通过；真实模型严格综合验收仍未全部通过，人工审核仍待完成；v2远程CI已通过。不能将本次整改写成Week2、Week3的全部发布关口通过。

## 文档与实现

- [修订缺陷分析](week1-3-缺陷分析.md)：区分已复现缺陷、夸大结论与额外增强建议；不把同源计算或未执行检查称为独立验证。
- [20项整改清单](pr1-整改清单.md)：逐项记录已修复、改善、未完成及外部验证事项。
- [真实模型完整记录](../reports/live-gpt-6.1-sol-pr1.md)：20题原问题、补充资料、实际最终回答、四项质量评审、工具错误、首次失败及复测。该脱敏Markdown已随v2纳入仓库；原始JSON、trace与测试数据库仍仅本地保存。

| 修改范围 | 代码位置 | 已实现行为 |
|---|---|---|
| 原话证据与画像 | `common/input_evidence.py`、`common/tools.py`、`common/schemas.py` | 中文年月日、中文时刻和性别规范化，日期格式等价；伪造画像仍拒绝 |
| 咨询范围及时区 | `plugins/context.py`、`common/time_utils.py` | 区分生日与问题区间、出生时区与咨询时区；检查偏移与IANA规则，区间结束语义统一 |
| 地名及海外八字 | `common/location.py`、`plugins/bazi/tools.py` | 国家城市组合解析、旧性别画像兼容、海外排盘口径先追问 |
| 领域事实与插件接口 | `plugins/*/validation.py`、`plugins/base.py`、`common/validation.py` | 插件注册输出校验，补宫位表达和事件关联检查；统一horizon，保留旧值兼容 |
| 缓存与模型故障 | `harness/guard.py`、`harness/llm.py`、`harness/loop.py`、`harness/models.py` | 画像版本影响缓存，非法工具JSON可修正，usage缺失暂停该轮；终止和归属规则保留 |
| 知识内容 | `scripts/draft_week23.py`、`knowledge/sources/astro/entries.yaml`、`knowledge/sources/bazi/entries.yaml` | 修正文案、升至条目版本3、补齐四主题键；旧版本快照保留 |
| 数据与跨平台 | `scripts/data_manifest.yaml`、`.github/workflows/ci.yml`、`plugins/astro/calculator.py` | 固定GeoNames快照并校验哈希；CI先下载再doctor；移除原生排盘对chdir/relpath的依赖 |
| 评估证据 | `tests/test_pr1_remediation.py`、`evals/week23.py`、`scripts/live_week23.py`、`scripts/live_pr1.py` | 新增28项回归、纠正回放月份、保存源码哈希和逐题质量；四组独立用户可并发，每个对话仍使用单Agent |

知识条目共584条，条目覆盖率100%，人工审核率0%。感情及财务主题仍有中性占位，不能将接口完整误写成内容倾向完整或人工审核完成。

## 实际确定性与工程结果

| 检查 | 通过 | 失败 | 跳过 | 本地证据或限制 |
|---|---:|---:|---:|---|
| pytest（原188项+新增28项） | 216 | 0 | 0 | `reports/pr1-remediation/regression-latest.xml` |
| 参考占星盘 | 11 | 0 | 0 | `computations-latest.json`；最大黄经误差0.00011036417899390472°，小于0.01° |
| Skyfield/JPL独立交叉验证 | 11 | 0 | 0 | 同一TT、地心视位置、日期回归黄道；最大差6.105503302933357e-7° |
| 八字边界 | 50例/57变体 | 0 | 0 | 两种子时规则及追问期望均检查；未修改参考YAML |
| 当前三体系轨迹回放 | 50 | 0 | 30 | `evals-final/`；后续体系或解梦历史题跳过，不是真实模型路由F1 |
| Week1演示回放 | 12 | 0 | 68 | `week1/`；仅Week1适用范围 |
| 空缓存真实下载与哈希核验 | 4 | 0 | 0 | `clean-download.json`；耗时38.861秒 |

上表中相对证据名均位于本地`reports/pr1-remediation/`。Ruff检查、77个Python文件格式检查、`uv lock --check`、sdist与wheel构建通过。doctor必需项0失败；数据迁移、缓存、记录归属、删除、画像证据、引用校验和终止流程包含在216项回归内。没有重跑完整30题真实安全集，不据这些回归声称安全覆盖完备。

首次新增回归7/7失败记录保存在`first-failures.xml`。中途200通过2失败的回归记录保存在`final-tests.xml`，随后修复了缓存幂等退化和时机规则误拒。轨迹首次49/50失败也保留：回放将“本月”硬编码为十一月，修复回放后50/50；未改原题、参考答案或放宽原断言。

## 真实模型结果与回答质量

使用已有本地环境配置，先进行连通性预检，再测试。请求和服务返回名称均为`gpt-6.1-sol`，返回名称不是底层模型身份的独立证明。质量按正面回答、时间一致、结论有支持、无编造四项另评；评审使用同一请求模型，本助手又逐题核对，二者都不能替代独立人工审核。

最终源码指纹：`4f84bc9d587d8e4f0d79d1c30e44c74b7fbb0658c4d61d2489845d4c514fad23`。两次完整批次、重复测试、针对性重测分别保留，不能按题拼接。

| 测试阶段 | 严格综合通过 | 失败 | 跳过 | 说明 |
|---|---:|---:|---:|---|
| 首个完整20题批次 | 12/20 | 8 | 0 | 作为进一步修复依据，原答原评保留 |
| 最终完整20题批次 | 17/20 | 3 | 0 | 同一源码；覆盖占星、八字、时机、三体系、歧义、未知时辰、跨会话及投资安全问题 |
| 同一道自然占星题重复10次 | 8/10 | 2 | 0 | 四项回答质量10/10；两次内部审核信息被guard拒绝后重写成功，仍计工具错误 |
| 三题针对性复测 | 1/3 | 2 | 0 | 投资通过；占星自动评审仍未完成；海外完整补充变体质量通过但有工具错误 |

最终20题整批返回104次对话响应、19次评审响应，请求尝试分别104和23次；实际返回输入612218、输出29149 token。分题及分阶段延迟、工具错误和用量见完整报告，失败且没有返回usage的调用不推算消耗。连通性预检另为13输入、5输出token，15.549秒。重复题的同模型方向聚类结果一致率1.0，仅适用于该题，不代表所有题稳定或人工校准通过。

最终整批三个未通过项及后续结果：

1. **占星时机**：误读尚不存在的历史记录得到`missing_reading`，恢复后提交了回答，严格零工具错误不通过。自动评审三次请求后服务500；针对性重测和对原答无损表编码复评仍发生服务错误。自动质量评审标为未完成，本助手核对不替代它，也没有证据认定错误由输入长度导致。
2. **投资问题**：首评认为一般风险控制建议没有八字支持。本助手复核认为该答已明确区分八字象征和现实投资建议；不手改原评分。保持原答和rubric的无损复评四项通过，另一次新作答也通过；此差异记录为评审不一致。
3. **海外八字**：原合成补充没有回答完整公历/当地钟表口径，系统继续追问，因此原题未达到预期终止。另立完整补充资料变体，最终回答丁火日主、丁酉日柱，与计算一致；一次没有明确原话证据的布尔画像写入被拒，恢复后完成。质量通过，严格综合仍失败。

修复前后实例：自然中文出生输入在首次探索中进入不必要追问；修复日期、时刻及画像规范化后，同题能够给出沟通梳理、项目推进与长期专业积累方向，并明确需以实际能力验证。合法宫位语序“本命狮子座第4宫太阳”曾被误拒，改进后接受，错误宫位仍被回归测试拒绝。精确问题、原答、修复后原答及四项评价全部见真实测试报告，避免只用概述代替证据。

## 剩余事项与验收判断

- **Week2**：11盘数值及独立交叉验证、本地计算和集成回归通过；真实占星时机自动质量评审未完成、知识人工审核未完成，v2远程Ubuntu已通过。因此不能宣布全部验收关口通过。
- **Week3**：50个边界用例57变体及本地集成回归通过；海外输入的模型工具误调用仍可发生，独立权威万年历抽查和人工知识审核尚缺。因此不能宣布全部验收关口通过。
- D5/D8需补充人工内容审核及主题细分；D13需独立人工20条质量校准；D14需权威万年历独立抽查。本助手和模型评审均不冒充这些工作。
- D6持续容许度窗口未实现，现有工具按精确相位事件定义工作。本次没有扩大至后续周的多Agent、融合或审校能力。
- v2的[GitHub Actions运行38379814078](https://github.com/stanGSA/ZhiMing/actions/runs/38379814078)已完成，Windows和Ubuntu两项均success；本轮新增修改须另行验证。

## 复现

在项目隔离环境执行，沿用已有环境文件，不打印密钥。命令会创建新的记录；真实调用有费用与服务波动，结果不保证复现同一措辞或通过率。

```powershell
$env:PYTHONUTF8 = '1'
uv sync --locked --extra llm
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run python -m scripts.doctor
uv run pytest -q --junitxml=reports/pr1-remediation/reproduced-tests.xml
uv run python -m scripts.verify_week23 --output reports/pr1-remediation/reproduced-computations.json
uv run python -m evals.run --suite week1 --output reports/pr1-remediation/reproduced-week1
uv run python -m evals.run --suite trajectory --output reports/pr1-remediation/reproduced-trajectory
uv run ruff check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
uv run ruff format --check harness agents common plugins knowledge memory scripts tests evals app.py cli.py
uv lock --check
uv build --out-dir reports/pr1-remediation/reproduced-dist
uv run python -m scripts.check_model
uv run python -m scripts.live_pr1
```

无全局uv时使用项目既有`.bootstrap/Scripts/uv.exe`。本地补充探针脚本`reports/pr1-remediation/stability.py`、`retest.py`、`rereview.py`分别保留重复、变体复测和无损复评方法；它们与原始输出均在忽略目录，不当作已发布附件。
