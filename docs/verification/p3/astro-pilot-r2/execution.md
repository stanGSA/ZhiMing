# P3 星盘 r2 调参实验执行记录

- 正式实验：2026-11-07 23:20 至 2026-11-08 00:12（Asia/Shanghai），串行完成 36 条。
- 被测提交：`4ed500dfdc744c8050d8b443c16fb845c43cf438`，PR #56 合并并修复后的代码。
- 按截图运行 `p3-astro`，6 题 × 3 次重复 × single/pipeline；本轮没有运行最终验收集。
- `--snapshot . --baseline .` 使用主工作区；两组均记录 179 个源文件哈希，源码指纹 `b1c2c6f6549af956ec1c88ef2395e576a323ded8341419160516d079e7f4830a`。
- 178 个非配置源文件与上述 Git 提交逐字节一致；两组完整 source-hashes 相同，运行期间没有修改被测代码。
- 本机原配置只启用了 `[tarot]`，因此正式运行临时改为 `[tarot, astro]`；其余内容不变。两组使用同一配置。
- 实验配置 SHA256：`141eca6bf025732ff3c749837b6eab79907356140ce05dd8e8216ca436bfa54a`。
- 原配置 SHA256：`d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`，结束后已按字节恢复并核对。
- 图片原命令的第一次试跑因为没有启用 astro 而回退 Agent，不作为 r2 结果；已停止并完整归档到本机 `reports/p3-astro-r2-config-mismatch-20261107T1520`。
- 请求和返回模型均为 `deepseek-v4.1-flash`，`--judge pro` 的实际评委也是同一模型；名称 pro 不代表独立模型或独立评审。
- 费率文件 `models: {}`，中转计费未经验证，费用未知。配置和凭据不发布。

## 正式命令

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-astro --root reports/p3-astro-r2 --snapshot . --baseline . --publish docs/verification/p3/astro-pilot-r2
```

命令由本机 `reports/run_astro_r2.py` 包装执行，仅负责临时配置和结束恢复，不修改 campaign 行为。
单组评估均退出 1（存在失败断言），但两组都生成完整 live.json，campaign 按设计继续，最终退出 0，状态 complete。
未逐条补跑、未改分、未替换失败样本。

本机原始记录在 `reports/p3-astro-r2`；公开摘要、证据和局限见 [assessment.md](assessment.md)、[integrity.json](integrity.json)。
