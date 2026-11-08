# 编造失败分类依据

分类由 Codex 离线读取原始回答、评委理由和计算结果完成，不是负责人逐条裁决或独立人工校准。
全部原始布尔评分保留；分类仅拆分 `no_fabricated_facts=false`，不把其他维度的失败当成编造。
计数表的“完整”只表示评分覆盖齐全、没有未分类失败。

## AstroFinal-single：下周合作，第2次

原始评委四维仅 `no_fabricated_facts=false`，按其理由归为**叙述类**。
评委认可出生资料、落座、宫位及行运依据，但质疑把象征推理写成用户已有特征。
正文包括“你容易在沟通里要么过度理想化对方、要么为安全感退让”、
“对方往往觉得你好沟通、愿意听”、“你在实际利益上的判断力其实很好”等表述。
这类指控针对未经用户提供的行为与能力归因，未指向可核验星盘事实的错误，因此该项不记事实类。
“容易”等倾向词是否已足够限定、星盘性格概括与用户已知特征之间的边界仍可复核，原分不改。

single：已提交8条全部评分，编造评分失败1条，事实类0，叙述类1/8（12.5%）。
pipeline：已提交12条全部评分，编造评分失败0条，事实类0，叙述类0/12（0%）。
这些是按原始评委失败计数的指标，不证明所有答案不存在漏评。

两组全部回答与完整理由见 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)，
分类输入见 [fabrication-reviewed.yaml](fabrication-reviewed.yaml)，汇总见 [fabrication-counts.md](fabrication-counts.md)。
