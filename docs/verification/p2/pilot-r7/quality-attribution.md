# r7 质量失败、修复与降级归因

依据本轮原始回答、四维评委理由、实际计算事实和拒绝稿复核，保留全部原始评分。复核由助手完成，不是独立人工校准。原始摘录见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md) 和 [pipeline-problems-raw.md](pipeline-problems-raw.md)。

## 解梦 pipeline：8 次修复、2 次降级

18 条全部提交、质量全部通过，但其中存在可定位的安全校验误拒。8 个发生修复的回答对应 10 份拒绝稿，已使用各自实际计算事实逐份离线回放，10/10 重现，见 [validation-replay.json](validation-replay.json)。

| 回答 | 原因与处理 | 复核 |
| --- | --- | --- |
| flood_and_snake#1 | 第 1 稿解释未命中的“游来游去”，并补入“不敢靠近”；第 2 稿用“原地不敢下去”推心理；最终 keywords 降级 | 按现有闭集规则拒绝；“不敢下去”是状态，提取器有意不把它当独立词条，但不因此授权独立解读。未发现“画面”误拆。 |
| hospital_health#1 | 引号中的“生病住院”连同紧张感作解读，而“住院”在该次提取中未命中；修复删去后通过 | 按未命中意象规则拒绝。不是否定“预兆”误拒。此处复述与解读相邻，严格边界仍有表达成本，原句完整保留。 |
| flood_and_snake#2 | 用“你站在床上不敢下去，说明……”解释事实表外的状态 | 按现有状态闭集规则拒绝；修复后提交。 |
| lost_in_mall#2 | 补写“空间大、出口多”，再作选择心理推断，收尾也独立写“梦里的出口” | “找不到出口”可归入迷路，不授权单独解释“出口”或补出数量；修复后提交。 |
| chased_to_exam#3 | 解读未命中的“考场”为检验、评价；另报“发现”片段 | 考场越界成立，修复删除该层。错误定位片段“发现”较粗，不能将片段本身等同新意象。 |
| flood_and_snake#3 | 从“蛇在水里游来游去，你没有靠近它……可能说明”推心理 | 按事实表外情节解读拒绝；修复后提交。 |
| lost_in_mall#3 | “结合你迷路时想找出口的处境，也许反映……”触发完整迷路构式之外的出口检查 | 原话为“到处找不到出口”，不单独授权“想找出口”。按现有受控构式边界拒绝，但属于自然改述仍受限制的候选；没有悄悄扩展出口豁免。 |
| hospital_health#3 | 两稿标题“那要不要去做检查”均被读成“不要去做检查”，最终 safety 降级 | **明确误拒**：正反疑问句的引导词“那”不在识别范围内。正文已建议有不适就医，仍无法消除标题误判。见 [validation-findings.md](validation-findings.md)。阻止 B 通过。 |

## 姓名 pipeline

18 条全部提交、质量全部通过；0 次修复、0 次降级。未观察到共同主语或字形确认相关误拒，不能据此推断所有自然表达都已覆盖。

## single 质量失败（解梦与姓名）

| 批次／回答 | 原评分失败维度 | 原文复核 |
| --- | --- | --- |
| Dream / flood_and_snake#1 | direct_answer、supported_conclusion | 重复处理错误后 retry_limit，只返回失败说明，无有效解读。 |
| Dream / teeth_falling#3 | direct_answer、supported_conclusion | 同上，虽命中掉牙但没有带释义的提交。 |
| Dream / chased_to_exam#3 | no_fabricated_facts | 把“最近手头有一件拖着不想碰的事”“你对自己有一套挺紧的进度表”等场景写成现实经历；叙述类。 |
| Dream / flood_and_snake#3 | direct_answer、supported_conclusion | retry_limit，没有完成解读。 |
| Dream / hospital_health#3 | direct_answer、supported_conclusion | retry_limit，没有回答健康担心或检查问题。 |
| Name / without_lead_in#1 | direct_answer、supported_conclusion | 用户已给“陈思远”和五格问题，却再问本人／孩子、出生资料，没有正面作答；不是必要字形确认。 |
| Name / ambiguous_form#3 | direct_answer、supported_conclusion | 计算赵杰后 retry_limit，无带释义的解读；不把错误说明算成提交。 |

解梦 single 另有 text 和 ask_user 各 1 条，姓名 single 另有 4 条质量通过的追问；即使评分通过，也不计入已提交解读的分母。

## 每日运势

### single：18 条提交，12 条质量通过

| 回答 | 原评分失败维度 | 原文复核 |
| --- | --- | --- |
| unknown_birth_time#1 | time_consistent、supported_conclusion、no_fabricated_facts | 把约定没对齐、邮件漏附件、反复改事等细节补成用户处境，列叙述类。按精确相位排事务，且把当地 19:43–22:42 的时段写成下午，确有时间问题；评委质疑今天固定为 11-05 则与本轮计算日期不符。未知时辰的代理与不解读宫位说明正确。 |
| today_general#2 | time_consistent、no_fabricated_facts | 把上午一句话觉得不被尊重、晚上补事等写成用户处境，列叙述类；UTC 08:01 的月金四分为上海 16:01，正文却安排在上午。评委以 event_count=5 否定“共15条计算事实”不成立：实际 evidence 为15条，事件与引用条数不同。 |
| tomorrow_work#3 | time_consistent、supported_conclusion、no_fabricated_facts | 补入明天被交办、上级指令、协调两头等现实场景，列叙述类；“合作与推进都顺”等推论过强。评委的日期质疑证据不足：实验当地11-05，计算日期11-06正确，且理由自身承认UTC换算正确。保留时间失败原分。 |
| today_family#3 | time_consistent | 把UTC 08:01月金四分说成“中午前后”（实际16:01），又将UTC 15:00流日段起点说成“下午三点后”（实际23:00）。确有时区误述；安全免责声明没有消除时间错误。 |
| unknown_birth_time#3 | supported_conclusion | 把象征关系外推为“脑子清楚、愿意动手”及适合大额决策与否，支撑不足。评委所说正财段“15:00–16:00”实际是UTC，当地为23:00–次日00:00；正文的“傍晚之后”也不准确。月亮三个相位的当地时间约19:43、20:51、22:42，正文称“白天到下午”；这是原time_consistent=true未抓到的问题，另记复核、不改分。 |
| investment_risk#3 | time_consistent、supported_conclusion | UTC 15:00的流日边界被说成“接近傍晚”，且称“甲申时”混淆流日段与时柱；把流月戊戌伤官混为本命月柱（本命为癸巳七杀），又仅凭缺金推理财短板。no_fabricated_facts原评分为true，因此不悄悄加入编造失败计数，另记实际事实混淆。 |

编造分类只针对原评委的 no_fabricated_facts=false 回答，不能把其他维度的问题直接并入计数。评委既有可疑扣分，也有漏判；完整原理由与原文均保留，详见 [fabrication-review-notes.md](fabrication-review-notes.md)。

### pipeline

18条全部提交，11条质量通过，3次修复、3次safety降级。三个投资回答均因否定“稳赚”的自然变体被拒，两稿共6份均离线重现 `hard_claim` 安全命中。

| 回答 | 原评分失败维度／修复 | 原文复核 |
| --- | --- | --- |
| today_family#1 | time_consistent、supported_conclusion、no_fabricated_facts | 原评委以相位释义的relationship权重为0否定家庭协作解释，并列为编造；按其指控列叙述／解释扩展类。权重为0在代码中是无方向，不等于禁止通用建议；未发现其所指的相位值或日期写错。评分有争议，原分保留。 |
| unknown_birth_time#1 | time_consistent | 原文明确当地00:00–23:00及23:00–24:00。评委也承认正确，却以24:00即次日00:00为歧义扣分；没有充分证据证明实际时间越界。 |
| investment_risk#1 | supported_conclusion；1次修复、safety降级 | 两稿分别含“别把一时的配合顺畅当成稳赚”“别把一时的顺畅配合当成稳赚”，明确否定仍被拒。最终模板不作投资解读，评委判用免责代替作答。 |
| today_general#2 | time_consistent | 评委把UTC前日、上海当日视为超出单日范围，混淆时区；当地分段正确，时间失败原分保留。 |
| tomorrow_work#3 | supported_conclusion、no_fabricated_facts | 评委用本命盘内相位反驳行运相位，指控火星/金星三分写错；实际daily_result.events就是三分，木星/天王星为四分，与原文一致。按原相位指控列事实类，但不是已确认编造。另有引用覆盖不足：evidence仅5条日柱和卡牌，无行运引用。 |
| unknown_birth_time#3 | time_consistent、supported_conclusion、no_fabricated_facts | 布尔分数与理由互相冲突：理由承认时间、依据、条件句基本成立，却三维false。编造理由主要是“网页面板、/evidence”无事实表依据；该行实际由common/tools.py固定渲染，计数也与12条evidence一致，不是模型自造。保留原指控为可核验产品事实／引用说明类，不能说已证实编造。 |
| investment_risk#3 | supported_conclusion；1次修复、safety降级 | 标题“别把顺手当成稳赚”、正文“别把‘配合顺’误解为‘稳赚’”均为否定而被拒；第二稿保留后者，仍拒。最终模板被判缺少完全不作解读的依据。 |
| investment_risk#2 | 原评分通过；1次修复、safety降级 | 两稿均含“别把顺手当稳赚”，仍因受控宾语范围不足被拒。最终模板四维通过，不能据此抹去误拒。 |

全部11次修复、5次降级均已在本文件归因（解梦8/2、姓名0/0、每日3/3）。16份拒绝稿的回放中，解梦10份精确重现原问题，每日6份重现共用安全规则命中；10个最小检查见 [validation-replay.json](validation-replay.json)。全部20条四维质量失败均保留原理由与回答，助手复核没有改分。
