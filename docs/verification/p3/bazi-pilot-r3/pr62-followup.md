# PR #62 合并后的修复与离线验证

PR #62 已合并到 `claude_modify_model`，合并提交为 `75e1c60`。本次修复处理审查中发现的降级稿容量问题，并补齐日期边界和原始失败稿的回归覆盖。没有调用真实模型，也不据此宣称满足 B 或冻结。

## 修复

- 降级稿先按类别和完整句子分层；超过 6 层时，允许相邻类别共用一层，并同步合并标题和引用。避免很短的日主、四柱等段落占满层数，挤掉后面的关系事实。每层仍不超过 1200 字。
- 如果完整句子仍装不下，正文不截断句子，建议中明确说明有多少项依据未展开；全部依据仍保留在 evidence 中。
- 高风险降级稿第一句直接说明不能依据八字作重大现实决定。撰写提示词明确禁止从八字推出股票仓位、买卖时点或收益判断。
- 右开结束时间只有精确到微秒都是午夜时，才归入前一天；午夜后一微秒仍包含当天。

## 回放与边界覆盖

`tests/pipeline/test_bazi_fallback_capacity.py` 覆盖：

- 原投资题的年度降级稿、三天流日和下个月流月：可展示事实的正文与引用全部保留，层数和长度符合 schema。
- 投资题原有 33 条关系事实从展示 26 条变为全部展示；整份降级稿为 3 层，正文长度分别为 1173、1196、192 字。
- 不可分割的超长总量：如实说明未展示数量，避免静默省略。
- 跨年、按咨询范围区分年份、当地午夜右开边界、洛杉矶夏令时回拨，以及午夜后一微秒。
- r2 投资题两份原稿固化在 `tests/pipeline/fixtures/bazi_pilot_r2_investment_drafts.json`，来源是原发布的 `repair-quotes.json`，未修改题集。展开后第 2 层分别为 985 和 869 字。此测试仅验证原长度问题，不认可原稿中的投资推断。

## 验证环境与范围

本机工作区有用户未提交的 `config.yaml` 改动，且该配置只启用塔罗流水线；未修改、提交该配置。离线测试在使用仓库默认配置和本机既有地名、星历数据的隔离副本中执行，副本覆盖本次全部代码和测试改动。

相关测试命令：

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest tests/pipeline/test_bazi_fallback_capacity.py tests/pipeline/test_bazi_pilot_r3.py tests/pipeline/test_runner_bazi.py tests/pipeline/test_bazi_pilot_r2.py tests/pipeline/test_bazi_title_regressions.py tests/pipeline/test_bazi_closed_set.py tests/plugins/test_bazi_validation.py tests/plugins/test_astro_bazi_calculations.py -q
```

结果：246 passed（167.37 秒）。Ruff 检查与格式检查使用 `.github/workflows/ci.yml` 中的目录范围，均通过（270 个 Python 文件格式符合要求）；`git diff --check` 通过。

上述检查不替代完整真实模型调参实验；r3 后续仍按原约定运行，两组评分覆盖和质量结果需另行验收。r2 原证据文件及两份题集没有改动。
