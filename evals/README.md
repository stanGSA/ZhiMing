# 占卜 Agent 评估数据集

对应计划书“数据库与环境配置 → 五、评估数据集”的 9 类数据，外加 1 份共用画像夹具。解压后把 `evals/` 放进项目根目录即可，路径与计划书一致（`evals/cases/*.yaml`）。

## 一览

| 文件 | 数量 | 怎么来的 | 状态 |
| --- | --- | --- | --- |
| `reference_charts.yaml` | 11 盘 | Swiss Ephemeris 计算，交叉验证见下 | 已计算并校验 |
| `bazi_boundary.yaml` | 50 例 | lunar_python 计算 + 独立实现交叉验证 | 已计算并校验 |
| `name_strokes.yaml` | 200 字 | Unicode Unihan 18.0 + 五格部首还原规则 | 181 字已校验，19 字待人工定稿 |
| `trajectory.yaml` | 80 题 | 人工编写（8 类 × 10） | 草稿，待审核 |
| `dream_annotations.yaml` | 100 条 | 人工编写并标注 | 草稿，待审核 |
| `reviewer_drafts.yaml` | 45 份 | 人工编写：30 份坏草稿 + 15 份可接受草稿 | 草稿，待审核 |
| `safety.yaml` | 30 例 | 人工编写 | 草稿，待审核 |
| `multiturn.yaml` | 12 段 | 人工编写的脚本化多轮对话 | 草稿，待审核 |
| `reference_queries.yaml` | 50 条 | 人工编写（第 7 周可选的 RAG） | 草稿，相关段落 id 待建库后标注 |
| `profiles.yaml` | 6 个画像 | 合成数据，供上面三类用例引用 | — |

所有出生信息、姓名都是合成数据，不对应真实人物。

## 有标准答案的三类：做了哪些校验

**参考星盘（reference_charts）**

- 覆盖：1900–2024 年；南北半球；赤道附近与高纬度；UTC+5:30 半小时时区；1987 年中国夏令时；本地日期与 UT 日期跨天；水星逆行；北极圈内 Placidus 无定义（第 10 盘，给出 Porphyry 回退结果）；时间未知（第 11 盘，宫位为 null）。
- 行星位置：Swiss Ephemeris 星历文件结果与 Moshier 解析星历对比，最大差 0.00056°，远小于 0.01° 的容差。
- 宫位：Swiss Ephemeris 结果与独立实现的 MC / 上升 / Placidus 公式对比，差值小于 0.000001°。
- 与计划书不同的一点：计划写的是用 Skyfield 交叉验证，生成环境无法下载 JPL 星历，改用了上面两种方式。项目环境搭好后，建议在 `tests/` 里再补一道 Skyfield 校验。

**八字边界（bazi_boundary）**

| 类别 | 数量 | 测什么 |
| --- | --- | --- |
| 立春换年 | 8 | 立春前后 15 分钟，年柱和月柱一起换 |
| 节气换月 | 10 | 惊蛰、清明、芒种、白露、大雪前后 10 分钟 |
| 子时归属 | 8 | 23 点换日与“早晚子时”两种规则各给一套答案 |
| 真太阳时 | 8 | 乌鲁木齐、喀什等经度偏差大的城市；上海、广州两例主要由均时差造成差异 |
| 夏令时 | 6 | 1986–1991 年夏令时换算；不存在的时间（02:30）与重复的时间（01:30）期望追问 |
| 农历闰月输入 | 6 | 5 个闰月 + 1 个非闰对照 |
| 春节与立春错位 | 2 | 过了春节没过立春、过了立春没过春节 |
| 时辰未知 | 2 | 只排三柱；节气当天时辰未知时期望追问 |

- 四柱：lunar_python 与独立实现（太阳视黄经定年月、儒略日定日柱、五鼠遁定时柱）55/55 一致；年、月、时干十神 55/55 一致。
- 节气时刻：lunar_python 与 Swiss Ephemeris 最大差 2.3 秒；所有节气边界用例离节气至少 9.5 分钟，答案不受算法差异影响。
- 闰月：用 Swiss Ephemeris 求朔日与中气，6 例的农历初一日期和闰月判定全部一致。其中 2020 年闰四月是“中气与下一个朔日同一天”的经典陷阱，已在用例里注明。
- 夏令时与真太阳时用例都额外记录了“忽略夏令时 / 关闭真太阳时会得到什么”，方便直接测出常见错误。
- 大运用 lunar_python 默认起运算法，不同流派起运岁数可能相差数月。

**名字笔画（name_strokes）**

- 100 个常见姓氏用字 + 100 个常见名字用字，覆盖氵扌艹辶阝（左右）王字旁、月肉之分、数字一至十等规则。
- 与 37 个公认的常见姓氏五格笔画比对，37/37 一致。
- 19 个字标为 `needs_review`：多是姓氏的繁体惯例（于、余、范、钟写“鍾”、肖与蕭等）或名字里的繁简歧义（杰 / 傑、郁 / 鬱、强 / 強等）。期望工具给出默认值并提示，或通过追问确认写法。上线前请对照康熙字典定稿。

## 人工编写的六类：审核时重点看什么

这几类没有公开数据可用，内容是按计划书的设计逐条编写的，`status: draft_needs_review`。建议审核时关注：

- `trajectory.yaml`：每题的期望专家与工具集合是否符合你的设计；`optional_tools` 定得宽还是严会直接影响 F1。
- `dream_annotations.yaml`：金标意象是否合理；`vocabulary_used` 里的 89 个 key 是解梦知识库 300 条意象的种子，建议先定下这份 key 表。
- `reviewer_drafts.yaml`：坏草稿是否“坏得明显”、可接受草稿是否确实不该打回，这决定了漏拦率和过度干预率能否真实反映宽松审校的尺度。
- `safety.yaml`：`must_include` / `must_not` 是否与你的安全策略一致；危机类用例的求助渠道按目标用户所在地区补充具体热线。
- `multiturn.yaml`：对“何时开新 reading”的约定（例如“那下下个月呢？”算新 reading）是否同意。
- `reference_queries.yaml`：`expected_topics` 同时是参考文本库的选题清单。

## 重新生成

`evals/generators/` 里是生成脚本。三类计算型数据集需要：

```bash
pip install lunar_python pyyaml
export SWETEST=/path/to/swetest            # Swiss Ephemeris 命令行程序
export SE_EPHE_PATH=data/ephe              # sepl_18.se1 / semo_18.se1
export UNIHAN_DIR=data/unihan              # kRSUnicode.txt、kTotalStrokes.txt、kTraditionalVariant.txt、kKangXi.txt
cd evals/generators
python gen_charts.py ../cases/reference_charts.yaml
python gen_bazi.py   ../cases/bazi_boundary.yaml
python gen_names.py  ../cases/name_strokes.yaml
```

在当前环境里已验证：用这三个脚本重新生成，输出与包内文件逐字节一致。其余脚本只依赖 `pyyaml`。

数据来源：Swiss Ephemeris（aloistr/swisseph，AGPL / 商业双许可）、lunar_python（6tail/lunar-python，MIT）、Unicode Unihan 18.0（Unicode License）。

## 项目当前执行范围（Week2 / Week3，2026-10-13）

上文数据集自带的验证说明不等于本次运行结果。当前实际计算验收由`python -m scripts.archive.verify_week23`逐项读取原始11盘、50例；不运行生成器覆盖金标。占星另用Skyfield/JPL DE440s、统一TT与视位置口径独立对照。详细误差和逐例状态见`docs/verification/week23/computations.json`。

`python -m evals.run --suite trajectory`回放当前可用三体系的50条标注路线，经过实际guard、registry、计算器、存储及trace；30条依赖未实现工具或解梦历史而跳过，逐题记录原因。它不是模型自主路由F1，也不评估自然语言质量。相对日期使用明确的集成测试区间，H_timing/H_decision为新生成合成历史；first_action题止于追问，不编造后续输入。

`python -m scripts.live_week23`使用现有兼容接口和gpt-6.1-sol测试14个合成场景，另以固定四项rubric评审最终回答；工程和质量分开计分。评审是同一请求模型，不是人工审核或独立模型。`scripts.archive.review_week23`可以对保留的原答案提供完整计算证据重新评审，结果写入独立文件，原判定不覆盖。`scripts.live_test`保留第一周17场景回归。未执行完整80题真实轨迹、完整30题安全语义评审及后续体系数据集，不声称这些检查通过。

## 第六周执行范围（2026-10-14）

`python -m evals.run --suite week6` 逐字读取 `name_strokes.yaml` 的 200 字，对照 `plugins/name/strokes.py` 的输出（200/200，37 个公认姓氏 37/37），并检查每日运势跨会话 10 次一致、三个新知识分区的覆盖率和 89 个解梦种子意象。19 个 `needs_review` 字的定稿记录在代码与 `docs/verification/week6/datasets.json`，数据集金标未改动。`dream_annotations.yaml` 只做了结构审核；离线 precision / recall 来自词典扫描基线，不是计划中的 LLM 抽取指标。`--suite trajectory` 的标注路线回放现覆盖全部 80 题（含 H_dream 历史），仍不是模型自主路由 F1。

## 评测总表（2026-10-26）

`uv run python -m evals.report`（或 `make eval`）离线生成 `reports/eval/summary.md` 与 `summary.json`，约 10 秒，不调用任何付费模型。各项沿用已有口径：工具选择调用 `evals.run` 的离线演示回放（single 与 multi）；参考星盘与八字边界调用 `evals/facts.py`（与 `scripts.archive.verify_week23` 共用，缺少 `de440s.bsp` 时只跳过 Skyfield 交叉校验）；姓名笔画与每日运势调用 `evals/week6.py`；安全集调用 `evals/safety.py`（危机检查与 `tests/runtime` 同一组）；审校调用 `evals/reviewer.py` 的离线关键词基线；延迟为本机单轮 P50 与最近秩 P95。真实模型一节只读取 `docs/verification/p1/` 的归档摘要，用 `scripts.failure_taxonomy` 重算并写明模型、日期、评委与口径版本。

每个数据集标出状态；`draft_needs_review` 数据集上的结果标“草稿”。参考星盘、八字边界、姓名笔画三份文件没有 `status` 字段，按上文“已计算并校验”记为 `computed_cross_checked`，姓名笔画另列逐字状态（`auto_ok` 181、`needs_review` 19）。
