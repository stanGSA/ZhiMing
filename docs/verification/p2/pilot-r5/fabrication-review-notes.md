# P2 r5 编造分类依据

分类只针对已提交且原始 `no_fabricated_facts=false` 的回答；一条可归入一类以上，计数仍按失败回答去重。原评分、回答和理由保持原样。

| 回答 | 分类 | 依据 |
| --- | --- | --- |
| `Name-single/name_compound_surname#1` | 叙述类 | 把数理象征说成家里支持、早年环境及用户既有做事经历。 |
| `Name-single/name_compound_surname#3` | 叙述类 | 把吉数象征写成用户已有长辈缘、外部机会与贵人经历。 |
| `Daily-single/daily_today_family#1` | 叙述类 | 由象征推断具体身体感受，且部分家庭互动写成用户现实状态。 |
| `Daily-single/daily_today_general#2` | 事实类 | 把未经用户提供的出生日期写成已知生日。 |
| `Daily-single/daily_tomorrow_work#2` | 叙述类 | 从偏财象征扩展出“午后机会感增强/一时兴起”的具体生活场景。 |
| `Daily-single/daily_unknown_birth_time#2` | 事实类 | 把系统档案中的 11 月 2 日生日写成用户已提供事实。 |
| `Daily-single/daily_investment_risk#2` | 叙述类 | 把相位落成上午、中午、晚间可能经历的具体情绪与事件时段。 |
| `Daily-single/daily_today_general#3` | 事实类 | 正文加入计算事实未列出的“壬与年干相冲”。 |

计数为事实类 3、叙述类 5（其中分类表按批次计为 3 和 3，是因为 `Name-single` 的两条均属叙述，`Daily-single` 另有 3 条叙述；合计叙述类实际为 5）。分类由助手复核自动评委证据，不代表人工校准评委。
