# P2 r8 实验评估：未通过 B，不冻结

2026-11-05 22:08:18–23:02:03（Asia/Shanghai），按负责人截图中的命令完成六组串行调参实验，共108条，退出码0。被测提交 `e01a0083f01b30383db73eae4f1a92ce8937361d`，包含 PR #50 合并及相位别名／反向角色漏检修复。实验配置沿用 r7，SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。执行期间未修改源码、提示词或样本，没有剔除、替换、补跑失败回答或改原评分。执行记录见 [decisions.md](decisions.md)、[execution.json](execution.json)。

**108条全部运行完成，107条有完整四维评分，1条评委解析失败。B不通过，不冻结，未运行 p2-final。**

| 体系 | single 提交／提交后质量通过 | pipeline 提交／提交后质量通过 | pipeline 已评分 | pipeline 最多模型调用 | pipeline 步数／预算失败 | pipeline 修复／降级 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 解梦 | 13/18；13/13 | 18/18；18/18 | 18/18 | 3 | 0 | 7/1 |
| 姓名 | 11/18；10/11 | 18/18；18/18 | 18/18 | 2 | 0 | 0/0 |
| 每日运势 | 18/18；14/18 | 18/18；14/18（3失败、1未评分） | 17/18 | 2 | 0 | 3/1 |

质量通过率以已提交回答为分母；未评分保留未知，不偷偷剔除或改成内容失败。每日 pipeline 已评分子集为14/17，但主表继续报告14条确认通过／18条提交。Dream-single另5条 retry_limit；Name-single另4条 retry_limit、2条 ask_user、1条 text，后三条虽原评委质量通过，却没有提交解读。自动表中的“质量通过”还可包含澄清回复，不等于已提交解读数量。

提交成功、任务完成、严格工程通过是不同口径：自动报告的任务完成分别为 single 13/11/12，pipeline 18/18/18（解梦／姓名／每日）；原始 `engineering_pass` 还计工具错误，为 single 0/4/7、pipeline 18/18/17。每日 single 的18条保存成功不能代替12条任务完成；每日 pipeline 第2条投资回答已保存，但因安全校验与降级，严格工程未通过。完整自动指标见 [comparison.md](comparison.md)，审计字段见 [integrity.json](integrity.json)。自动文档仍沿用“P1”标题及 Pro/Flash 模板用语；本轮实际为 P2，pro 是评委配置名，请以这里记录的实际模型为准。

## 阻止冻结的原因

- **掉牙复述误拒**：`dream_teeth_falling#1` 的“梦里牙齿是一颗一颗掉下来的”没有绑定到已命中的“掉牙”；最小对照只插入“是”就从放行变拒绝。这是既有归一化范围遗漏，本轮观察到，不能直接说由 PR #50 引入。
- **普通确定性否定误拒**：`daily_today_general#2` 的“不是事情必然顺利的保证”和 `daily_lucky_color#3` 的“别把配合当成必然有利”都被识别成肯定“必然”。两条最终修复通过不消除前稿缺陷。
- **否定“稳赚”仍有遗漏**：投资第2次的“别在情绪顺畅时把配合或行情当成稳赚”“别因为情绪顺畅就把配合或行情当作稳赚”两稿都误拒，最终 safety 降级并失答；幸运色第3次还出现“别把‘有机会’直接当成‘稳赚’”的命中。r7指定原句已回放通过，但插入状语的自然表达仍不完整。
- **评分缺失**：`Daily-pipeline / daily_unknown_birth_time#3` 两次评委解析后 ValueError，`quality_pass=null`、`scored=false`。本轮不重评分；全量评分和完整编造统计门槛无法确认通过。

三个 pipeline 均满足提交100%、调用≤3、步数／预算失败0。已评分的原始编造指控共3条，Name-single、Daily-single、Daily-pipeline各1条，均为叙述类，其他组为0。全部已知失败键已复核覆盖，但每日 pipeline 有1条未评分，所以不能宣称全组“事实类编造为零”已确认；审计区分 `observed_pipeline_fact_fabrication_zero=true` 与需要完整评分的门槛 `pipeline_fact_fabrication_zero=false`。分类统计尚不完整不是发现了另一条事实类错误。

三类校验缺陷的根因及最小对照见 [validation-findings.md](validation-findings.md)。解梦8份拒绝稿全部按本轮事实重现；每日4份拒绝稿回放共用确定性／安全谓词均重现对应命中，不冒充完整提交事务；这些回放均0模型调用。17条质量失败、1条未评分、10次修复和2次降级的归因见 [quality-attribution.md](quality-attribution.md)。原文及分类见 [pipeline-problems-raw.md](pipeline-problems-raw.md)、[quality-reasons-with-answers.md](quality-reasons-with-answers.md)、[fabrication-review-notes.md](fabrication-review-notes.md)。

## 对照及评分局限

同批提交后质量，解梦 single/pipeline 均100%，姓名为90.9%/100%，每日为77.8%/77.8%确认通过；每日后者含1条未知，不能解释为完整评分后的等效性。按事先约定调参质量比较照常报告，不单独阻止 B；最终验收仍须逐体系判定。配对胜／负／平（pipeline相对single，任务完成且质量通过）为5/0/13、8/0/10、2/2/14，未知条保留为非已确认通过。每题3次是重复测量，不是18个独立题目，以上仅作描述。

相较r7，pipeline确认质量通过数为解梦18→18、姓名18→18、每日11→14（本轮另1未知）；修复由8/0/3变为7/0/3，降级由2/0/3变为1/0/1。固定的r7原句已修好，医疗题三次直接提交，但新否定变体仍出现误拒，不能宣称整改完毕。不同版本与模型采样等同时变化，这些数字不构成 PR 的净因果效果。

运行与 pro 配置评委请求、返回均为 `deepseek-v4.1-flash`，thinking关闭、policy_judge关闭，属于同模型评分。助手复核不是独立人工校准。原评委存在把运行日11月5日当未来日期、UTC与上海归属推理冲突等问题；同时正文也确有正官时段写成23点前、姓名木生水方向错误等漏判，因此不能将全部质量失败归咎于评委。原分一律保留，事实摘录见 [fact-review.json](fact-review.json)。中转费率未核实，费用未知，见 [pricing.yaml](pricing.yaml)。

## 完整性与后续

已核对108个唯一题目／重复编号、每题0/1/2及single/pipeline成对覆盖；六组源码哈希一致且与被测文件吻合，所有原始live哈希与发布清单一致。源码指纹 `74d3ff68e54711c8b957ba9625411fd51e1498d34d415a3d0af5cee6f05c5934`。107条完整评分、1条缺失被明确保留，不能把数据来源完整性核对通过写成“108条均评分成功”。六组trace没有 model_error 或 limit_reached；存在工具校验错误及3条评委解析重试，其中1条最终未评分。

本机原配置已按字节恢复，SHA256 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`；配置、密钥、原始live／trace／数据库不进入发布材料。发布证据是合成测试内容，文件清单见 [evidence-manifest.json](evidence-manifest.json)，复现步骤见 [reproduction.md](reproduction.md)。本轮实验和本地报告完成；下一轮应先修复已定位的受控表达遗漏，并排查评委解析缺失，再另行验证。当前结果不足以冻结或启动留出集。
