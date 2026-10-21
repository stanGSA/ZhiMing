# 释义审核账本

这里存放知识条目的**模型交叉审核**通过记录，每个体系一个 `<system>.yaml`。账本不记录人工审核：人工审核只用源文件里的 `reviewed: true` 表示，任何代码与脚本都不写这个字段。

- 每条记录按条目 `id` 与条目内容的 SHA256（`knowledge/review.py` 的 `content_hash`）绑定。条目内容（包括 `theme_map` 数值）一改，哈希不再匹配，条目自动回到 `draft`；重新运行 `scripts/draft_*.py` 不会改动账本。
- 只有两家不同厂商的审核模型都判 `pass` 的条目才写入账本，状态为 `model_reviewed`。任一家判 `revise` 或 `reject` 的条目不写入，保持 `draft`，进入修改队列。
- 账本文件参与知识库版本摘要：审核状态变化会产生新的知识库版本，旧 reading 继续引用旧版本快照。
- 账本由 `scripts/model_review_kb.py` 根据审核批次的合并结论生成，原始输出存于 `docs/verification/kb-model-review/`。
- 复审对相同内容哈希给出否决时先撤销旧批准，即使本批校准失败或尚未完成；新增批准仍须满足校准要求。撤销证据存为批次内的 `ledger_revocations.json`。
- 已修订源文件是内容依据。`draft_week23.py`、`draft_week6.py` 发现源文件与旧模板不一致时拒绝覆盖；内容一致时保持文件字节不变。不要删除修订源文件后重跑旧模板来恢复批准。
- `apply` 先校验整个候选体系的同义词与其他条目key/同义词是否冲突，再写入源文件；单条修改稿通过并不表示跨条目的唯一性已经通过。
- 本次负责人确认的体系级验收使用 `python -m scripts.kb_review_campaign --run-root <活动目录> --output <活动目录>/campaign --write-ledger`。脚本自动发现活动目录下全部初审及复审 manifest，保留失败版本与失败样本；通过率按当前内容哈希的最后一份完整双模型两轮结论计算。后续同哈希否决先撤销批准，不因后续批次校准失败而保留旧批准。
- 体系级 kappa 按全部批次第一轮的真实及埋错样本计算，分类为放行（pass）／不通过（revise、reject），阈值仍为0.6。这是负责人明确批准的口径变更；埋错样本会改变分布，报告同时保留真实条目三分类、全部样本三分类 kappa 和各批原始指标，不能直接比较不同口径的数值。第二轮用于计算重跑一致率。
- 体系汇总脚本会在活动目录写入 `campaign-acceptance.json`。此后 `model_review_kb ledger` 拒绝逐批写入该目录下的批次：单个小批次可能自身校准达标，但不代表体系校准达标。体系校准未达标时，`--write-ledger` 还会撤销该体系当前内容的全部已有批准，不论是哪个命令写入的。
- 体系校准未达标时，即使当前内容获得四次 pass，也只记录双审候选，不新增模型审核批准。汇总中的 `candidate_count` 与实际账本的 `model_reviewed_count` 必须分开，正式三态覆盖率以重新构建结果为准。

```yaml
schema_version: 1
system: tarot
records:
- id: kb:tarot:card:the_fool:upright
  content_sha256: <64 位十六进制>
  reviewers:
  - {vendor: <厂商>, model: <请求的模型名>, returned_model: <服务返回的模型名>, verdict: pass, issues: []}
  - {vendor: <另一家厂商>, model: ..., returned_model: ..., verdict: pass, issues: []}
  date: 2026-10-21
  report: docs/verification/kb-model-review/<批次目录>/report.md
```
