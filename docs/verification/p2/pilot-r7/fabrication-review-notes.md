# r7 编造分类复核说明

分类只覆盖原始评委对已提交回答标出的 `no_fabricated_facts=false`；不改原分、不补跑。由助手对照回答、评委理由和本次计算事实复核，**不是独立人工校准**。既有脚本表头“待人工判定”是工具术语，不代表本轮已有独立人工审查。

| 批次／回答 | 分类 | 依据 |
| --- | --- | --- |
| Dream-single / chased_to_exam#3 | 叙述类 | 回答说“你最近手头有一件拖着不想碰的事”“你对自己有一套挺紧的进度表”，用户只提供了梦境，现实经历没有依据。 |
| Daily-single / unknown_birth_time#1 | 叙述类 | 评委的编造理由针对“约定没对齐、邮件漏了附件、反复改同一件事”等具体生活情节。没有把时辰未知改写为已知，也没有补出宫位。日期与时段异议另列，不混入此分类。 |
| Daily-single / today_general#2 | 叙述类 | 评委的编造理由指向上午觉得不被尊重、晚上补事情等用户处境。时间安排确有误差，但分类依据是该维度理由，不能仅因其他维度含时间错误就同时记事实类。 |
| Daily-single / tomorrow_work#3 | 叙述类 | 原文推入明天被交办、上级指令、协调两头等现实情节；虽然多处使用“容易”，原评委仍从严判失败，保留原分。 |
| Daily-pipeline / today_family#1 | 叙述类 | 原评委否定的是把相位的协作释义套入家人关系，且明确承认没有编造具体事件；不是可核验的相位、日期或出生信息错误。按原失败保留为叙述／解释扩展类，此标签不表示已证实编造了用户经历。 |
| Daily-pipeline / tomorrow_work#3 | 事实类 | 原评委明确指控月火、月金相位写错，按该指控归事实类；复核发现它把本命盘内相位与行运月亮对本命星体的相位混同。实际行运为三分，原回答在这一点正确，故不能把本项计数解释成已确认的相位编造。 |
| Daily-pipeline / unknown_birth_time#3 | 事实类 | 原指控是“共12条计算事实、网页面板、/evidence”无依据，属于可核验的产品事实／引用说明，不是用户经历。计数与12条evidence一致，该句由common/tools.py固定生成，cli.py也实际支持该命令；这是评委误把程序渲染说明归为模型编造。 |

## 评委理由的异议与漏判

- `unknown_birth_time#1`：今天为2026-11-05，与计算日期一致，“没有确认今天”不足以证明日期编造。时间方面仍有可核实错误：把当地晚间相位写成下午，不能因此整条补分。
- `today_general#2`：“解读依据共15条”与结构中的15个evidence一致。`event_count=5`是天象事件数量，并非全部日柱、关系、卡牌引用数量；原评委把两者混同。UTC 08:01相位应为上海16:01，正文的上午表述仍有误。
- `tomorrow_work#3`：本轮11-05运行，计算日期11-06就是明天；评委也承认UTC/当地转换正确。其时间失败缺少充分根据，原分保留。
- `unknown_birth_time#3`：原 `time_consistent=true`，但正文把UTC 15:00起的正财段写成傍晚，且把当地19:43–22:42相位说成“白天到下午”，有时间漏判。原 `supported_conclusion=false` 保留；评委的“15:00–16:00”也未转换为当地时间。
- `investment_risk#3`：原 `no_fabricated_facts=true`，但 `supported_conclusion` 理由和原文可见流月/本命月柱混淆，原事实为本命癸巳、流月戊戌。按既定计数口径不额外制造一条编造失败；本报告单列此漏判，不能将事实类表格理解为已证明所有回答零事实错误。
- `Daily-pipeline / today_family#1`：`theme_map.relationship=0`表示合并时无方向，不等于禁止把通用协作建议用于关系反思。原释义确实含“较顺的协作”，因此评委的主题推断不足以直接证明编造；这主要是解释支持边界争议。其时间理由也承认相位在当日，未指出具体日期错用，保留原分并标注异议。
- `Daily-pipeline / unknown_birth_time#1`：评委承认00:00–23:00及23:00–24:00边界正确，却因24:00为次日00:00而扣分。同一瞬间的两种表示不能单独证明时间错误，未发现实质日期越界。
- `Daily-pipeline / today_general#2`：评委把UTC前一天、当地当天视为超出当日，混淆时区范围；原理由同时承认当地分段正确，时间扣分证据不足。
- `Daily-pipeline / tomorrow_work#3`：本轮 `daily_result.events` 明确为行运月亮对本命火星/金星三分、对木星/天王星四分，原文吻合。评委拿本命盘内相位反驳，属于事实层次混淆。该回答的evidence只列5条日柱/卡牌，没有对应行运相位引用，引用完整性另有不足；这不能反过来证明相位值被编造。可核对 [fact-review.json](fact-review.json)。
- `Daily-pipeline / investment_risk#1` 与 `#2`：相同拒绝投资方向的safety模板，前者因“用免责代替作答”判supported=false，后者四维通过；两者卡牌不同，但没有分别解释牌义。不能把模板质量差异都归为代码行为差异。
- `Daily-pipeline / unknown_birth_time#3`：理由承认time_consistent、supported_conclusion基本成立，布尔值却均为false；编造理由针对的产品说明由 [common/tools.py](../../../../common/tools.py) 的 `evidence_count_line` 固定生成，[cli.py](../../../../cli.py) 支持 `/evidence`，不是模型补出的经历或计算。12条与实际引用一致，证据见 [fact-review.json](fact-review.json)。保留原评分与事实类指控，不能用这两条有争议的事实类计数断言流水线已确认编造2条。

机器可读分类见 [fabrication-reviewed.yaml](fabrication-reviewed.yaml)，原始评分与回答见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)。原始失败仍计入统计与门槛，争议项没有补分；事实类计数与已确认事实缺陷不能混为一谈。
