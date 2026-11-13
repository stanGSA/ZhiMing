# r13 复核补发

本次按 r12 的证据范围，补齐两组各 18 份运行输出全文，以及被检稿件和修复引文。数据直接取自本机已完成的 r13 `live.json` 和 trace；没有重新运行实验、调用模型或修改原评分。本次补发供继续复核，既有归因和结论仍以原记录为准，不因补发自动视为已完成复核。

| 文件 | 内容 |
| --- | --- |
| [supplement-answers.md](supplement-answers.md) | 全部 36 份最终输出全文，包括 30 份提交答案、4 份追问和 2 份 retry_limit 回复；按组、题号和重复次序排列 |
| [supplement-answers.json](supplement-answers.json) | 相同 36 行的完整原始结果，保留 `answer`、`structured`、`calculated_facts`、`quality_review`、usage、工具错误及 trace 路径；另附组名、run_id、来源哈希和一基重复编号 |
| [repair-evidence.json](repair-evidence.json) | 沿用 r12 的数组格式，包含 5 份被检稿件的展开全文及其原始问题列表，共 9 条问题 |
| [repair-quotes.json](repair-quotes.json) | 沿用 r12 的数组格式，包含 4 条修复样本的全部 `problems` / `repair` trace 事件，保留原始稿、展开稿和 4 次修复的 quotes 映射 |

`supplement-answers.json` 中 `repeat` 与原报告一致，从 0 开始；新增 `repeat_number` 从 1 开始。Markdown 和两个 repair 文件的重复编号均从 1 开始。`repair-evidence.json` 的 `text` 取 trace 的 `rendered_text`，与 r12 一致；未展开的原稿仍可在 `repair-quotes.json` 对应事件的 `text` 中找到。最终修复结果或关键词降级稿均在 36 份输出中，不用被拒稿替代最终回复。

原始报告哈希按 [raw-manifest.json](raw-manifest.json) 验证；36 条 trace 均按 [trace-manifest.json](trace-manifest.json) 验证。JSON 中的回答、结构、计算事实、评分和事件均与来源逐字段一致。Markdown 仅整理换行和空白，JSON 保留原字符串。新增文件已加入 [evidence-manifest.json](evidence-manifest.json)。本机原始报告与 trace 未改动。
