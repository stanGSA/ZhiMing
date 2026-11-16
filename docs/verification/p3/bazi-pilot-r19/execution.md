# r19 官方 DeepSeek 实验记录

北京时间 2026-11-16，在 PR #81 合并提交 `cc5a4b6996e33e07eafaf19c3a93aa34991692eb` 上运行。single 与 pipeline 各运行 18 题、每题重复 3 次。运行和评委均请求官方 DeepSeek 配置中的 `deepseek-flash`，评委别名 `pro`；探针的运行回复、工具调用和评委回复三项均通过，requested/returned model 都是 `deepseek-flash`。返回模型名是服务端元数据，不是独立身份验证。

实验配置 SHA-256：`ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`。r18 `run-metadata.json` 记录 `base_url` 为 `https://api.deepseek.com`，此字段作为 r18 接入地址的来源依据；补发的 r18 配置文件与该记录一并保留，探针与运行/评委的 requested/returned model 记录见对应 JSON。`pricing.yaml` 沿用 r18 的费率范围；官方当前单价未核实，费用未知。运行提交使用合并后的 r19 代码，源码指纹 `f05c93db8ba32470b1d2a8c40035d0a4c22822e5cea17e4337364681813cec3a`；single 和 pipeline 的 source-hashes 相同。

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 样本 / 最终评分 | 18 / 18 | 18 / 18 |
| 提交 | 14/18 | 18/18 |
| 已提交且质量通过 | 12/14（85.7%） | 16/18（88.9%） |
| 任务完成且质量通过 | 12/18 | 16/18 |
| 严格综合通过 | 6/18（33.3%） | 16/18（88.9%） |
| 每题模型调用总数 | 116 | 23 |
| 每题运行输入 / 输出 token | 58,260 / 3,278 | 20,441 / 1,219 |
| 每题工具错误 | 0.89 | 0 |
| 修复 / 降级 | — | 5 / 0 |
| 运行耗时 P50 / P95（秒） | 15.1 / 35.8 | 6.6 / 10.5 |
| 缓存命中率 | 73.4% | 82.5% |

两组评委各评分 18 次，36/36 有评分。配对指标“任务完成且质量通过”：pipeline 胜 6、single 胜 2、平 10，共 18 对。每题重复三次，不是 18 个独立样本；运行与评委为同一模型，不构成独立人工校准。

## 编造分类

人工复核 single 的两项 `no_fabricated_facts` 失败，均归为叙述类：事业题 #2 把性格、职业习惯和具体人事场景写成用户情况；大运题 #3 把推算年龄关联到幼儿园、小学和少年期经历。pipeline 18 份提交没有 `no_fabricated_facts` 失败。完整分类见 [fabrication-counts.md](fabrication-counts.md)，逐项理由见本机 `reports/p3-bazi-r19/quality-reasons-with-answers.md`。

pipeline 的两项质量失败都在文字出生题：#2 的 `time_consistent` 与 `supported_conclusion` 未通过，#3 的 `time_consistent` 未通过。评委文字中关于节气边界的理由与其给出的“时间标注基本合规”结论存在不一致，故保留原评分，不作离线改分。流水线修复日志中有 5 份真实拦截项，包含大运前后步、重复标签、确定性用语和标题/流月时段不符；未观察到降级。

## 结论与限制

r19 达到 pilot 的运行完整性、编造计数完整性和“pipeline 已提交质量通过率高于同批 single”的数值条件；但这不是最终冻结结论。样本为合成数据，每题三次重复且同模型评分；文字出生题仍有评委时间判定不一致，且两项质量失败需要负责人确认是否存在可定位的误拒。未据此记录代码冻结，也未启动最终集 `p3-bazi-final`。

运行原始报告、逐题全文、trace 和数据库保存在本机 `reports/p3-bazi-r19/`；发布目录中的 summary、source-hashes、raw-manifest、comparison、failure 归因、计数表、探针和 pricing 文件为审阅入口。第一次 campaign 因隔离工作树缺少被忽略的 GeoNames wheel 而未完成，原始部分结果另存于本机 `reports/p3-bazi-r19-incomplete-20261116/`；修复数据后完整重跑，发布文件只对应完整的第二次 campaign。
