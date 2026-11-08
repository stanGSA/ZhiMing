# r3 执行记录

按用户截图执行：

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r3 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r3
```

| 项目 | 值 |
| --- | --- |
| 被测提交 | `a6a1c80bf7ec13eb8f5868e256bbe810e390b09d` |
| PR #62 合并提交 | `75e1c60b3ad13a9e99e258cb9c53675b97ed63bd` |
| 源码指纹（183 文件） | `7fa842a76a4172146fa25d2055032936a0c9bdfc3f7606b089033109f5363d90` |
| 实验配置 SHA256 | `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b` |
| 原有配置 SHA256 | `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24` |
| pricing.yaml SHA256 | `d6d6cb2c2c385d894d79cb6c054a330f79458e068ef6183744f58ea65c812ef6` |
| 北京时间 | 2026-11-09 05:53:21–06:10:37；1036.6 秒 |
| campaign / wrapper 退出码 | 0；complete |
| Bazi-single run_id / 子进程退出码 | `20261108T215323-e33358ae` / 1 |
| Bazi-pipeline run_id / 子进程退出码 | `20261108T220537-dcf74824` / 1 |

子进程退出 1 表示原始工程或质量断言存在失败；campaign 退出 0 仅表示批次完整执行，不代表验收通过。

本机包装器 reports/run_bazi_pilot_r3.py 在运行前备份原配置，临时写入约定的实验配置；结束后 finally 按原字节恢复。两组 183 项源码哈希、预检哈希完全一致，除实验配置外的 182 项逐文件匹配被测提交，全部原始报告 SHA256 与发布摘要一致。36 条 trace 均存在；两组 18 对 id/repeat 一致。本地 config.yaml 的既有改动保留，不纳入提交。

原始报告路径：

```text
reports\p3-bazi-r3\Bazi-single\20261108T215323-e33358ae\live.json
reports\p3-bazi-r3\Bazi-pipeline\20261108T220537-dcf74824\live.json
```

后处理只读原始报告：scripts.quality_reasons（含 --answers 与 --counts-only --reviewed）、scripts.pipeline_problems，以及 reports/extract_bazi_pilot_r3.py、reports/audit_bazi_pilot_r3.py、reports/build_bazi_pilot_r3.py。没有额外模型请求或评分。脚本及原始 reports 数据留在本机，发布证据位于本目录。

发布 Markdown/JSON 使用 LF；evidence-manifest.json 覆盖本目录其他证据文件，原始报告与 trace 另由 raw-manifest.json、trace-manifest.json 记录。
