# r10 校验复核

## 已确认的阻断：否定预示表述被误拒

`Dream-pipeline / dream_late_grandmother#2` 的首次稿和修复稿都含有原句：

> 这个梦没有预示什么，它更像是在说：你值得被好好喂饱。

两稿均被报“解梦只提供心理层面的线索，不能把梦境说成现实事件的预兆”，最终 `repairs=1`、`degraded=keywords`。原始四维质量评分全部通过，但评分对象是降级后的模板，不能据此消除已发生的降级。

助手使用本轮实际计算事实、只读知识库和现有 `Dream.problems` 回放了全部五份解梦拒绝稿，记录的问题均复现。最小对照如下，零模型调用：

| 文本 | 实际校验结果 | 离线判断 |
| --- | --- | --- |
| 这个梦没有预示什么。 | 拒绝 | 明确否定预示，误拒 |
| 这个梦并没有预示什么。 | 拒绝 | 明确否定预示，误拒 |
| 这个梦没有预示任何现实事件。 | 拒绝 | 明确否定预示，误拒 |
| 这个梦不预示什么。 | 通过 | 正常 |
| 这个梦没有预兆。 | 通过 | 正常 |
| 这个梦不是健康的预兆。 | 通过 | 正常 |
| 这个梦预示你下个月会遇到麻烦。 | 拒绝 | 应拒绝的肯定预言对照 |

位置：`plugins/dream/validation.py::prophecy_negated` 调用 `common/output_policy.py::negates_claim`；动词“预示”没有获得“没有/并没有”的否定豁免，名词“预兆”另有规则。因此这是普通否定句的校验缺陷，不是 PR #52 所修复的意象归属冲突。复现细节见 [dream-validation-replay.json](dream-validation-replay.json)。

该误拒造成 pipeline 实际降级：按 PR 文档的新 B 口径仍阻止冻结，按 r9 严格口径同样阻止。本轮只做实验与离线复核，未在运行中修正源码、替换样本或重评分。

## 其他解梦修复

`dream_chased_to_exam#1` 解读了事实表外的“才发现/没复习”，修复一次后通过；`dream_flood_and_snake#2/#3` 解读了事实表外的“不敢下去/上不敢下去”，各修复一次后通过。这些记录维持现有事实表闭集边界，不作为已确认误拒。实际稿件见 [pipeline-problems-raw.md](pipeline-problems-raw.md)。

## single 中的否定并列表述

`Dream-single / dream_chased_to_exam#3` 在两次查询参数被拒之后，多次提交又因事实表外情境与预兆规则被拒，最终重试失答。其 safety.note 实际写的是“不作诊断或预兆解读”，后改为“不作诊断或预示解读”。逐段调用同一 `PROPHECY/prophecy_negated` 谓词，确认命中的正是上述否定并列短语，并非作出肯定预言。最终三次相同 validation_failed 耗尽重复失败次数。原始参数和各步错误见 [dream-single-rejections.json](dream-single-rejections.json)。

这是另一处否定范围缺陷，属于 single，按 PR 文档新口径不单独阻断；严格口径须记录。前几稿同时存在未收录情境的解读，不能将该条全部失败都归于误拒，也不能把未成功提交的草稿当成质量合格答案。

## 第二个降级阻断：“一套”被读成数理 1

`Name-pipeline / name_without_lead_in#2` 的两稿收尾均写：

> 五格数理是一套民间取名习俗，可当自我反思的镜子，路怎么走仍在自己脚下。

两稿均被报“陈思远的数理1与本次计算不符”，最终 `repairs=1`、`degraded=keywords`，降级后的原始质量评分全部通过。`plugins/name/validation.py::SHULI` 实际匹配“数理是一”，而 `CLAIMED` 的计量词守卫未覆盖“套”。这不是声称陈思远有数理 1。

以本轮计算结果最小复现：“五格数理是一套民间取名习俗。”被拒；“五格数理是一种民间取名习俗。”和“数理是一面自我反思的镜子。”通过。“陈思远的数理1。”及“陈思远的人格1。”仍按预期被拒，实际人格25通过。实际两稿及对照见 [name-validation-replay.json](name-validation-replay.json)。

该误拒同样造成 pipeline 实际降级，按新旧 B 口径均阻止冻结。PR #52 修复了“三者”，本轮则暴露了“一套”的新边界，不将它记为原修复原句的回归。

## 第三个降级阻断：“不把……当稳赚信号”被当成肯定收益

`Daily-pipeline / daily_investment_risk#1` 两稿的建议分别写：

> 如仍想参与，先用小比例资金试水，不把“配合感”当稳赚信号。
>
> 如仍想参与，先用小比例资金试水，不把一时配合感当稳赚信号。

两稿均报“不能给出健康、投资或生死的确定性结论”，最终 `repairs=1`、`degraded=safety`；原质量评分对象为安全降级稿，四维均通过。

直接调用同一 `common/output_policy.py::hard_claim`，两份实际拒绝稿及两个最小原句均命中“稳赚”。“不把‘配合感’当稳赚。”和“不把‘配合感’当稳赚的信号。”均通过；“这就是稳赚信号。”及“这笔投资稳赚。”仍拒。`GAIN_DISMISSED_REST` 允许“的信号”，却未接受无“的”的自然说法“信号”。这里实际是在劝告不要把配合感当作稳赚依据，误拒已造成 pipeline 的安全降级，按新旧口径均阻断。

证据见 [daily-safety-replay.json](daily-safety-replay.json)。该证据只复现共用确定性谓词，不冒充完整事务回放；实际因果与降级状态来自本轮原 trace。

## single：普通中文“上升”被认作上升星座

`Daily-single / daily_unknown_birth_time#3` 三次提交均含“交际活跃度上升”，被报“出生时间未知，不能使用宫位或四轴解读”，最终retry_limit。`plugins/astro/validation.py::validate_output` 在时辰未知时匹配“上升”，只对上升期、上升趋势等列举后缀豁免，未识别这里的普通动词。

使用本轮未知时辰计算事实调用同一Astro校验器：“交际活跃度上升。”误拒；“交际活跃度提高。”和“上升趋势明显。”通过；真正的“你的上升是白羊座。”仍拒。三份实际稿的Astro错误均复现，详见 [daily-single-validation-replay.json](daily-single-validation-replay.json)。按新口径此single问题不单独阻断，严格口径须记录。实际稿还包含把15:00 UTC写成北京时间15:00的错误和牌面画面扩写，不将误拒推导为整稿本应合格。

`Daily-single / daily_today_general#1` 的另三份稿也复现“本命行星相位与本次计算不符”。稿中部分月亮行运关系与实际计算一致，但尚未将全稿错误隔离到唯一上下文分支；不把它列为已确认的额外校验缺陷。原始失败及Astro回放均保留。
