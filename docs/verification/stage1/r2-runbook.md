# 阶段1第二轮知识库审核：本机运行手册

上一轮（2026-10-21）中，八字、姓名、解梦的 kappa 未达标，姓名的重跑一致率也未达标，阶段1知识库验收未通过。原因不是随机波动，而是两家审核方在同一批内容上用了不同的标准。八字：B 要求写出对象专属内容，A 不要求。解梦：B 要求方向有依据、同义词范围要窄。姓名：B 看三才的民间约定写法，A 看数理，而且 A 记错了尾数定五行的规则。上一轮作为失败记录保留，不删除、不重置分母、不降低阈值。

第二轮做了这些改变：

1. **审核规则 v2**（[scripts/kb_review_rubric.py](../../../scripts/kb_review_rubric.py)）：两家共用一套判定锚点，涵盖六项：只认具体问题、方向的依据、对象专属信息、参考事实优先、民间约定的写法、预测。参考事实（藏干、干支关系、十神、尊贵表、宫位主题、尾数五行、数理三档、五行配色、各体系的方向约定）直接取自程序计算用的同一份表，不靠审核员记忆。
2. **平衡的标注校准集**（[确认表](r2-calibration-review.md)）：168 条，各体系约一半合格、一半各含一处真实缺陷。kappa 在这份校准集上计算，避免"九成都判通过"导致 kappa 失真。
3. **运行前登记**：开始调用之前，把规则哈希、审核方、校准集哈希、阈值和 kappa 口径写入 `preregistration.json` 并推送到 GitHub。之后任何批次与登记不符，都不能通过验收。
4. **一键运行**（[scripts/kb_review_live.py](../../../scripts/kb_review_live.py)）：初审 → 修改 → 只复审改过的条目，最多 3 轮；中断后用同一命令续跑，已完成的调用不会重复。

阈值不变：当前内容通过率 ≥95%；埋错检出合并 ≥90%、单家 ≥80%；每家重跑一致率 ≥90%；kappa ≥0.6。

以下命令均在 PowerShell 里、项目根目录（`C:\Users\…\知命`）下执行。

## 第 0 步：准备

```powershell
$env:PYTHONUTF8 = "1"
git fetch origin
git checkout claude/brave-ride-ng806d      # 合并到 main 后改为 git checkout main; git pull
uv sync --locked --extra llm --extra web
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run pytest -q tests/test_kb_review_r2.py tests/test_kb_review_campaign.py
```

检查 `.env` 是否已有这三个变量（只显示有没有，不显示值）：

```powershell
uv run python -c "from dotenv import dotenv_values as v; e=v('.env'); print({k: bool(e.get(k)) for k in ('DEEPSEEK_API_KEY','OPENAI_REVIEW_API_KEY','OPENAI_REVIEW_BASE_URL')})"
```

三个都要是 `True`。**`OPENAI_REVIEW_BASE_URL` 是新增的**：中转站地址不再写在 config.yaml 里，请在 `.env` 加一行 `OPENAI_REVIEW_BASE_URL=https://codegoai.com/v1`（上一轮用的地址）。`.env` 已被 .gitignore 排除，不要提交它。

## 第 1 步：确认校准集

打开 [r2-calibration-review.md](r2-calibration-review.md)，逐行看标签和缺陷说明是否成立。有不同意的，把编号和理由发给我，我修改后重新生成；全部同意就进入第 2 步。

## 第 2 步：冻结校准集

```powershell
uv run python -m scripts.kb_review_calibration freeze `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml `
  --confirmed-by "你的名字"
```

这一步会生成 `calibration.lock.json`，记录哈希、确认人和时间。之后校准集任何改动都会使冻结记录失效。

## 第 3 步：预先登记，并在审核前推送

```powershell
uv run python -m scripts.kb_review_live preregister `
  --run-root docs/verification/kb-model-review/stage1-r2 `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml `
  --decisions docs/verification/kb-model-review/stage1-r2/owner-decisions.json

git add docs/verification/kb-model-review/stage1-r2
git commit -m "docs(stage1-r2): freeze calibration set and preregister the second review"
git push
```

**一定要先推送，再进入第 4 步。** 推送的时间早于任何审核结果，这才能证明口径是事先登记的，而不是看完结果再定的。登记文件不能改写；如果要换审核方、规则或校准集，只能换一个新的活动目录重新登记。

如果想先看预计的调用规模（不发任何请求）：

```powershell
uv run python -m scripts.model_review_kb plan --system tarot `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml
```

上一轮全部六个体系约用了已知输入 206 万、输出 60 万 token。这一轮多了 168 条校准条目，复审轮数取决于结果，预计与上一轮相当或略多。上一轮负责人决定不设预算上限；本轮费用同样未知，不会记为 0。

## 第 4 步：运行审核

```powershell
uv run python -m scripts.kb_review_live run --run-root docs/verification/kb-model-review/stage1-r2
```

- 按顺序处理六个体系：塔罗、占星、八字、姓名、解梦、每日运势。每个体系先初审全部条目（含埋错和校准条目），再由修改方处理被退回的条目，然后只复审真正改过的条目，最多 3 轮。
- 也可以分体系运行：在命令末尾加 `--systems tarot`。
- 预计耗时 1～3 小时。可以随时按 Ctrl+C 中断，再执行同一条命令即可续跑；已完成的调用、修改稿和已应用的修改都不会重复。
- 输出“有调用失败”时（例如网络或接口错误），稍后再执行同一条命令即可，失败不会被算作审核结论。

查看进度：

```powershell
uv run python -m scripts.kb_review_live status --run-root docs/verification/kb-model-review/stage1-r2
```

## 第 5 步：体系验收并写入账本

```powershell
uv run python -m scripts.kb_review_live accept --run-root docs/verification/kb-model-review/stage1-r2
uv run ruff check harness agents common plugins knowledge memory signals scripts tests app.py cli.py web.py evals
uv run pytest -q
```

`accept` 按登记的口径逐体系汇总。达标的体系写入模型审核批准，未达标的体系撤销其当前内容的全部批准，不论这些批准是哪一轮写入的。最后重新构建知识库，并把三态覆盖率写入 `stage1-r2/coverage.json`。

## 第 6 步：提交全部证据

```powershell
git status          # 确认 .env 不在列表里
git add docs/verification/kb-model-review/stage1-r2 knowledge/sources knowledge/reviews
git commit -m "feat(stage1-r2): archive the preregistered second knowledge review"
git push
```

推送后告诉我，我会核对证据、写验收报告，并更新 README 和阶段 1 的说明。

## 常见问题

| 提示 | 处理 |
| --- | --- |
| `未设置 OPENAI_REVIEW_BASE_URL` | 在 `.env` 里补上这一项（见第 0 步） |
| `校准集尚未经负责人确认冻结` / `校准集在冻结后被修改` | 回到第 1、2 步 |
| `请先运行 preregister` | 回到第 3 步 |
| `与预先登记不符` | 登记之后改动了审核模型、中转地址或规则代码。改回原样，或换新的活动目录重新登记 |
| `修改稿同义词冲突` / `在修改建议之后被另行修改` | 停止运行，把完整提示发给我 |
| `预算账本正被其他进程使用` | 确认没有其他审核在运行后，删除 `stage1-r2/budget.json.lock` |
