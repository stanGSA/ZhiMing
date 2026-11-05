# r8 编造指控复核

助手按既定口径复核，仅对**已提交且原始 `no_fabricated_facts=false`** 的回答分类；保留评委原分。其他维度失败和另外发现的漏判独立记录，不人为新增原始失败键。这不是独立人工校准，也不代表负责人逐条裁定。机器分类见 [fabrication-reviewed.yaml](fabrication-reviewed.yaml)，计数见 [fabrication-counts.md](fabrication-counts.md)。摘录中的“初筛／待人工判定”是提取工具未加载复核文件时的提示，以这里及分类文件为准。

| 组／回答 | 原始指控与原文核对 | 分类 |
| --- | --- | --- |
| Name-single / name_compound_surname#2 | 将数理象征写成本人的习惯和经历：“习惯先照顾外部期待”“你是被小事磨”等；未坚持条件句或象征性表述 | 叙述类 |
| Daily-single / daily_unknown_birth_time#3 | “开会时忍不住指出问题”“对家里安排多年做法不耐烦”等把象征变成具体个人状态；五行简单计数推性格还涉及结论支持不足 | 叙述类 |
| Daily-pipeline / daily_today_family#3 | “你觉得自己的意思很明白，对方却理解成另一回事”“家人之间常常是嘴上说没事，心里各有各的节奏，今天这种若有若无的别扭感容易冒出来”并非条件式场景 | 叙述类 |

三条指控均已分类，其他组没有已评分的原始编造失败。**Daily-pipeline 仍有 1 条未评分**：`daily_unknown_birth_time#3`，评委两次解析后 ValueError，不能当作 no_fabricated_facts=true，也不能自行指定失败维度。其已观察事实类为0、叙述类为1，但全组事实类零不能确认；叙述类占已提交只能报 5.6%–11.1%。其余组计数完整。审计中的已知失败键覆盖为真，与整轮分类统计尚不完整并不矛盾。

另外发现 `Name-single / name_compound_surname#2` 写“天格木生人格水”，实际为天格木、人格水、天人关系“被生”，应为水生木。原评委 `supported_conclusion=true` 漏掉这一方向错误；原始 no_fabricated_facts 指控只针对叙述，因此不把该键再加为原始“事实类失败”。证据见 [fact-review.json](fact-review.json)。已观察事实类0不等于所有回答没有事实错误。

日期上下文误判、UTC 转换争议、时间分段表述和 safety 模板失答见 [quality-attribution.md](quality-attribution.md)。所有问题继续保留原分，没有补跑或人工改成通过。
