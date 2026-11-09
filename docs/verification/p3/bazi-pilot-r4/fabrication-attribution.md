# r4 编造失败离线归因

本文件由 Codex 离线核对原回答、原评委理由与计算事实，不是独立人工复核。只给原 no_fabricated_facts=false 的已提交回答归因；不修改原分，也不把其他新发现追加进原评分计数。`fabrication-reviewed.yaml` 的接口要求非空类别列表，因此争议条目省略 key，计数如实保留待判定。

| 批次 | 样本 | 本轮归因 | 依据 |
| --- | --- | --- | --- |
| Bazi-single | bazi_pilot_trait#1 | 叙述类 | “你大概有过这样的体验”“你往往大方但有底线”等将性格场景写成个人经历。 |
| Bazi-single | bazi_pilot_dayun#1 | 叙述类 | “近年常被身边人拉着聊合作、副业”“年末一算结余不如预期”等编出未提供的经历；五行取用方向的过推归叙述支撑问题，没有据此确认干支或计数写错。 |
| Bazi-single | bazi_pilot_trait#2 | 叙述类 | “当年环境里可能就有要争、要比较的氛围”等凭年柱写早年生活背景。 |
| Bazi-single | bazi_pilot_typed_birth#2 | 叙述类 | “追求你的人不缺”等将象征落到具体处境；原理由也明确其余出生、四柱、十神及计数未编造。 |
| Bazi-single | bazi_pilot_investment_risk#3 | 叙述类 | “你熟悉的那套方法明年可能反复失灵”等预设个人场景；该判负与其他回答的条件式措辞尺度存在争议，保留原分。 |
| Bazi-pipeline | bazi_pilot_investment_risk#1 | 叙述类 | “容易遇到资源被分走或冲动花费的情形”等从象征推具体场景及财务评价；没有确认新的排盘事实错误。 |
| Bazi-pipeline | bazi_pilot_dayun#2 | 待复核，未分类 | 原评委说内部排盘事实未在题面出现即属编造，但这些事实与 calculated_facts 一致，正文也有“按排盘口径”。保留 false，不将其强塞事实类或叙述类 |

计数：single 编造失败 5，其中叙述类 5、已确认事实类 0、待判定 0；pipeline 原编造失败 2，其中叙述类 1、已确认事实类 0、待判定 1。pipeline 的事实类总数尚不能确认为零。

大运 #3 的“出生当年起运”和投资 #3 的年柱/时柱错置均见 r4-observations.md；其原 no_fabricated_facts=true，所以它们不出现在本表的原失败计数中。
