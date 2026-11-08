# P3 星盘 r4 调参实验执行记录

- 时间：2026-11-08 18:26:14 至 18:58:38（Asia/Shanghai），约32分24秒。
- 被测提交：PR #58 head `dfbc2dba01335b571f41afa207d07e5296d5c7b9`。
- 在隔离 worktree `C:/Users/Stan/.codex/worktrees/review-pr-58/知命` 上执行；实验运行时 PR 尚未合并。
  负责人随后合并 PR #58，合并提交为 `d7c3ff89f6e39f48f41038be781e85e7fdbd0cf1`；
  发布结果前再次核对，178个非配置源码文件与合并后版本逐字节一致。
- 按负责人截图执行 `p3-astro`，6道调参题，single 与 pipeline 各3次，串行完成36条。
  `--snapshot . --baseline .` 使用同一 PR 代码，比较两种运行模式。
- 实验配置直接取 r3 保存的原始字节，SHA256 与约定精确一致：
  `248e6db07c2c5d82240d20beaa32bfe55a6d31301ca2d3f64a9b659dd57acb9c`。
  `pipeline.systems` 为 `[tarot, dream, name, daily, astro]`。
- 工作区配置运行前备份、结束后恢复，恢复后SHA256为
  `909824cf6261c4d0b65b1a5334d5f4b7f8ad111140def050e3341cfa6f6a12ad`。
- 主工作区 `D:/知命/config.yaml` 全程未改动，SHA256仍为
  `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。
- 两组179项源码哈希相同，178个非配置文件与被测提交逐字节一致；指纹为
  `1b96414d8332a4c3388150b99d6992d94117296a13030fe0f99ba1dc0a5ff53c`。
- 36/36条完成四维评分，18对 repeat/id 匹配，36份原始 trace 存在并计哈希。
- 运行和评分请求、返回模型均为 `deepseek-v4.1-flash`。
  `--judge pro` 是配置角色名；本次实际为同一模型评分，未经独立人工校准。
- 中转费率未知，沿用 `models: {}`，费用记未知。
- 两个子批次退出码均为1（存在断言失败），完整报告各18条；campaign 退出码0、状态complete。
- 没有修改产品代码、提示词、校验器、题目、rubric，没有补跑、重评或替换失败样本。
  未运行最终验收集，未冻结代码。实验完成后按负责人要求，将本目录结果提交到 `claude_modify_model` 发布。

## 命令

在上述 worktree 中，使用主工作区 Python 3.11 虚拟环境执行截图中的参数：

```powershell
D:\知命\.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-astro --root reports/p3-astro-r4 --snapshot . --baseline . --publish docs/verification/p3/astro-pilot-r4
```

本机 `reports/run_astro_r4.py` 只包装配置哈希检查、凭据环境载入、源码提交检查、元数据记录和配置恢复。
凭据没有复制到 worktree，也没有写入发布材料。

```powershell
D:\知命\.venv\Scripts\python.exe -X utf8 -m reports.finalize_astro_r4
D:\知命\.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-astro-r4/Astro-single reports/p3-astro-r4/Astro-pipeline --counts-only --reviewed docs/verification/p3/astro-pilot-r4/fabrication-reviewed.yaml --output docs/verification/p3/astro-pilot-r4/fabrication-counts.md
D:\知命\.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-astro-r4/Astro-pipeline --output docs/verification/p3/astro-pilot-r4/pipeline-problems-raw.md
```

编造分类由 Codex 离线读取原始回答与计算事实后完成；不是负责人逐条裁决或独立人工校准。
发布文本统一为LF换行，并重新生成发布文件哈希清单；原始报告与trace字节及其哈希未改动。
原始评分保留，分类依据和疑点见 [fabrication-attribution.md](fabrication-attribution.md)。

## 材料位置

原始报告、配置备份、日志和 trace 保留在该 worktree 的 `reports/p3-astro-r4`。
为便于从主工作区查看，同内容副本保存到 `D:/知命/reports/p3-astro-r4`，发布材料副本保存到
`D:/知命/docs/verification/p3/astro-pilot-r4`。原始报告中的绝对 trace 路径仍指向实际执行 worktree，未改写报告。

- [assessment.md](assessment.md)：指标、r3比较、评分局限。
- [repair-attribution.md](repair-attribution.md)、[repair-evidence.json](repair-evidence.json)、[repair-quotes.json](repair-quotes.json)：全部修复及引句。
- [fabrication-counts.md](fabrication-counts.md)、[fabrication-reviewed.yaml](fabrication-reviewed.yaml)：两组编造分类计数。
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md)：36条原始回答与评委理由。
- [integrity.json](integrity.json)、[raw-manifest.json](raw-manifest.json)、[trace-manifest.json](trace-manifest.json)、[evidence-manifest.json](evidence-manifest.json)：完整性证据。
