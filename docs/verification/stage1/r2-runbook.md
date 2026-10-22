# 阶段1第二轮知识库审核：本机运行手册

## 2026-10-22 本机实施状态

当前工作分支为 `codex/stage1-r2-acceptance`（从 `4e2f54d` 继续），main 为 `9951cdd`，PR #17 已合并。上一轮失败结论不变。

Codex AI 已逐条复核274条校准样本及188个被删别名，首次真实调用前修正24条样本的内容/依据，保留全部原标签，恢复10个别名；详见活动目录中的 `calibration-ai-review.json`、`calibration-review-ai.md`、`dream-alias-review-ai.md`。确认身份为 AI，未声称负责人亲自逐条核对，也不产生人工审核状态。校准集尚无独立人工专家确认，Codex 与审核B同属 OpenAI，此限制须随验收结果披露。原起草确认表保留，不再用作当前冻结内容的依据。

校准锁使用 `--review-kind ai_delegated`；保留集哈希 `535c87eaabeeec47591f4029d96cd0b990485f8157e522fc3e52db67f9733ac3`。不要重跑起草脚本覆盖已复核文件，任何条目改动都会使锁失效。正式验收仍须开发集试跑达标、预登记并推送后才能开始。

别名修改后构建 `v1-984b14f53d4d43c7`，1171条，451条模型审核、720条草稿、0条人工审核。100条离线扫描的 precision=0.7852、recall=0.8548、完全一致67条（R1为65条、初始旧版69条）；后缀匹配存在的事件区分问题另列于别名复核文件，不据此宣称真实回答质量通过。

离线计划见 `../kb-model-review/stage1-r2/offline-plan.json`：开发集108次请求，粗估输入275,916 / 输出50,880 token；正式初审524次请求，粗估输入2,027,892 / 输出700,800 token。重试、修改、复审另计；沿用无预算上限，三角色费率未知，不能报为零费用。

## 为什么要有第二轮

上一轮（2026-10-21）中，八字、姓名、解梦的 kappa 未达标，姓名的重跑一致率也未达标，阶段1知识库验收未通过。原因不是随机波动，而是两家审核方在同一批内容上用了不同的标准：

- 八字：B 要求写出对象专属内容，A 不要求。
- 解梦：B 要求方向有依据、同义词范围要窄。
- 姓名：B 看三才的民间约定写法，A 看数理，而且 A 记错了尾数定五行的规则。

上一轮作为失败记录保留，不删除、不重置分母、不降低阈值。

## 第二轮的做法

1. **审核规则 v2**（[scripts/kb_review_rubric.py](../../../scripts/kb_review_rubric.py)）：两家共用的判定锚点，加上八字、姓名、解梦的正反例。参考事实直接取自程序计算用的同一份表：藏干、干支关系、十神、尊贵表、宫位主题、尾数五行、数理三档、五行配色、各体系的方向约定。
2. **解梦别名逐条复核**（[复核表](r2-dream-alias-review.md)）：恢复同一意象的说法，保留对误匹配的拦截，并重测准确率与召回率。
3. **标注校准集，分两部分**（[确认表](r2-calibration-review.md)）：开发集用于试跑和完善规则，保留集只在正式验收中用一次。两部分都含边界案例，标签全部有规则依据，不参考任何模型的结论。
4. **先试跑开发集**：费用约为整轮的十分之一。不达标时由我分析分歧、调整规则，最多 3 轮。
5. **运行前登记**：规则、审核方、知识库、保留集、阈值和 kappa 口径一并冻结并推送，然后才开始正式审核。

正式验收的阈值不变：当前内容通过率 ≥95%；埋错检出合并 ≥90%、单家 ≥80%；每家重跑一致率 ≥90%；kappa ≥0.6（在保留集上计算）。

**试跑标准在运行前就写定，不看结果再改**：两家在开发集上的 kappa ≥0.6，各家重跑一致率 ≥90%，各家与标签的一致率 ≥85%。最多 3 轮（首轮加两次规则调整）。仍不达标时停下来，由你决定是否更换审核模型。登记时，最近一次试跑必须在当前规则下达标；否则只能由你用 `--pilot-override` 写明理由。

以下命令均在 PowerShell 里、项目根目录下执行。

## 第 0 步：准备

```powershell
$env:PYTHONUTF8 = "1"
git fetch origin
git checkout claude/brave-ride-ng806d      # 合并到 main 后改为 git checkout main; git pull
uv sync --locked --extra llm --extra web
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run pytest -q tests/test_kb_review_r2.py tests/test_kb_review_campaign.py
uv run python -c "from dotenv import dotenv_values as v; e=v('.env'); print({k: bool(e.get(k)) for k in ('DEEPSEEK_API_KEY','OPENAI_REVIEW_API_KEY','OPENAI_REVIEW_BASE_URL')})"
```

三个都要是 `True`。`OPENAI_REVIEW_BASE_URL` 是新增的：中转站地址不再写在 config.yaml 里，请在 `.env` 加一行 `OPENAI_REVIEW_BASE_URL=https://codegoai.com/v1`。不要提交 `.env`。

## 第 1 步：解梦别名复核

1. 打开 [r2-dream-alias-review.md](r2-dream-alias-review.md)，再在 `docs/verification/kb-model-review/stage1-r2/dream-alias-review.yaml` 里把 35 条 `decision: undecided` 改成 `restore` 或 `keep`。其他组不同意的，也可以直接改。
2. 写入源文件并重测：

```powershell
uv run python -m scripts.dream_alias_review apply --review docs/verification/kb-model-review/stage1-r2/dream-alias-review.yaml
uv run python -m knowledge.build
uv run python -m scripts.dream_alias_regression --old-version v1-db9e5019df128abc `
  --output docs/verification/kb-model-review/stage1-r2/dream-alias-regression-after.json
uv run pytest -q tests/test_week6.py
```

还有未决定的条目，或者恢复后与其他条目冲突时，`apply` 会拒绝，并且不改动任何文件。重测需要旧版快照 `data/kb_versions/v1-db9e5019df128abc.sqlite`；本机没有这个文件就跳过重测，告诉我即可。

## 第 2 步：确认并冻结校准集

打开 [r2-calibration-review.md](r2-calibration-review.md)：保留集逐条确认，开发集抽查。有不同意的，发编号和理由给我。如果第 1 步改了"恢复"组的某条，也请告诉我。全部同意后冻结：

```powershell
uv run python -m scripts.kb_review_calibration freeze `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml `
  --confirmed-by "你的名字"
git add docs/verification/kb-model-review/stage1-r2 knowledge/sources
git commit -m "docs(stage1-r2): restore reviewed dream aliases and freeze the calibration set"
git push
```

## 第 3 步：试跑开发集

```powershell
uv run python -m scripts.kb_review_live pilot --iteration 1 `
  --run-root docs/verification/kb-model-review/stage1-r2 `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml
git add docs/verification/kb-model-review/stage1-r2
git commit -m "docs(stage1-r2): pilot 1 on the dev calibration set"
git push
```

- 输出里每个体系都是 `"met": true`：直接进入第 4 步。
- 有体系没达标：push 后告诉我。我会根据 `pilot-1/<体系>/pilot-summary.json` 里的分歧清单调整规则（必要时更正开发集标签，再重新冻结），然后你 pull 下来，运行 `--iteration 2`；最多到 `--iteration 3`。
- 第 3 轮仍不达标：停下来，由你决定是否更换审核模型。换模型要改 config.yaml，然后从第 3 步重新开始。
- 中断或接口出错时，用同一个 `--iteration` 再运行一次即可，已完成的调用不会重复。

## 第 4 步：预先登记，并在审核前推送

```powershell
uv run python -m scripts.kb_review_live preregister `
  --run-root docs/verification/kb-model-review/stage1-r2 `
  --calibration docs/verification/kb-model-review/stage1-r2/calibration.yaml `
  --decisions docs/verification/kb-model-review/stage1-r2/owner-decisions.json
git add docs/verification/kb-model-review/stage1-r2
git commit -m "docs(stage1-r2): preregister the second review"
git push
```

登记会冻结规则哈希、审核方、批次设置、知识库版本与源文件哈希、保留集哈希、阈值、kappa 口径和试跑记录。**一定要先推送，再进入第 5 步**：推送时间早于任何正式审核结果，才能证明口径是事先定的。登记之后不能再改知识库源文件，否则初审会被判为与登记不符。

## 第 5 步：正式审核

```powershell
uv run python -m scripts.kb_review_live run --run-root docs/verification/kb-model-review/stage1-r2
uv run python -m scripts.kb_review_live status --run-root docs/verification/kb-model-review/stage1-r2
```

- 每个体系先初审全部条目（含埋错和保留集），再由修改方处理被退回的条目，然后只复审真正改过的条目，最多 3 轮。
- 也可以分体系运行：在命令末尾加 `--systems tarot`。
- 预计耗时 1～3 小时。可以随时按 Ctrl+C 中断，再执行同一条命令续跑；输出"有调用失败"时稍后重跑即可，失败不会被算作审核结论。

## 第 6 步：体系验收、提交证据

```powershell
uv run python -m scripts.kb_review_live accept --run-root docs/verification/kb-model-review/stage1-r2
uv run ruff check harness agents common plugins knowledge memory signals scripts tests app.py cli.py web.py evals
uv run pytest -q
git status          # 确认 .env 不在列表里
git add docs/verification/kb-model-review/stage1-r2 knowledge/sources knowledge/reviews
git commit -m "feat(stage1-r2): archive the preregistered second knowledge review"
git push
```

`accept` 按登记的口径逐体系汇总：达标的体系写入模型审核批准；未达标的体系撤销其当前内容的全部批准，不论这些批准是哪一轮写入的。推送后告诉我，我会核对证据、写验收报告。

## 费用

上一轮六个体系约用了已知输入 206 万、输出 60 万 token。本轮正式审核与上一轮规模相当（多了 180 条保留集条目），每轮试跑约为其十分之一。上一轮负责人决定不设预算上限；费用未知，不会记为 0。

## 常见问题

| 提示 | 处理 |
| --- | --- |
| `未设置 OPENAI_REVIEW_BASE_URL` | 在 `.env` 里补上（见第 0 步） |
| `还有 N 条未决定` | 回到第 1 步，把 `undecided` 改成 `restore` 或 `keep` |
| `别名冲突` | 把提示发给我 |
| `校准集尚未经负责人确认冻结` / `校准集在冻结后被修改` | 回到第 2 步；重新冻结须加 `--reason "原因"` |
| `最近一次试跑未在当前规则下通过` | 回到第 3 步；或由你用 `--pilot-override "理由"` 登记 |
| `是在另一版规则下试跑的` | 规则改过了，用下一个 `--iteration` |
| `试跑最多 3 轮` | 由你决定是否换审核模型 |
| `与预先登记不符` | 登记后改动了审核模型、中转地址、规则或知识库。改回原样，或换新的活动目录重新登记 |
| `修改稿同义词冲突` / `在修改建议之后被另行修改` | 停止运行，把完整提示发给我 |
| `预算账本正被其他进程使用` | 确认没有其他审核在运行后，删除 `stage1-r2/budget.json.lock` |
