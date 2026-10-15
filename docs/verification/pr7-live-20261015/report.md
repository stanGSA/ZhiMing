# 新旧版本回复对照

- old-single：provider=openai，model=gpt-6.1-sol，日历基准=2026-10-15，seed=42
  代码版本=9eccedbce15e5138c4dcf863d5df66c685cd6eb8，dirty=False，版本读取错误=无记录
- new-single：provider=openai，model=gpt-6.1-sol，日历基准=2026-10-15，seed=42
  代码版本=545eb01342681c39564ccb8cec841424f6a4b6c4，dirty=False，版本读取错误=无记录
- old-multi：provider=openai，model=gpt-6.1-sol，日历基准=2026-10-15，seed=42
  代码版本=9eccedbce15e5138c4dcf863d5df66c685cd6eb8，dirty=False，版本读取错误=无记录
- new-multi：provider=openai，model=gpt-6.1-sol，日历基准=2026-10-15，seed=42
  代码版本=545eb01342681c39564ccb8cec841424f6a4b6c4，dirty=False，版本读取错误=无记录

| 指标 | old（single） | new（single） | old（multi） | new（multi） |
|---|---|---|---|---|
| turns | 10 | 10 | 10 | 10 |
| submitted | 9 | 9 | 9 | 8 |
| avg_reply_chars | 696 | 1402 | 523 | 1317 |
| avg_analysis_chars | 258 | 1270 | 227 | 1191 |
| avg_evidence_share | 0.564 | 0.111 | 0.524 | 0.098 |
| layered_turns | 0 | 9 | 0 | 8 |
| rejections | 3 | 2 | 3 | 1 |
| fact_rejections | 2 | 1 | 1 | 1 |
| expression_rejections | 0 | 1 | 0 | 0 |
| safety_rejections | 0 | 0 | 0 | 0 |
| schema_rejections | 0 | 0 | 0 | 0 |
| review_rejections | 0 | 0 | 0 | 0 |
| disclosure_rejections | 0 | 0 | 1 | 0 |
| other_rejections | 1 | 0 | 1 | 0 |
| unclassified_legacy_rejections | 0 | 0 | 0 | 0 |
| resubmitted_turns | 2 | 1 | 2 | 0 |
| review_revise | 0 | 0 | 0 | 0 |
| followup_recompute | 0 | 0 | 1 | 1 |
| clarified | 1 | 1 | 1 | 1 |

## 逐题

| 题目 | 版本 | 状态 | 回复字数 | 正文字数 | 依据占比 | 层数 | 提交/拒绝 | 审校 | 警告 | 追问重算 |
|---|---|---|---|---|---|---|---|---|---|---|
| bazi-month-1 | old-single | ask_user | 136 | 0 | None | 0 | 1/1 | - | 0 | - |
| bazi-month-1 | new-single | submit_reading | 1865 | 1670 | 0.118 | 4 | 3/2 | - | 0 | - |
| bazi-month-1 | old-multi | ask_user | 85 | 0 | None | 0 | 0/0 | - | 0 | - |
| bazi-month-1 | new-multi | ask_user | 121 | 0 | None | 0 | 0/0 | - | 0 | - |
| bazi-month-2 | old-single | submit_reading | 348 | 183 | 0.386 | 0 | 2/1 | - | 0 |  |
| bazi-month-2 | new-single | submit_reading | 987 | 814 | 0.042 | 2 | 1/0 | - | 0 |  |
| bazi-month-2 | old-multi | submit_reading | 427 | 151 | 0.596 | 0 | 1/0 | pass | 0 | consult_specialist,compute_bazi,consult_specialist |
| bazi-month-2 | new-multi | submit_reading | 1363 | 1175 | 0.081 | 3 | 1/0 | pass | 0 | consult_specialist,compute_bazi,consult_specialist,compute_bazi,consult_specialist |
| bazi-timing-1 | old-single | submit_reading | 933 | 425 | 0.505 | 0 | 1/0 | - | 0 | - |
| bazi-timing-1 | new-single | submit_reading | 1442 | 1319 | 0.169 | 3 | 1/0 | - | 0 | - |
| bazi-timing-1 | old-multi | submit_reading | 636 | 307 | 0.457 | 0 | 1/0 | pass | 0 | - |
| bazi-timing-1 | new-multi | submit_reading | 1894 | 1766 | 0.141 | 4 | 1/0 | pass | 0 | - |
| astro-trait-1 | old-single | submit_reading | 690 | 187 | 0.699 | 0 | 1/0 | - | 0 | - |
| astro-trait-1 | new-single | submit_reading | 1557 | 1444 | 0.1 | 4 | 1/0 | - | 0 | - |
| astro-trait-1 | old-multi | submit_reading | 788 | 348 | 0.607 | 0 | 1/0 | pass | 0 | - |
| astro-trait-1 | new-multi | submit_reading | 1486 | 1373 | 0.146 | 4 | 1/0 | pass | 0 | - |
| astro-timing-1 | old-single | submit_reading | 1233 | 436 | 0.612 | 0 | 2/1 | - | 0 | - |
| astro-timing-1 | new-single | submit_reading | 2203 | 2054 | 0.161 | 5 | 1/0 | - | 0 | - |
| astro-timing-1 | old-multi | submit_reading | 674 | 305 | 0.487 | 0 | 1/0 | unavailable | 0 | - |
| astro-timing-1 | new-multi | limit_reached | 41 | 0 | None | 0 | 0/0 | - | 0 | - |
| tarot-three-1 | old-single | submit_reading | 407 | 172 | 0.518 | 0 | 1/0 | - | 0 | - |
| tarot-three-1 | new-single | submit_reading | 1108 | 1004 | 0.1 | 3 | 1/0 | - | 0 | - |
| tarot-three-1 | old-multi | submit_reading | 374 | 128 | 0.605 | 0 | 1/0 | pass | 0 | - |
| tarot-three-1 | new-multi | submit_reading | 1180 | 1076 | 0.043 | 3 | 1/0 | pass | 0 | - |
| tarot-three-2 | old-single | submit_reading | 293 | 136 | 0.46 | 0 | 1/0 | - | 0 |  |
| tarot-three-2 | new-single | submit_reading | 788 | 692 | 0.132 | 2 | 1/0 | - | 0 |  |
| tarot-three-2 | old-multi | submit_reading | 372 | 210 | 0.36 | 0 | 1/0 | - | 0 |  |
| tarot-three-2 | new-multi | submit_reading | 621 | 543 | 0.061 | 2 | 1/0 | - | 0 |  |
| tarot-decision-1 | old-single | submit_reading | 481 | 198 | 0.541 | 0 | 1/0 | - | 0 | - |
| tarot-decision-1 | new-single | submit_reading | 1207 | 1100 | 0.037 | 3 | 1/0 | - | 0 | - |
| tarot-decision-1 | old-multi | submit_reading | 460 | 188 | 0.541 | 0 | 1/0 | pass | 0 | - |
| tarot-decision-1 | new-multi | submit_reading | 1165 | 1061 | 0.038 | 3 | 1/0 | pass | 0 | - |
| combined-timing-1 | old-single | submit_reading | 1323 | 444 | 0.638 | 0 | 1/0 | - | 0 | - |
| combined-timing-1 | new-single | model_error | 21 | 0 | None | 0 | 0/0 | - | 0 | - |
| combined-timing-1 | old-multi | submit_reading | 610 | 271 | 0.497 | 0 | 2/1 | pass | 0 | - |
| combined-timing-1 | new-multi | submit_reading | 1480 | 1358 | 0.156 | 3 | 1/0 | pass | 0 | - |
| daily-1 | old-single | submit_reading | 555 | 139 | 0.72 | 0 | 1/0 | - | 0 | - |
| daily-1 | new-single | submit_reading | 1460 | 1337 | 0.138 | 3 | 1/0 | - | 0 | - |
| daily-1 | old-multi | submit_reading | 362 | 133 | 0.565 | 0 | 2/1 | pass | 0 | - |
| daily-1 | new-multi | submit_reading | 1350 | 1173 | 0.119 | 3 | 1/0 | pass | 0 | - |

## 解释与人工阅读

详见 [合并后修复报告](../../pr7-合并后校验修复.md)。`submitted` 只表示成功提交结构化结果，不代表完整满足用户要求：新旧 multi 的 combined-timing 均只完成八字部分。依据占比来自结构化正文与 evidence 文本长度，不是屏幕占比；事实拒绝次数只计 submit_reading/submit_report 校验，不包括预算、网络和所有计算工具错误。

每个子目录的 results.json 保存固定合成资料、完整最终回复、结构化输出、工具与指标。原始 trace 和运行时数据留在本机 reports 目录，不随文档提交。可用 compare_layers.py report 对四个子目录重新生成指标。

PR #8 截图评审后，此表用当前分类器对原始 code/error 重新分类。results.json 中的 category 保留采集时值；模型回复、调用状态与字数未改，也未重新调用模型。
