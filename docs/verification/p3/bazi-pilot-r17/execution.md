# r17 官方 deepseek-flash 执行记录

北京时间 2026-11-15 05:29:05 至 05:37:45，在 PR #78 合并提交 `82619a936a7c2afa3c38f67343d28b76d113ffde` 上按 r16 复核 §7 的方案执行。使用官方端点 `https://api.deepseek.com`，single、pipeline 和评分评委均请求 `deepseek-flash`，评委别名 `pro`。没有重跑样本、补评或修改评分。实验结束后按备份逐字节恢复个人 `config.yaml`。

实验配置 SHA256：`ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`。从 r16 发布配置按 CRLF 恢复并在开跑前断言；发布副本 `config.experiment.yaml` 入库时为 LF。旧知识库审核角色未被此流程调用。`pricing.yaml` 沿用 r16，官方费率未核实，费用未知。

服务探针三项通过：运行回复 1 token、无参数工具调用 21 token、评委回复 1 token；均返回 `deepseek-flash`，`reasoning_tokens` 为空。运行 trace 的 138 次模型响应全部记录为请求 / 返回 `deepseek-flash`；两组已保存的评委元数据也均为 Flash。返回模型名是服务端元数据，不构成独立身份验证。

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 样本 / 最终已评分 | 18 / 18 | 18 / 18 |
| 提交 | 15/18（另 3 条 ask_user） | 18/18 |
| 已提交且质量通过 | 11/15（73.3%） | 17/18（94.4%） |
| 提交且质量通过 / 全部请求 | 11/18（61.1%） | 17/18（94.4%） |
| 运行模型调用数 / 每题最多 | 118 / 11 | 20 / 2 |
| 评委请求数 | 19 | 18 |
| 修复 / 降级 | — | 2 / 1（keywords） |
| 运行输出 token 中位数（每行 / 每次模型响应） | 2180.5 / 141 | 676 / 653.5 |
| 评委输出 token 中位数（每行 / 每次评委请求） | 362.5 / 无法精确恢复 | 346.5 / 346.5 |
| 运行耗时 P50 / P95（秒） | 15.232 / 31.63 | 5.368 / 10.081 |
| 已提交 no_fabricated_facts 失败 | 3 | 0 |

Single 的文字出生 #1 有一次评委 JSON 解析重试，两次合计 975 个输出 token；现有脚本仅保留这一行的合计 usage，无法拆出两次各自的 token 数。因此单次评委请求的精确中位数未知，在非负整数 token 假设下可确定范围为 351–374。没有用“每行输出除以调用数”的统计替代真实逐次响应中位数，也没有为补此字段重跑评委。两组最终均完成 18 条评分。

以下沿用 r15/r16 review 的另一种算法：对每行“运行输出 / 运行调用数”取中位数，与逐次响应中位数分列。

| 可比指标 | r13 Single | r15 Single | r16 Single | r17 Single | r13 Pipeline | r15 Pipeline | r16 Pipeline | r17 Pipeline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 评委每行输出 token 中位数 | 356.5 | 356 | 327.5 | 362.5 | 337 | 386 | 388.5 | 346.5 |
| 每行运行输出 / 调用数的中位数 | 412 | 368 | 411.4 | 346.625 | 691 | 710 | 679.5 | 653.5 |
| 运行耗时中位数（秒） | 34.0 | 13.8 | 17.83 | 15.232 | 8.9 | 6.0 | 5.96 | 5.368 |

服务端输出规模与 r13、r15、r16 接近，没有已记录的推理正文或输出截断异常。Single 的一次解析重试见上。配对指标为“提交且质量通过”，pipeline 胜 6、single 胜 0、平 12；同一题重复三次，不是 18 个独立样本。同模型评分不构成独立人工校准。

源码指纹 `1b5fcf2c841a40e8ce8c344efd9340d939d1b7664fbc9a72dc7bfc0aedb7d16f`，两组 184 项哈希逐项相同。除实验 config 外的 183 项与被测提交的 Git 内容一致；raw 文件与发布 manifest 对应，36 份 trace 均存在并已计算哈希。详见 `integrity.json`、`raw-manifest.json`、`trace-manifest.json`。`evidence-manifest.json` 以 Git 规范化后的入库字节计算，不包含自身。

Campaign 状态为 complete，两个 job 退出码均为 1，表示存在质量或断言失败，未中断实验。Pipeline 17/18 的评委质量通过里包含投资 #3 的关键词降级；这不能替代对误拒、失答的复核。初步结论仍不满足 B，见 `assessment.md`。

36 份全文与计算事实见 `supplement-answers.json` / `.md`；全部质量失败见 `quality-failures.json`、`quality-reasons-with-answers.md`；3 份被拒稿件和 2 组修复记录见 `repair-evidence.json`、`repair-quotes.json`。

Single 3 条编造评分失败尚无负责人逐条分类，计数表保留待判，未把模型初筛或本次离线分析写成人工判定。Pipeline 编造计数表完整、失败 0。原始评分保留。

个人配置恢复后 SHA256 为 `5dd4e29337070841a6acd8facd9f3548aad500b4ededb9c2046bd975ef1c91fd`；本机备份为 `reports/config.personal.before-r17.yaml`，未发布。此次未修改应用代码，未在恢复后的个人配置上追加离线测试。
