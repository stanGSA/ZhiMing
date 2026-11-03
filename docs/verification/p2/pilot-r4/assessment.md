# P2 r4 实验与复核：不冻结

2026-11-03；PR #46 合并和审查修复后的被测提交为 `0357a99c85ec5b49a43df2ba1a78cbc0a94ec30f`。六组各18条，共108条运行记录，106条有效四维评分。服务恢复后的串行实验从09:17:02至11:02:59 UTC（北京时间17:17至19:03），约1小时45分57秒。

| 体系 | single已提交 | single已提交质量 | pipeline已提交 | pipeline已提交质量 | pipeline最多返回调用 | 修复/降级 |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 解梦 | 13/18 | 12条通过、1条未评分 | 17/18 | 17/17（100%） | 3 | 7/0 |
| 姓名 | 9/18 | 8/9（88.9%） | 18/18 | 18/18（100%） | 2 | 2/2 |
| 每日运势 | 17/18 | 10/17（58.8%） | 18/18 | 16/18（88.9%） | 1 | 0/0 |

**不满足事先确定的 B 标准，不冻结，不执行 p2-final。** 原因包括：解梦pipeline有一条模型服务超时，提交未达18/18；解梦single有一条已提交回答缺失评分，因此六组编造分类表未全部完整；另已离线复现多项代码校验误拒。评分和规则问题必须分开保留，不能通过删除服务故障、补判或重跑失败样本使本批“通过”。

三个pipeline的步数/预算失败均0；按既有报告口径，成功返回的每轮模型调用最多3/2/1。但解梦pipeline最慢故障样本包含请求重试：运行端4次实际请求尝试仅1次成功返回，评委3次请求均超时；不能把“返回调用≤3”说成“所有网络请求≤3”。实际请求数另见[integrity.json](integrity.json)。姓名和每日运势的提交及调用数条件满足，pipeline已提交质量均不低于同批single；解梦single未评分使其质量区间为12/13至13/13，pipeline已提交为17/17。完整任务、提交、工程通过、质量通过及配对结果见[完整对照](comparison.md)。

## 可复现误拒

| 位置 | 原句与后果 | 离线证据 |
| --- | --- | --- |
| `plugins/dream/validation.py::phrase_hits/ungrounded` 与 `NORMALISATIONS` 边界 | 已命中掉牙后，“牙齿一颗一颗掉下来”通过，同义的“牙齿一颗颗掉下来”仅复述也拒；`dream_teeth_falling#1`多一次修复 | [解梦重放](false-rejection-replay.json) |
| `plugins/name/validation.py::GRID/SHULI/check_claims` | 把“人格是五格里的五”“总格三项的三”“外格一项的一”“数理是一份的一”等识别成格数；4条single重试耗尽，1条pipeline降级 | [姓名重放](name-false-rejection-replay.json) |
| `common/output_policy.py::negates_claim/NEGATED_NOUN` | “而不是把它理解成必然的坎坷”否定宿命论却被拒；修复稿保留后再次拒，1条pipeline降级 | [否定句重放](certainty-false-rejection-replay.json) |

原始报告不改动，被测代码不在本批运行期间修复。姓名及共享措辞校验在r3/r4间没有变化，本轮通过新原句定位，不能将其称为PR #46引入的回归。解梦7次修复全部见[解梦归因](dream-attribution.md)，姓名2次修复和2次降级见[姓名归因](name-attribution.md)。投资题single还因今日摘要没有明确“行运”标记而触发本命相位检查；同实际事实表仅加“行运”两字后接受，详见[上下文重放](daily-context-replay.json)，不应将该次错误解释为计算事件不存在。

## 质量与编造复核

全部23条未通过或未评分结果均已逐条核对（21条false、2条null），见[质量归因](quality-attribution.md)与[原理由、回答全文](quality-reasons-with-answers.md)。未更改原布尔分数，也没有额外调用评委补分。

53条已提交pipeline回答的原编造失败为0；那条model_error没有提交且未评分，不能据此宣称54条全部无编造。已提交编造失败共7条：姓名single 1条（事实类及叙述类各1），每日single 6条（事实类5、叙述类5），可双重分类但失败数只计一次。判定key恰好覆盖原始已评分编造失败；Dream-single仍有1条已提交未评分，所以其分类表“不完整”，不是确认零。详见[计数](fabrication-counts.md)、[判定YAML](fabrication-reviewed.yaml)、[分类依据](fabrication-review-notes.md)。

每日pipeline两条质量失败均出自幸运色题，且没有修复/降级：

- `daily_lucky_color#1`支持性false。评委称23点后四项关系缺少时段依据，但实际引用ref_id已绑定15:00 UTC的壬午段（当地23点）；牌面“控制资源”的措辞强弱仍可讨论。保留原失败。
- `daily_lucky_color#3`时间false。评委理由又承认水海当地07:27、月木18:53均为当天、流日边界正确，未指出与原答相冲突的时刻。保留原失败，不用复核替换16/18。

每日single存在真正的UTC/本地时间混用，部分被评委漏判；姓名single一条生克方向错误也由复核补充识别。评分可靠性未独立验证，不能只凭同模型评委分数宣称没有语义错误。

## 完整性、实际模型与首次中断

- 各组18条题目/重复编号唯一，每题0/1/2齐全，single/pipeline配对相同。六组174个被测文件哈希一致，且逐文件匹配实验结束的代码及实验配置副本；源码指纹 `07482587277dcf97facc0ed4e2b24af236e94fb98cbe04a81f768742d6ac55e0`。原始报告与摘要及raw-manifest SHA256全部匹配。
- 实验配置SHA256恰为图片要求的 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`；结束后已逐字节恢复本机原配置 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`，不提交config.yaml。
- 请求及所有成功运行/评委返回模型字段均为 `deepseek-v4.1-flash`。`eval_judges.pro`只是配置名称，实际也是Flash，thinking disabled。r3实际返回 `deepseek-v4.1-flash-sg`，跨批分数变化不能只归因代码；未新增独立评委或服务身份验证。自动comparison模板底部的“Pro”是通用文案，实际模型以本报告和逐组摘要为准。
- pricing.yaml与r3逐字节相同；中转费率未核验，费用未知。
- 首次08:55至08:56 UTC的尝试因服务不可用中断，3条model_error不计入本次108条。历史报告及诊断保存在[interrupted-attempt](interrupted-attempt/assessment.md)，重试前最小接口检查09:16:48 UTC成功。此次模型运行中又出现上述超时，保留为本次故障，不剔除。
- 当前campaign状态complete及外层退出0只说明六组结束；5组评估退出1、姓名pipeline退出0。campaign.json仍保留首次中断的旧error_type字段，不能据此忽略当前complete/时间戳或反过来说本批没有失败。

原始数据库、live.json及trace留在本机 `reports/p2-r4/`；按r3流程发布合成题回答和被拒草稿证据，未发布本机配置或密钥。完整步骤见[reproduction.md](reproduction.md)，发布文件哈希见[evidence-manifest.json](evidence-manifest.json)。
