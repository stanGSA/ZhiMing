# P2 r10 评估

**新旧 B 口径均不通过，当前不能冻结。** PR [#52](https://github.com/stanGSA/ZhiMing/pull/52) 已合并；本轮完成全部108条请求，有效评分107条。三个pipeline均提交18/18，但各有一条因可定位误拒而降级；Name-pipeline另有一条评委JSON解析失败，不能宣称六组分类全部完整或pipeline事实编造率已经确认归零。

被测提交 `2fc44b59a6de7759dcfeb48172803978f4c05662`；源码指纹 `671227dec997801cc8a66f4fd780916c8bf3a26d8811b2ee6c181fae9e80e034`。执行时间2026-11-06 19:18:11–20:08:15（Asia/Shanghai），约50分钟04秒。实验配置沿用r9，原本机配置已按字节恢复。详见 [执行记录](execution.json)、[完整性审计](integrity.json) 和 [复现说明](reproduction.md)。

## 六组结果

| 组别 | 已提交 / 请求 | 有效评分 / 请求 | 已提交且质量通过 / 已提交 | 任务完成 / 请求 | pipeline修复 / 降级 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dream-single | 16/18 | 18/18 | 16/16 | 16/18 | 0/0 |
| Dream-pipeline | 18/18 | 18/18 | 18/18 | 18/18 | 4/1 |
| Name-single | 14/18 | 18/18 | 14/14 | 14/18 | 0/0 |
| Name-pipeline | 18/18 | 17/18 | 17/18（另1条未评分） | 18/18 | 1/1 |
| Daily-single | 16/18 | 18/18 | 8/16 | 8/18 | 0/0 |
| Daily-pipeline | 18/18 | 18/18 | 15/18 | 18/18 | 1/1 |

Name-pipeline在已评分提交中为17/17通过；按全部提交计算保留17/18，不把未评分当作通过或质量失败。Dream-single另有1条质量通过的文本回复，Name-single另有4条质量通过的追问；它们均不是提交成功。Daily-single保存16条但任务完成8条，不能以保存成功替代任务完成。

原始质量失败共14条、未评分1条。pipeline累计6次修复、3条降级，无无命中模板降级。三组pipeline最大模型调用分别3、3、2，无步数/预算失败，原始engineering_pass分别18、18、17。single的工具修改与重试不计为pipeline repairs。自动对照报告的“无工具错误”和原始engineering_pass分开保留，见 [comparison.md](comparison.md) 和 [integrity.json](integrity.json)。

## 冻结阻断

| 项目 | 实际证据 | 新口径 | r9严格口径 |
| --- | --- | --- | --- |
| Dream否定句误拒 | `dream_late_grandmother#2` 两稿“这个梦没有预示什么”被判预言，keywords降级 | 阻断 | 阻断 |
| Name计量词误读 | `name_without_lead_in#2` 两稿“数理是一套…”被读成数理1，keywords降级 | 阻断 | 阻断 |
| 投资否定句误拒 | `daily_investment_risk#1` 两稿“不把…当稳赚信号”被判确定收益，safety降级 | 阻断 | 阻断 |
| 评分完整性缺口 | `Name-pipeline/name_career_grid#3` 评委两次返回带尾随逗号的JSON，scored=false | 阻断 | 阻断 |

三条降级稿的原始质量评分均通过，但这不消除实际发生的误拒与降级。拒绝稿、最小对照和源代码位置见 [validation-findings.md](validation-findings.md)；评委两份失败原文见 [judge-unscored.json](judge-unscored.json)。没有补跑、替换样本、补评或回写原分。

已评分的53条pipeline回答中，原 `no_fabricated_facts=false` 为0；Name-pipeline尚有1条未评分，因此“pipeline事实类编造为零”完整性门槛不通过。六组计数表有5组完整、1组不完整。Daily-single的5条已提交编造维度失败由助手分为事实类1条、叙述类5条（其中1条兼属两类），分类与异议详见 [fabrication-counts.md](fabrication-counts.md) 和 [fabrication-review-notes.md](fabrication-review-notes.md)。

## 离线复核与限制

全部26条异常、修复或非提交记录已逐条归因，见 [quality-attribution.md](quality-attribution.md)。除上述三个pipeline阻断，还复现了single的“不作诊断或预兆/预示解读”否定范围误拒，以及“交际活跃度上升”被读成上升星座；single的这些缺陷按PR记载的新口径不单独阻断，严格口径仍需记录。

Daily评分存在可核验异议：额外抽出的三张塔罗牌确有计算记录；`daily_tomorrow_work#3` 的17:52–23:00实际仍乙酉，评委误称丙戌；`daily_today_family#3` 正文没有其声称的21:18Z时刻，高塔真实释义也包含被质疑的“检查基础条件”。同时部分single回答确有23:00换段写成傍晚、21:00或15:00等错误。异议不直接改分，不把所有失败归咎评委。36条每日请求的计算证据索引见 [fact-review.json](fact-review.json)：35条有daily_result，1条通过单项工具计算而使用transit_result/bazi_period_result。

运行及pro评委均为 `deepseek-v4.1-flash`，thinking和policy_judge关闭；同模型评分不是独立校准。中转费率未核实，费用未知。每题3次是重复测量，小样本只作描述；与r9相比，不能把质量计数差异直接归因于PR修复。

本轮未修改产品源码、未执行p2-final、未查看留出题目。PR #52的新增边界守卫通过本地366项回归；本轮暴露的新边界留待后续修复与重新实验，本次原始结果保持完整。
