# r19 评估：达到试点数值门槛，暂不冻结

r19 campaign 完整结束：single 与 pipeline 各 18 个合成样本、每题重复 3 次，36/36 均完成评分。Single 提交 14/18，其中 12/14 质量通过；pipeline 提交 18/18，其中 16/18 质量通过。严格综合通过为 single 6/18、pipeline 16/18；pipeline 的同批提交质量通过率较高。

**本轮结果不足以冻结。**

- Pipeline 的两条已提交质量失败均来自文字出生题：第 2 次未通过 `time_consistent` 和 `supported_conclusion`，第 3 次未通过 `time_consistent`。评委对节气边界的解释与部分判定文字不完全一致，保留原评分，需负责人复核是否存在可定位的误拒。
- Single 两条已提交的 `no_fabricated_facts` 失败经人工归为叙述类，分别把性格/职业场景和推算年龄关联到用户具体经历；pipeline 没有已提交回答的编造失败。分类口径和逐项证据见 `fabrication-counts.md`、`quality-reasons-with-answers.md`。
- Pipeline 有 5 个样本触发首稿修复，共拦截 7 项问题，未降级；原稿、问题描述和修复引用保存在 `repair-evidence.json`、`repair-quotes.json` 与 `pipeline-problems-raw.md`。

本次 18 个请求每题重复三次，不是 54 个独立样本；运行模型与评委模型相同，自动评分不构成独立人工校准。实验未据此记录代码冻结，也未启动最终集 `p3-bazi-final`。统计、配置与完整性核验以本目录中的 r19 证据为准；原始 trace 留在本机 `reports/p3-bazi-r19/`。
