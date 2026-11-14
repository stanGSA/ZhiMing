# r16 官方 deepseek-flash 执行记录

完成时间（北京时间）：2026-11-14 14:52:37。依据 review #76 的方案，配置和代码来自 `claude_modify_model` 合并提交 `5640889a3bbfe22f2885ed57e8672e0023fa3873`。实验使用官方端点 `https://api.deepseek.com` 和 `deepseek-flash`；配置 SHA256 为 `ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`。实验结束后已按本机备份恢复 `config.yaml`。

服务探针三项通过：运行回复 1 token、无参数工具调用 21 token、评委回复 1 token；三项返回模型名均为 `deepseek-flash`，`reasoning_tokens` 为空。原始记录见 `service-probe.json`。返回模型名是服务端元数据，不能单独证明服务身份。

两个批次各运行 18 题，共 36 条；评委各评分 18 次，没有未评分记录。Single 提交 14/18（另有 3 条 `ask_user`、1 条 `retry_limit`）；pipeline 提交 18/18。Pipeline 共修复 3 次、降级 1 条。Campaign 状态为 complete；每个 job 退出码为 1，表示存在质量/断言失败，不表示运行中断。

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 提交 | 14/18 | 18/18 |
| 已提交且质量通过 | 8/14（57.1%） | 13/18（72.2%） |
| 评委输出 token 中位数（每行 / 每次评委请求） | 327.5 / 327.5 | 388.5 / 388.5 |
| 运行模型输出 token 中位数（每行 / 每次模型响应） | 2590 / 135.5 | 683 / 682 |
| 运行时长中位数 | 17.83 秒 | 5.96 秒 |
| 运行模型调用数 | 124 | 21 |
| 评委请求数 | 18 | 18 |
| `no_fabricated_facts` 失败（已提交） | 6 | 1 |

运行模型逐次响应 token 中位数从 trace 的 `model_response` 事件计算；评委请求本轮均为每行一次。r15 execution.md 记录的逐次响应中位数为 single 137、pipeline 732；本轮为 135.5、682。以下表格沿用 r15 review §2.2 的另一种算法：每行运行输出除以该行调用数，再对行取中位数，不能与逐次响应中位数混用。

| 可比指标 | r13 Single | r15 Single | r16 Single | r13 Pipeline | r15 Pipeline | r16 Pipeline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 评委每行输出 token 中位数 | 356.5 | 356 | 327.5 | 337 | 386 | 388.5 |
| 每行运行输出 / 调用数的中位数 | 412 | 368 | 411.4 | 691 | 710 | 679.5 |
| 运行耗时中位数（秒） | 34.0 | 13.8 | 17.83 | 8.9 | 6.0 | 5.96 |

两组 source-hashes 的 184 项相同；除实验配置外的 183 项逐文件与 `5640889` 的 Git 内容一致，源码指纹重算一致：`05138a2ad01f20f0cfe2c264ee7d8018528761d66073e5f4fe500f46516b2007`。36 条 trace 文件均存在，raw 与 trace 哈希已复核。修复证据包含 4 份被拒稿件（其中投资 #3 两份），3 组修复请求。

`fabrication-reviewed.yaml` 不存在负责人逐条判定。本轮计数表因此保留待判：single 有 6 条编造失败，初筛为 0 条事实、1 条叙述、5 条待复核；pipeline 有 1 条，初筛为事实类。初筛不是最终归因；没有用它替代人工判定。评委另有 supported-conclusion、time-consistent 和 direct-answer 失败，详见 `quality-reasons.md` 与 `Bazi-*-summary.json`。这些评分来自同一个模型，未做独立人工校准。

费用未知：`pricing.yaml` 没有官方费率。执行后恢复的个人配置哈希为 `5dd4e29337070841a6acd8facd9f3548aad500b4ededb9c2046bd975ef1c91fd`；个人配置备份在本机 `reports/config.personal.before-r16.yaml`，未发布。更新分支前对个人配置另作了单文件 stash，作为额外可恢复副本，未删除。

附加离线测试未获得通过结果：恢复个人配置后运行 `tests/pipeline/test_bazi_pilot_r16.py`，其 fixture 首项返回 `model_error` 而不是 `submit_reading`。测试使用根目录个人配置；该次执行不能作为纯净配置下的代码回归结论。此前缺少 swisseph 的问题在本轮项目 `.venv` 中未出现。本轮 campaign 与报告已完整结束，没有因该附加测试重跑实验。

可复核材料包括两组 summary、source hashes、raw manifest、trace manifest、36 条完整回答、repair evidence/quotes、质量原因和 pipeline 问题。`evidence-manifest.json` 列出发布文件的 Git 规范化字节哈希；manifest 自身不纳入清单。
