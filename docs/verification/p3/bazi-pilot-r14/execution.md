# P3 八字调参集 r14 执行记录

| 项目 | 内容 |
| --- | --- |
| 被测提交 | `e9b8e9071315904561ecfdf00eacfc9595fee7f4`（PR #73 合并提交） |
| 源码指纹 | `2a974a96ed903255910bca94169680c088fd71a74ac4f735ccff4aad4af60b68`，183 项 |
| 实验配置 | `reports/p3-bazi-r9/config.experiment.yaml`，SHA256 `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b` |
| 本机个人配置 | 运行前后均为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24` |
| 模型 | 运行请求/返回 `deepseek-v4.1-flash`；评委请求/返回 `deepseek-v4.1-flash` |
| 评委设置 | `thinking=disabled`，`max_tokens=8192`，未传 `reasoning_effort`；客户端设置见 [judge-request-options.json](judge-request-options.json) |
| rubric | `v2-2026-10-24`，judge role `pro` |
| 样本 | 6 题 × 3 次重复 = 每组 18 行 |
| 定价文件 | [pricing.yaml](pricing.yaml)，与 r13 逐字节相同；中转站费率未提供，费用未知 |

北京时间 2026-11-13 18:37:17 至 19:24:35。先跑 single，再跑 pipeline；campaign 总退出码 0，两组子任务因存在失败结果各退出 1，均生成完整 18 行报告。运行时临时使用约定配置，`finally` 恢复原个人配置；恢复后哈希与备份一致。

| 组 | run_id | 行数 | 已提交 | 已评分 | 质量通过 | 工程通过 | 调用最多 | 原始报告 SHA256 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Bazi-single | `20261113T103718-0f673755` | 18 | 0 | 10 | 0 | 0 | 12 | `b74cb904ed24fb8e09f2b64369713ce6602050a5f0fe2856d5de047af0a68f26` |
| Bazi-pipeline | `20261113T105622-43845d42` | 18 | 18 | 18 | 17 | 17 | 2 | `9c629a124a1b8f6f0e34f3bfc9b5c3ac7a0e222d099698e748b60aef0b1c07a7` |

single 的 18 条全部未完成提交，10 条有评委评分，8 条未评分；single 样本出现执行步数上限、模型错误和 `get_profile` 的 `_placeholder` 参数 schema 错误。pipeline 有一条提交工程检查失败（标题长度），但修复后最终提交；一条质量失败（海外题 `supported_conclusion=false`）。原始评分与失败回复全部保留，没有补评、重跑或修改答案。

## 复现命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r14 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r14
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r14/Bazi-single reports/p3-bazi-r14/Bazi-pipeline --answers --output reports/p3-bazi-r14/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r14/Bazi-single reports/p3-bazi-r14/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r14/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r14/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r14/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r14/pipeline-problems-raw.md
```

两组已评分结果中，没有提交答案的 `no_fabricated_facts=false` 行；single 无提交答案，pipeline 18 份中该维度均通过。归因文件因此为空分类表，不代表其他质量维度没有失败。完整 36 行回答和评分、pipeline 被检稿件及修复事件见本目录相应证据文件。单次实验不构成稳定性结论；运行与评委同模型、同厂商，评委不是独立人工评审。
