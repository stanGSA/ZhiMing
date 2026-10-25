# P1 实施与验收

2026-10-24，Asia/Shanghai。用户要求按本机实施手册执行，实际仓库 `D:\知命`，分支 `p1/implementation`。

当前的中转接口活动已完成：`deepseek-v4-flash` 的 B0、Final、留出集与模式对照共517个案例/句子均已跑完，见 [中转对照](codego-v4/README.md)。随后依据图片方案修正了评测统计与 C 类根因，并对已有结果离线重算；没有为重算重新调用模型。

## 实施状态

Final 实现已完成并通过定向回归：来源默认填参和错误信息、短引用、代码证据附录、阶段工具列表、体系规则按需返回、结构化 verdict、可选异步表达策略判断、multi-lite、SSE 进度及评测工具。按后续方案移除了模型写入地理/历法口径字段的路径，改由地点解析和成功排盘代码保存默认值。事实 Guard、权限隔离、历史结果和正式知识库均保留。运行默认仍为 single；不根据尚未完成的人工校准宣称质量验收通过。

`p1-b0` 为 `4702b51`：新 rubric v2/重复评测脚本与旧 agent。最终结果和留出集均已完整完成；离线重算后的摘要、分类和配对报告已更新到本目录。原始 trace 和完整答案只保留在忽略目录 `reports/p1/`。评测批次完成不等于 P1 质量验收通过。

|检查|当前证据|
|---|---|
|定向回归|159 passed，覆盖评测脚本、地点自动保存、画像字段边界和八字默认口径|
|评测规模|B0/Final、留出集、single/multi/multi-lite及策略评估共517/517|
|留出集脚本一致性|B0/Final 的 `scripts/live_test.py` SHA256 一致；核验值记在中转对照摘要|
|统计口径|工具重试失败但任务完成不再判整题失败；评委解析失败单列未评分；另列已提交回答质量通过率|
|C类根因|画像写入字段移除坐标/location_id/出生时区/八字约定；地点解析及成功排盘后由代码保存|
|Final single/multi|任务完成37/60、33/60；已提交回答质量通过率13/25、11/22；P1仍未通过|
|评委人工校准|20份待标注材料仍未完成人工四维标注，kappa未计算|

DeepSeek Pro 与被测 Flash 为同厂商的不同模型；不是跨厂商独立评委。返回模型名称也不等于独立验证底层服务身份。人工标注缺失时不能把模型/代理标注当成人工一致性。

重算报告位于 [中转对照](codego-v4/README.md)。原始模型响应、trace 和源快照保存在本机忽略目录；离线重算只读取已保存数据，不会产生新的模型费用。

## 比较口径

任务完成不计 `zero_tool_errors`；零工具错误率另列，保留原严格综合列。编排者 `no_model_error` 仅看自身会话，专家失败单列。延迟包含澄清，不含 rubric 评分/准备知识库，P95 为 nearest rank；只比较串行批次。每题 token/成本包括实际编排、专家、审校和策略判断，不包括独立 rubric 评委；未知 usage/cache 不补零，费用是 pricing.yaml 费率估算而非账单。

heldout 的 decision/all-in 改查 verdict 字段，两份源码快照使用相同断言；旧 agent 没有 verdict 的失败会保留，属于接口迁移结果，不能解释成原回答内容变差。其余断言与17场景保持。B0-heldout 开始前已经同步脚本；本次脚本还补充了 `.env` 自动加载，避免独立执行器误报缺少密钥。

本次多个实现点在完整 B0 尚运行时并行落地，未生成 B1/B2/B3 的逐项源码快照和真实消融数据。最终版只能标为“合并实现对照”，不把同一结果复制成多条逐步提升。若需要独立归因，必须另建中间版本并重复跑。

## 本机操作

```powershell
# 真实调用批次串行；不要另开并发跑批
& .venv/Scripts/python.exe -X utf8 -m scripts.p1_campaign --root reports/p1 --snapshot reports/p1/final-source --baseline reports/p1/b0-source --publish docs/verification/p1
# 原始标注文件只留本机；完成20份四维人工标签后才计算
& .venv/Scripts/python.exe -X utf8 -m scripts.p1_calibration reports/p1/human-calibration.json
```

执行器在 `campaign.json` 记录进度，日志 `Final-*.log`、`Compare-*.log`；已有完整结果不重复调用。`campaign.lock` 防止重复执行。失败退出码1代表评测断言不通过，完整结果仍保留并继续下一批；进程异常造成报告不完整则停止，需先检查日志。

提示词迁移见 [审计表](prompt-audit.md)，策略混淆矩阵见 [表达判定](policy-judge.md)，官方费率查询日期见 [pricing.yaml](pricing.yaml)。
