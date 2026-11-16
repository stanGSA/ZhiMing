# r18 官方 DeepSeek 实验记录

北京时间 2026-11-15 20:04:49 至 20:14:32，在 PR #80 合并提交 `41d3efd1039b2cd7aa605573177e5f616eb28161` 上执行。single 与 pipeline 各运行 6 题、每题重复 3 次；两组及评委均请求官方 `https://api.deepseek.com` 的 `deepseek-flash`，评委别名 `pro`。未重跑样本、补评或改分。

实验配置 SHA-256：`ca6e52b208b6697de7a7b8accc58604eb87e1a89eab582dbc4937c138624bab1`，与 r17 复核指定配置一致。`pricing.yaml` 与 r17 逐字节相同；官方当前费率未核实，费用未知。实验前服务探针三项通过：运行回复 1 token、工具调用 21 token、评委回复 1 token；请求与返回模型均为 `deepseek-flash`，`reasoning_tokens` 为空。返回模型名是服务端元数据，不是独立身份验证。

| 指标 | Single | Pipeline |
| --- | ---: | ---: |
| 样本 / 最终评分 | 18 / 18 | 18 / 18 |
| 提交 | 15/18（另 3 条 ask_user） | 18/18 |
| 已提交且质量通过 | 12/15（80.0%） | 15/18（83.3%） |
| 严格综合通过 | 6/18（33.3%） | 15/18（83.3%） |
| 每题模型调用总数 / 最多 | 113 / 11 | 23 / 2 |
| 评委请求 | 18 | 18 |
| 修复 / 降级 | — | 5 / 0 |
| 运行输入 / 输出 token | 818,008 / 45,322 | 118,141 / 16,780 |
| 每行运行输出 token 中位数 | 2,059 | 757 |
| 每次运行模型响应输出 token 中位数 | 135 | 685 |
| 评委每行输出 token 中位数 | 381 | 355 |
| 运行耗时 P50 / P95（秒） | 15.436 / 41.295 | 6.942 / 13.573 |

评委按题输出的总 token 分别为 6,931 与 6,955。相同题目配对指标“提交且质量通过”：pipeline 胜 5、single 胜 2、平 11，共 18 对；每题重复三次，不是 18 个独立样本。运行与评委均为同一模型，不构成独立人工校准。

源码指纹为 `aceae1461352546d9d3d53608204f52df536f412038f76c0e4d390755caf1a33`，single 与 pipeline 的 184 项 source-hashes 完全相同，除实验配置外按换行规范化核对被测提交。两组 raw 报告（含 36 条结果）及 36 份 trace 的哈希均与 manifest 相符；完整性结果见 `integrity.json`。原始回答与 trace 保存在本机 `reports/p3-bazi-r18/`。

Campaign 状态为 complete。两个 job 退出码均为 1，表示批次内有失败或断言未通过，不表示运行中断。Single 有 2 条 `no_fabricated_facts` 失败，pipeline 有 1 条，负责人分类尚未提供，计数表因此不完整。初步结论见 `assessment.md`。

实验在独立 worktree 执行，原工作区的个人配置未修改。实验 worktree 的配置已按备份逐字节恢复；恢复后 SHA-256 为 `a802e8c261869acfea4994f5953fc8ebd5361db87fb8a7d5aa07b26523dedbc3`。发布的 `config.experiment.yaml` 为 LF，转为 CRLF 后的哈希与运行配置 `ca6e52b2…` 一致。
