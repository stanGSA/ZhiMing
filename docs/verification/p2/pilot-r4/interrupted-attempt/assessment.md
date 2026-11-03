# P2 r4：实验未完成（模型服务不可用）

2026-11-03。按负责人图片指定，PR #46 合并及审查修复后的被测提交为 `0357a99c85ec5b49a43df2ba1a78cbc0a94ec30f`。

## 已执行

在仓库根目录执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p2 --root reports/p2-r4 --snapshot . --baseline . --publish docs/verification/p2/pilot-r4
```

外层本机 runner 备份原配置，逐字节恢复 r3 实验配置，并在退出时恢复原配置。没有修改被测源码或 rubric，没有更换模型。预定六组、每组18条、共108条。

| 项目 | 核对结果 |
| --- | --- |
| 实验配置 SHA256 | `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`，与 r3 相同 |
| 源码指纹 | `07482587277dcf97facc0ed4e2b24af236e94fb98cbe04a81f768742d6ac55e0`，逐文件核对一致 |
| 请求模型 / 评委模型 | 均为 `deepseek-v4.1-flash`；评委配置名 `pro`，thinking disabled |
| 定价文件 | 与 r3 逐字节相同；中转费率未核验，成本未知 |
| 已完整批次 | 0/6 |
| 保存的尝试记录 | Dream-single 3条，均为 model_error |
| 成功运行模型返回 / 已评分 | 0 / 0 |
| 原本机配置 | 已恢复，SHA256 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24` |

## 中断原因

运行模型和评委请求出现 `RateLimitError` / `InternalServerError`。随后独立的小请求检查反复得到 HTTP 503：

```json
{"type":"new_api_error","code":"get_channel_failed","message":"当前模型服务暂不可用，请稍后重试"}
```

最新检查为 2026-11-03 09:00:21 UTC（北京时间17:00:21）。因此中止当前组；campaign 因缺少完整 `live.json` 记录为 interrupted。前三条中每条运行模型已尝试3次、评委已尝试3次，但没有有效模型返回或评分；另有中止时正在处理的未完成请求，trace保留本机。这些都是服务故障尝试，不能当成产品质量失败、已完成样本或修复后效果。

接口检查使用单独的最小请求，不属于测试题或评委评分，未混入实验计数。完整原始记录在本机 `reports/p2-r4/`，启动、配置备份及诊断记录在 `reports/p2-r4-setup/`。

## 当前结论及恢复

**r4 未完成，不能判定是否满足 B 标准，不冻结，不执行 p2-final。** 当前 `comparison.md` 只有待完成项，`paired.json`、`raw-manifest.json`为空；它们是启动时自动产生的占位材料，不是实验结果。

没有完整 `live.json`，所以 r3 的 `pipeline_problems`、`quality_reasons`、编造分类和质量归因命令尚不能执行。服务恢复后，保持同一被测提交及相同实验配置，保留本次中断记录，以新 run 目录重启未完成组；不覆写或补造本次评分。

本机预备的恢复命令（会检查配置、提交及备份，归档前次启动元数据；保留已有 run 目录）：

```powershell
.venv\Scripts\python.exe -X utf8 reports/p2-r4-setup/run_campaign.py --resume
```

完整性检查见 [attempt-integrity.json](attempt-integrity.json)，本次启动元数据见 [experiment-metadata.json](experiment-metadata.json)，脱敏接口检查见 [endpoint-diagnostics.jsonl](endpoint-diagnostics.jsonl)。尚无成功返回，实际服务模型身份不能验证。
