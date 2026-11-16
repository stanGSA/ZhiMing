# r20 官方 DeepSeek 实验记录

北京时间 2026-11-17 00:38:42—00:47:16（UTC 2026-11-16 16:38:42—16:47:16），在 `D:\知命` 的 `claude_modify_model` 分支、PR #82 合并提交 `374d5855b4733fd87166d4474e7d9a7bb6ae0fe6` 上完成。本轮为 6 道合成题 × 3 次重复 × 两种模式，共 36 次请求；不是 36 道独立题。

接入为官方 `https://api.deepseek.com`；运行与评委均为 `deepseek-flash`，评委别名 `pro`、thinking=disabled、未设 reasoning_effort、max_tokens=8192。运行回复、工具调用、评委回复三项探针均通过，输出分别 1、21、1 token。请求和返回模型名一致；返回模型名为服务端元数据，不是独立身份验证。trace 未提供 reasoning_tokens 数值，不把缺失值当作 0。官方当前单价未核实，费用未知；pricing.yaml 与 r19 逐字节一致。

实验配置按 CRLF 还原，SHA-256 为 `ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`。原个人配置已逐字节恢复，SHA-256 为 `5dd4e29337070841a6acd8facd9f3548aad500b4ededb9c2046bd975ef1c91fd`；备份在本机 `reports/config.personal.before-r20.yaml`，不纳入发布。旧 r18 同名未跟踪文件单独保存在 `reports/r20-preflight-20261117T003525/untracked-overlap/`，其他既有文件保留。

命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r20 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r20
```

campaign 状态 complete，退出码 0；子任务的退出码 1 表示评测中存在失败，两个子任务均完成 18/18。Single run_id 为 `20261116T163844-b9aafb89`，Pipeline 为 `20261116T164415-7f575b38`。没有补跑、替换失败、重评、修改回答或改动被测源码、题目、rubric。

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 请求 / 已评分 | 18 / 18 | 18 / 18 |
| 提交 | 14/18 | 18/18 |
| 已提交质量通过 | 10/14（71.4%） | 13/18（72.2%） |
| 任务完成且质量通过 | 10/18 | 13/18 |
| 严格综合通过 | 8/18 | 13/18 |
| 工程检查通过 | 12/18 | 18/18 |
| 运行调用总数 / 每题平均 / 最大 | 107 / 5.94 / 9 | 21 / 1.17 / 2 |
| 评委评分行 / 请求尝试 | 18 / 18 | 18 / 19 |
| 修复 / 降级 | — | 3 / 0 |
| 运行输出 token 中位数（每行输出÷该行调用数，再取中位数） | 395.225 | 653 |
| 评委输出 token 中位数（每行） | 367 | 375 |
| 运行耗时中位数 / P95（秒） | 12.847 / 27.300 | 6.309 / 10.285 |
| 评委耗时中位数（秒） | 2.959 | 3.236 |
| 每题运行输入 token，平均（不含评委） | 37,987.7 | 5,416.7 |
| 每题评委输入 token，平均 | 10,415.5 | 13,464.5 |
| 每题合计输入 token，平均（含评委） | 48,403.2 | 18,881.2 |
| 每题运行输入 token，中位数（不含评委） | 34,745 | 4,871.5 |
| 每题合计输入 token，中位数（含评委） | 39,574.5 | 15,280.5 |
| 缓存命中率（运行） | 75.2% | 83.6% |

耗时包含澄清，不含准备和 rubric 评分；评委另列。token 取报告记录的 usage，运行输入为同一请求全部运行调用的输入之和，包含重复上下文；不把报告顶层含评委总量误作运行量。上述运行输出中位数也不是把全部模型响应混在一起取中位数。Pipeline 评委额外一次请求尝试为原始运行自动重试，未离线重评。配对指标为“任务完成且质量通过”：Pipeline 胜 4、Single 胜 1、平 13。

两组 184 个源码文件哈希完全相同，指纹均为 `648b998b6ec4b8eed7a883852604f89c0d46b70d2004034d96ac1263e35eec35`；除约定实验 config.yaml 外，全部逐字节对应被测提交。两份 live.json 的 raw-manifest、36 份 trace 的 SHA-256、36 份全文与 3 份修复首稿均已核对。源码指纹使用实验时工作区原始字节；evidence-manifest 使用 Git 暂存区字节，因此文本的换行归一化会导致二者的 config 哈希口径不同。

按截图生成质量理由、分类表、问题清单、修复证据及 staged evidence-manifest。分类依据见 [fabrication-attribution.md](fabrication-attribution.md)：六条分类由 Codex 离线提出，负责人已在本会话回复“确认上述分类”；两组计数表完整。此确认不构成独立人工校准。原始 reports、trace、数据库与执行日志保留本机；发布目录保留全部 36 份回答及复核所需事实、3 份未展开原稿与修复引句。本轮未冻结，也未启动 `p3-bazi-final`。
