# r10 编造维度分类复核

助手离线复核，非独立人工校准。只分类已提交且有四维评分的原始 `no_fabricated_facts=false`，不删除原失败、不补评分。原始理由与回答见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)。

| 组别 / 题目 | 分类 | 依据与异议 |
| --- | --- | --- |
| Daily-single / daily_unknown_birth_time#1 | 叙述类 | “旧朋友出现”等被列为彼此呼应。评委指三张牌编造不成立：实际tarot.cards确有宝剑二逆位、圣杯六正位、权杖四正位，属于另一次真实抽牌；每日一牌为星币三逆位，不等于其他抽牌不存在。因此只保留有依据的叙述类归属，原编造维度失败不变。另有21:00换段的真实错误，不能据此回写原time_consistent=true。 |
| Daily-single / daily_investment_risk#1 | 事实类、叙述类 | 原理由同时指控三合参与归属及当日心理/行动时点外推，保留混合分类。实际本命年支子、时支辰与流日申可以形成申子辰，日支未不参与，原文“年支子、日时之类”不严谨；不把该归因简化成三合事件本身不存在。分类计数不是对每项评委指控逐一确认。 |
| Daily-single / daily_tomorrow_work#2 | 叙述类 | 方案重做、改时间、同事分工争议等被写成当天场景；原理由明说出生资料与命盘事实一致。 |
| Daily-single / daily_unknown_birth_time#2 | 叙述类 | 约饭、谈副业、人际财务等具体场景及未知时辰下的细化安排，超出条件式反思；未把精确时间安排另行改成原评分之外的新编造失败。 |
| Daily-single / daily_investment_risk#3 | 叙述类 | 未经用户提供的“有人给你一个看似不错的投资建议”被列入彼此呼应。 |

Daily-single另有 `daily_today_general#1` 的编造维度false，但它是retry_limit，不进入已提交编造主表。评委把真实的“尚未完成解读”错误提示当编造；该提示与trace一致，此指控存在维度混用，原分仍保留。

其他组已评分提交没有原编造维度false。Name-pipeline的 `name_career_grid#3` 未评分，不能补成无编造。计数表因此为5组完整、Name-pipeline不完整。已评分pipeline事实类观测为0，仍不能宣布完整零编造。

36条每日请求的事实索引见 [fact-review.json](fact-review.json)。该索引涵盖35条daily_result与1条独立工具计算，保留UTC、本地时间、日段、相位、每日一牌和额外塔罗抽牌记录。
