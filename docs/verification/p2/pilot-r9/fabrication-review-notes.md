# r9 编造分类与评分异议

分类覆盖全部已提交回答的原始 `no_fabricated_facts=false` 键，不改原分。助手离线复核不是独立人工校准。一条可同时属事实及叙述类，不能直接相加。见 [fabrication-counts.md](fabrication-counts.md) 和 [fabrication-reviewed.yaml](fabrication-reviewed.yaml)。

| 组别/键 | 保留的分类 | 依据与异议 |
| --- | --- | --- |
| Name-single / name_compare_two#3 | 叙述类 | 人格/生活表现外推，“易得助力”偏离引用限制；五格数值本身正确 |
| Name-single / name_three_character#3 | 叙述类 | 将前辈帮过你、常被说要求高等写成用户既往经历 |
| Daily-single / daily_today_general#1 | 叙述类（有异议） | 理由承认计算正确、条件句尚可且“不构成明显编造”，却仍给false；不将此计数解释为已确认编造 |
| Daily-single / daily_lucky_color#2 | 叙述类 | 将有人搭手、好消息延期等作为当天具体画面；幸运色计算有据 |
| Daily-single / daily_tomorrow_work#3 | 事实类、叙述类 | 丙戌15:00 UTC写成当地下午三点，实际23:00；resonances又把临时任务等写成经历 |

六组统计完整，无未评分或待分类。三个pipeline原始事实/叙述类失败均为0，这是本轮观测，不证明模型不会编造。Name-single / name_compound_surname#1 未提交，不计入主表；它另被评委指控编造运行重试状态，但真实trace确有重复失败及已存计算，该指控有异议。

## 时间评分异议与真实错误

实际日期和UTC/本地分段逐行列在 [fact-review.json](fact-review.json)。

- Daily-pipeline / daily_today_general#2：原文明确上海时间00:00–23:00甲申、23:00–24:00乙酉；评委自己承认未越出日期，仍以“存疑”判false。未找到该理由指称的越界。
- Daily-pipeline / daily_tomorrow_work#2：原文已标上海时间00:00–17:52、17:52–23:00为乙酉，23:00–24:00为丙戌；实际UTC边界为前日16:00→当日09:52→15:00→16:00，换算后吻合。两个乙酉分段源自真实计算，不能仅因同柱名判矛盾。评委再次加8小时及声称未写丙戌的时间指控不成立。其supported_conclusion的权重/外推意见另存，不据时间异议改判整体通过。
- Daily-pipeline / daily_lucky_color#3：精确相位虽有UTC日期11月5日，转上海时间后全部为11月6日；不能以UTC日历不同排除本地当日相位，保留原分并记异议。
- Daily-pipeline / daily_unknown_birth_time#3：确有引用外推，例如把三会“力量集中”赋予情绪钻牛角尖的意义；未知时辰下未编宫位/时柱的限制仍遵守。
- Daily-single / daily_tomorrow_work#3 与 daily_investment_risk#3：确实将15:00 UTC写成当地下午/傍晚，属于真实时区错误。后者原编造维度仍true，另记漏判，不回写原失败计数。工作题另有牌面画面扩写，不能将全部问题归咎评委。

本轮有评分理由与布尔值冲突、相同时区口径不同判法；同模型评分不能称为可靠性已获独立验证。已复现校验缺陷独立阻止B，无需调整评分或放宽标准。
