# 释义审核账本

这里存放知识条目的**模型交叉审核**通过记录，每个体系一个 `<system>.yaml`。账本不记录人工审核：人工审核只用源文件里的 `reviewed: true` 表示，任何代码与脚本都不写这个字段。

- 每条记录按条目 `id` 与条目内容的 SHA256（`knowledge/review.py` 的 `content_hash`）绑定。条目内容（包括 `theme_map` 数值）一改，哈希不再匹配，条目自动回到 `draft`；重新运行 `scripts/draft_*.py` 不会改动账本。
- 只有两家不同厂商的审核模型都判 `pass` 的条目才写入账本，状态为 `model_reviewed`。任一家判 `revise` 或 `reject` 的条目不写入，保持 `draft`，进入修改队列。
- 账本文件参与知识库版本摘要：审核状态变化会产生新的知识库版本，旧 reading 继续引用旧版本快照。
- 账本由 `scripts/model_review_kb.py` 根据审核批次的合并结论生成，原始输出存于 `docs/verification/kb-model-review/`。
- 复审对相同内容哈希给出否决时先撤销旧批准，即使本批校准失败或尚未完成；新增批准仍须满足校准要求。撤销证据存为批次内的 `ledger_revocations.json`。
- 已修订源文件是内容依据。`draft_week23.py`、`draft_week6.py` 发现源文件与旧模板不一致时拒绝覆盖；内容一致时保持文件字节不变。不要删除修订源文件后重跑旧模板来恢复批准。

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
