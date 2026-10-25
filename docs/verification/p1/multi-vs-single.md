# 多体系实验登记

2026-10-24。数据集 `evals/cases/p1_multi.yaml`：原有4个多体系题和8个 trajectory 改写题，均把合成画像和明确日期写入原问题。与17场景heldout分开。

每种模式12题×3，依次 single、multi、multi-lite；各题内部专家允许原有的并行机制，各跑批之间串行。被测 deepseek-flash，评委 deepseek-v4-pro，rubric v2。同厂商局限和未经人工校准状态必须披露。固定源码快照、数据集哈希、相同预算和模型参数。

|指标|single|multi|multi-lite|
|---|---|---|---|
|样本完成|待运行|待运行|待运行|
|任务/质量/严格通过|待测|待测|待测|
|同题三次配对胜负|待测|待测|待测|
|张力披露覆盖|待测|待测|待测|
|专家报告合规率|不适用|待测|待测|
|每题模型调用、输入输出token|待测|待测|待测|
|缓存、每题估算成本|待测|待测|待测|
|P50/P95延迟|待测|待测|待测|

multi-lite 的 astro/bazi/tarot 前置调用由代码规划，经同一 Guard/trace；缺资料返回needs_input，完成计算后模型只写报告，最多两次真实报告/纠错调用。name/dream保留agent。代码计划记tool_plan，不冒充零token的真实模型调用。

尚无对照结果，因此不新增 auto，不更改默认single/agent，也不声称multi-lite提高质量或降低成本。若多模式优势不稳定，报告逐题波动而不是择优取一轮。
