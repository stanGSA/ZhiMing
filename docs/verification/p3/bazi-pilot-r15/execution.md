# P3 八字调参集 r15 执行记录

状态：探针通过后启动了实验，但服务实际行为异常；完成 3/18 条 single 后中断。pipeline 组尚未启动，本轮不构成有效对照。

记录时间（北京时间）：2026-11-14T03:48:46+08:00。

被测版本：`b6610ecd2f7c2e10b8c7f79984a103e8d8e353bd`（PR #74 合并，包含否定范围修复 `d9d0c74`）。

按 `../bazi-pilot-r14/review-claude.md` §7，临时切换到约定配置，核验 SHA256 为 `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b`，执行 `scripts.check_model`。前三次返回 HTTP 429；第四次成功：

```json
{
  "error_type": "RateLimitError",
  "status_code": 429,
  "requested_model": "deepseek-v4.1-flash"
}
```

第四次探针仅回复 `OK`，`output_tokens=16`、`reasoning_tokens=null`，按预检阈值放行。正式 campaign 随后启动，但前三条 single 中两条将英文/中文内部推理文字直接当作回答，一条达到 12 次调用上限；实际运行行为与预检结果不一致。为避免继续产生无效请求，已中断 campaign。pipeline 组尚未启动；未补评、重跑或改写已产生的样本。前三条原始记录保留在 `reports/p3-bazi-r15/Bazi-single/20261113T195833-9aa86e5f/progress.json`，campaign 检查点标记为 interrupted。

| 组 | 评委每行输出 token 中位数 | 运行每次调用输出 token 中位数 |
| --- | --- | --- |
| Bazi-single | —（仅 3/18 条，非完整组） | —（仅 3/18 条，非完整组） |
| Bazi-pipeline | —（未运行） | —（未运行） |

前三次探针原始记录为 [preflight-probe-attempt-1.json](preflight-probe-attempt-1.json)、[preflight-probe-attempt-2.json](preflight-probe-attempt-2.json) 和 [preflight-probe-attempt-3.json](preflight-probe-attempt-3.json)；第四次成功记录见 [preflight-probe-attempt-4.json](preflight-probe-attempt-4.json)。[preflight-probe.json](preflight-probe.json) 始终指向最新一次探针。预检输出 token 不能代表实际运行；因 single 不完整且 pipeline 未运行，本轮不报告正式的两组 token 中位数。

个人配置已在每次探针结束的 finally 中恢复；当前配置与备份 SHA256 均为 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。

第三次探针之后再次尝试：第四次探针成功后运行至第 3/18 条 single 时发现服务返回推理文本，立即中断。campaign 子进程已退出；个人配置从运行前备份恢复并校验一致。部分运行目录保留供诊断，不能当成完整评估结果。

## 再次尝试

2026-11-14 04:00 左右（北京时间），按用户要求再次运行探针。前三次探针均为 HTTP `429`；第四次探针成功，仅回复 `OK`，`output_tokens=16`、`reasoning_tokens=null`，因此启动 campaign。第四次探针原始记录见 [preflight-probe-attempt-4.json](preflight-probe-attempt-4.json)，此前失败记录仍保留。

正式运行的前三条 single 样本中，`bazi_pilot_trait` 达到 12 次模型调用上限；`bazi_pilot_dayun` 和 `bazi_pilot_next_month_career` 将内部推理文字直接作为回答。该行为与开跑探针明显不同，故中断 campaign，没有继续消耗调用。检查点中 single 仅有 3/18 行，pipeline 0/18；因此没有完整组可计算 token 中位数，表中不填正式 P50。原始部分记录保留在本机 `reports/p3-bazi-r15/Bazi-single/20261113T195833-9aa86e5f/progress.json`，本次不随执行摘要推送。

仅作故障诊断，三条 single 部分样本的每题累计运行输出 token 为 1877、265、362，样本中位数为 362；对应评委输出 token 为 1204、753、1256，中位数为 1204。它们不是每次模型调用的中位数，也不是完整组结果，不用于 r15 对照结论。

中断后个人配置已从运行前备份恢复，SHA256 校验一致；campaign 标为 interrupted，锁文件已清理。部分数据只供诊断，不作为 r15 评估结论。

## 再次预检

2026-11-14 04:31（北京时间），按用户要求重新预检。第五次探针返回 `OK`，`reasoning_tokens=null`，但 `output_tokens=31`，高于 §7 规定的 20-token 阈值。本轮依方案暂停，未重启 campaign。原始记录见 [preflight-probe-attempt-5.json](preflight-probe-attempt-5.json)。个人配置已恢复，哈希与运行前备份一致。
