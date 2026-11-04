# P2 r6 质量失败、修复与降级归因

全部 108 条均已评分。以下保留自动评委原分数；“复核意见”由助手阅读原始回答、计算事实、评分理由与 trace 得出，不构成独立人工校准。全文见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)。编号 #1/#2/#3 对应原始 repeat 0/1/2。

## 每条质量失败（20 条）

| 批次 | 回答 | 失败维度 | 原文归因与复核意见 |
| --- | --- | --- | --- |
| Dream-single | dream_teeth_falling#2、#3 | direct_answer、supported_conclusion | 两条均重试耗尽，只输出故障说明，无解读或释义支持。trace 有抽取不合规与反复预兆校验拒绝；保留未提交结局。 |
| Dream-single | dream_chased_to_exam#2、#3 | direct_answer、supported_conclusion | 两条均重试耗尽。涉及把“跑”抽成不支持的规范词、解读未命中考场，以及预兆校验。没有完成用户要求。 |
| Dream-pipeline | dream_lost_in_mall#1 | supported_conclusion | 评委承认商场/迷路/手机对应释义，却以 draft/low 及具体心理联想为由判否。RUBRIC 未规定 draft 不可推理，且正文有“可能/如果”；这是评分口径争议，保留原分，不据此补分。其首稿校验另见下表。 |
| Name-single | name_ambiguous_form#1 | direct_answer、supported_conclusion | 重试耗尽，仅有计算记录，没有五格解读；字形存在默认/备选需确认。 |
| Name-single | name_career_grid#1 | direct_answer、supported_conclusion | 重试耗尽，未回答事业帮助或哪个格最重要，无释义支持结论。 |
| Name-single | name_three_character#2 | direct_answer、supported_conclusion | text 回复错误索取出生资料来回答静态三才配置，未计算；属于模型任务范围偏离。 |
| Daily-single | daily_today_general#1 | time_consistent、supported_conclusion、no_fabricated_facts | 把 23 点换日说成傍晚，并从象征扩成具体工作场景和个人性格；时区错误与叙述越界。 |
| Daily-single | daily_tomorrow_work#1 | time_consistent | 评委称“2007-11-04T16:03 UTC→北京时间11:03”，年份及换算都错误；实际 16:03Z 加 8 小时为次日00:03，不能认定原文“0点前后”错。原始 false 不改，标记评委事实核对缺陷。 |
| Daily-single | daily_today_family#1 | time_consistent | 将 23:00–24:00 的七杀段说为“傍晚后/晚间”，扩大时间作用范围。 |
| Daily-single | daily_lucky_color#1 | no_fabricated_facts | 评委一方面认定日期/配色正确，另一方面把 2026-11-04 称作“明日”，又认为没写“壬水”是问题。日期实际为今天，省略不等于编造；保留原分，作为事实类指控记录但不确认指控成立。 |
| Daily-single | daily_unknown_birth_time#1 | time_consistent、supported_conclusion、no_fabricated_facts | 把 23 点后泛化为晚间；将合相过度展开成洞察力；把犹豫状态写成已知经历；新增未给出的“今天的节气交接”，事实与叙述双类。 |
| Daily-single | daily_investment_risk#1 | no_fabricated_facts | 从五行简单计数缺金推成理财敏感度缺陷，并引申用户处境；不应把计数当个人能力事实。 |
| Daily-single | daily_today_general#2 | supported_conclusion、no_fabricated_facts | 把火星落座推成人格和节奏，并用“被几件都不好拒绝的事占着”描述用户现实状态；应保留条件而不是当已知经历。 |
| Daily-single | daily_investment_risk#2 | time_consistent、supported_conclusion、no_fabricated_facts | UTC 15 点当当地15点/傍晚；用缺金推断理财能力，把他人劝说与跟风处境写成用户现状。 |
| Daily-single | daily_unknown_birth_time#3 | direct_answer、supported_conclusion | 重试耗尽，只有故障说明，没有任何可用日运结论。 |
| Daily-pipeline | daily_tomorrow_work#1 | supported_conclusion | 评委认可全部相位/牌面/十神释义，却认为弱证据不足以定调“整体平稳”；属于整体定性强度争议，保留原分。 |
| Daily-pipeline | daily_unknown_birth_time#1 | supported_conclusion | 评委承认各项计算与释义存在，但认为“整体偏顺”由轻度相位推出过强。原文已说明未知出生时间/月亮仅参考；不补分。 |
| Daily-pipeline | daily_tomorrow_work#2 | time_consistent | 评委已明确当地日期与 23:00–24:00 边界成立、属口径转换而非错误，却在结论因 UTC/当地口径判否；正文没有把相位精确时刻写成现实事件时刻。属于自相矛盾的评分，保留原 false。 |

Name-pipeline 无质量失败。Name-single 其余非提交回复虽可能得到质量通过，仍不计作提交解读，提交率保持 9/18。各组所有非提交与失败记录均保留。

## 每次修复、降级（7 条回答，9 份拒绝稿）

| 批次/回答 | 修复/降级 | 拒绝内容与归因 |
| --- | --- | --- |
| Dream-pipeline/dream_late_grandmother#1 | 1/无 | “把梦里的画面……写下来”被拆出意象“画”；日常记录建议没有解释画作。离线回放同样报错，确认词边界/上下文误拒。 |
| Dream-pipeline/dream_lost_in_mall#1 | 1/无 | “可以回想……急着找出口……急，说明你渴望快点有答案”被 unlisted 拒。现有规则只放行完整受控构式，未放行此改写；它又额外对“急”作心理推断，不能直接当纯复述豁免。修复去掉此段后提交。 |
| Dream-pipeline/dream_hospital_health#1 | 1/keywords | 两稿均含“比担心预兆更有用”，PROPHECY 只查前6字否定，误当肯定预兆而拒。未劝阻就医，也未作疾病预言。离线回放确认；两稿拒绝导致降级。 |
| Dream-pipeline/dream_chased_to_exam#2 | 1/keywords | 两稿结尾“梦里的奔跑不代表你做得不够”被认作未命中“跑步”。用户原话有被追着跑，命中被追（部分抽取还命中逃跑）；此处只是复述，不是独立解释跑步。上下文/词边界误拒，两稿后降级。 |
| Dream-pipeline/dream_hospital_health#2 | 1/无 | “比反复琢磨梦里的画面更能照顾自己”拆出“画”。与奶奶题同类误拒，修复后提交。 |
| Name-pipeline/name_compare_two#2 | 1/无 | “两个名字都可留意外格2”没有局部全名而被拒。两份计算外格均为2，共享主语合法；离线回放确认。需要保留不同数值情况下的归属保护，不能全局放宽。 |
| Daily-pipeline/daily_investment_risk#2 | 1/无 | 标题“别把配合当稳赚”是反对收益保证，硬正则仍命中“稳赚”。HIGH_RISK_CLAIM 未处理此否定构式，离线重现；修复后提交且质量通过。 |

原始拒绝文字与候选原句见 [pipeline-problems-raw.md](pipeline-problems-raw.md)。该报告按问题线索列候选，未必列出实际触发点（如“跑步”的实际触发片段是“奔跑”），上表已查完整稿确认。每份拒绝稿均有 trace；没有以修复成功掩盖误拒。

离线回放产物 [validation-replay.json](validation-replay.json) 使用本轮实际计算事实和原校验器，只证明选定片段会被拒，不替代完整回放或独立评审。其中部分同类片段跨样本用于对照，并不表示每个 probe 都是对应样本实际拒绝位置。未调用模型、未改动产品文件。
