# P3 星盘 r3 调参实验执行记录

- 执行时间：2026-11-08 12:02:40 至 12:30:49（Asia/Shanghai），约 28 分 8 秒。
- 被测提交：`18df682dd0905c2d2615aaeb13edc764fc84740a`，PR #57 合并并完成离线修复后的代码。
- 按负责人截图执行 `p3-astro`：调参集 6 题，single 与 pipeline 各重复 3 次，串行完成 36 条。
- 配置使用 r1 本机保存的原始实验文件，SHA256 精确匹配约定的
  `248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`。
  `pipeline.systems` 为 `[tarot, dream, name, daily, astro]`，不是 r2 的 `[tarot, astro]`。
- 临时替换主工作区配置前已保存字节备份，结束后恢复；原配置 SHA256 为
  `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`，恢复后相同。
- 两组 179 项源码哈希完全相同，178 个非配置文件与被测 Git 提交逐字节一致；指纹为
  `29c86c98e95dfa223dc70c95f518946c350bb9d46f15dac071d206c5c54a073e`。
- 36/36 条完成四维评分，18 对 repeat/id 一致，36 份原始 trace 存在并计哈希。
- 运行与评分均请求并返回 `deepseek-v4.1-flash`；`--judge pro` 是配置角色名，不代表不同模型。
  同模型评审未经独立人工校准。中转费率未核实，沿用 `models: {}`，费用未知。
- 两个子批次退出码均为 1，表示存在评测断言失败；完整报告各 18 行，campaign 退出码为 0、状态 complete。
- 未改产品实现、提示词、校验器、题目、rubric；未补跑、重评或替换失败样本。本轮不冻结代码、不运行最终验收集，等待负责人复核。

## 命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-astro --root reports/p3-astro-r3 --snapshot . --baseline . --publish docs/verification/p3/astro-pilot-r3
```

本机 `reports/run_astro_r3.py` 只包装约定配置的哈希核对、临时替换、元数据记录和结束恢复，campaign 行为不变。
本机原始报告、配置备份、运行日志与 trace 保留于 `reports/p3-astro-r3`，凭据不发布。

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-astro-r3/Astro-single reports/p3-astro-r3/Astro-pipeline --counts-only --reviewed reports/p3-astro-r3/fabrication-reviewed.yaml --output docs/verification/p3/astro-pilot-r3/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-astro-r3/Astro-pipeline --output docs/verification/p3/astro-pilot-r3/pipeline-problems-raw.md
```

编造失败分类由 Codex 阅读原始回答、结构化字段、计算事实与评委理由完成，不是负责人逐条裁决或独立人工校准。
计数表的“完整”只描述评分与分类覆盖；原始评分保持不变。分类输入和逐条依据随结果发布。

## 发布材料

- [assessment.md](assessment.md)：同批指标、局限和待复核事项。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-attribution.md](fabrication-attribution.md)、[fabrication-reviewed.yaml](fabrication-reviewed.yaml)：两组编造计数及分类依据。
- [repair-attribution.md](repair-attribution.md)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json)：全部 6 次修复的原文、问题与实际引句。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：全部 36 条回答及原始评委结果。
- [integrity.json](integrity.json)、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)：源码、配对、报告与证据文件核验。
