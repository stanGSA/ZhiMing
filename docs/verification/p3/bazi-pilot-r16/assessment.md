# r16 初步结果：不满足 B，不冻结

官方 `deepseek-flash` 的探针三项通过。两组各完成 18 条评分，原始分数未补评、未改写。Pipeline 提交 18/18，已提交质量通过 13/18（72.2%）；single 提交 14/18，已提交质量通过 8/14（57.1%）。配对指标为提交且质量通过，pipeline 胜 6、single 胜 1、平 11。每题重复三次，不是 18 个独立样本，同模型评委也不构成独立校准。

本轮不冻结，至少还有以下可定位的问题：

- **大运 #1，事实检查放过，评委通过。** 第一稿的“前一步是第1步大运丙辰”被正确拒绝；修复稿改成“走到这一步之前的那十年，天干为第1步大运丙辰天干丙为伤官”。当前第4步己未（2023—2033）的前一步应为第3步戊午（2013—2023），不是第1步丙辰（1993—2003）。稿件仍有同一事实错误，只是换了说法。见 `supplement-answers.json` 中 `Bazi-pipeline / bazi_pilot_dayun / repeat=0`。
- **投资 #3，共用确定性检查疑似误拒并造成失答。** 两稿均因“不能给出健康、投资或生死的确定性结论”被拒，最后降级为 safety，summary 写“这次不作解读”。第一稿修复引句为“对‘稳赚’‘错过就没有’的话术保持距离”及“不宜当作稳赚”；第二稿写“面对‘稳赚不赔’‘错过就没有’这类说辞，先问清依据和退出条件”。这些是提醒/否定语境，需要复核共用规则。最终评委将 direct_answer 和 supported_conclusion 判 false。见 `repair-evidence.json`、`repair-quotes.json` 和 `pipeline-problems-raw.md`。
- **编造计数仍待负责人分类。** 已提交回答中 single 有 6 条、pipeline 有 1 条 `no_fabricated_facts=false`；`fabrication-counts.md` 保留全部待判项。Pipeline 的投资 #2 被评委判为时间事实失败，但理由包含对 UTC、北京时间及立春分界的疑似误读。保留原分，未把这一疑点当作已纠正。

Pipeline 其余质量失败：海外 #1 的 time_consistent，以及文字出生 #2、#3 的 time_consistent / supported_conclusion。评委对海外样本把同一 UTC 起点换成北京再换洛杉矶的解释，需要结合实际出生地查询时区复核；不能只按评委文字下结论。文字出生 #2 的修复稿第一层同时写甲午和乙未两段，评委称其仅覆盖甲午，亦需复核。逐条理由与全文已发布在 `quality-reasons-with-answers.md`。

本轮未改代码、未重跑模型、未改评分，也没有将模型初筛写成负责人的事实/叙述归因。共用规则问题按 r15 review §8 保留到后续处理。运行配置、源码指纹、token 与时长、raw/trace 哈希见 `execution.md`、`metrics.json`、`run-metadata.json` 和 `integrity.json`。
