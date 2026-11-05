# P2 r7 实验评估：未通过 B，不冻结

2026-11-05 18:53–19:41（Asia/Shanghai），按负责人截图执行六组串行调参实验，共108条，全部完成并有四维评分。被测提交 `da447c41bbff650bb953c260157357de99872f6c`，实验配置沿用r6，SHA256 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。负责人批准否定“稳赚”放行，并保留现有“奔跑→被追”绑定范围；执行前决定和验证见 [decisions.md](decisions.md)。

| 体系 | single 提交/质量通过 | pipeline 提交/质量通过 | pipeline 最多模型调用 | 步数/预算失败 | pipeline 修复/降级 |
| --- | --- | --- | ---: | ---: | ---: |
| 解梦 | 12/18；11/12 | 18/18；18/18 | 3 | 0 | 8/2 |
| 姓名 | 12/18；12/12 | 18/18；18/18 | 2 | 0 | 0/0 |
| 每日运势 | 18/18；12/18 | 18/18；11/18 | 2 | 0 | 3/3 |

质量通过率的分母为已提交回答。解梦single另有4条retry_limit、1条text、1条ask_user；姓名single另有5条ask_user、1条retry_limit。合理追问的质量通过也不能当作已提交解读。每日single虽提交18条，工程任务完成为16/18，不能混用两个口径。每日pipeline的3条投资回答最终保存成功，但原稿与修复稿被拒，工程通过只有15/18。完整指标见 [comparison.md](comparison.md) 与 [integrity.json](integrity.json)。

**B不通过，不冻结，不运行p2-final。** 三个pipeline的提交率100%、调用≤3、步数/预算失败0均满足，但仍存在两类可定位误拒：

- 医疗正反疑问：“那要不要去做检查”被读成“不要去做检查”。解梦同一回答两稿均误拒，最终safety降级；最终模板质量通过不能消除前两稿缺陷。
- 否定“稳赚”的覆盖不足：批准的原句“别把配合当稳赚”已放行，但“一时的配合顺畅”“顺手”等宾语变体，以及“别把‘配合顺’误解为‘稳赚’”仍拒。三个投资回答各修复一次后safety降级。此次共用规则实现尚未完整覆盖负责人批准的语义。

10份解梦拒绝稿逐份重现原问题，6份每日拒绝稿重现共用安全命中，另有10个最小检查，均为离线回放、0模型调用。根因见 [validation-findings.md](validation-findings.md)，全部20条质量失败、11次修复、5次降级归因见 [quality-attribution.md](quality-attribution.md)，原文见 [pipeline-problems-raw.md](pipeline-problems-raw.md) 和 [quality-reasons-with-answers.md](quality-reasons-with-answers.md)。本轮运行中没有修改产品代码、替换样本或补跑。

保留原评分的编造分类为：Dream-single叙述1，Daily-single叙述3，Daily-pipeline事实2、叙述1，其余为0；六组均已覆盖全部原始失败key，没有待分类或未评分条目。这是助手复核，**不是独立人工校准**。两条Daily-pipeline事实类指控均有明确异议：一条把本命盘内相位与行运相位混同，实际行运值与原文一致；另一条将程序固定生成的证据计数、网页和`/evidence`说明当作模型编造。事实类计数2不代表已确认两条编造；在不改原分的保守计数下，审计的 `pipeline_fact_fabrication_zero=false`，不能宣布该数值门槛通过。即使移除争议指控，两类已复现校验缺陷仍独立阻止冻结。分类理由及漏判见 [fabrication-review-notes.md](fabrication-review-notes.md)，日期、相位、引用摘录见 [fact-review.json](fact-review.json)。

同批质量比较：解梦pipeline为100%高于single的91.7%；姓名同为100%；每日pipeline为61.1%，低于single的66.7%。按事先约定，调参集的质量比较照常报告，不单独阻止冻结，最终验收时仍须逐体系判定。配对胜/负/平（pipeline相对single，按任务完成且质量通过）依次为7/0/11、6/0/12、1/2/15；同题三次不是独立样本，仅作描述。

相较r6，pipeline质量由解梦17/18→18/18、姓名18/18→18/18、每日15/18→11/18；修复由5/1/1→8/0/3，降级由2/0/0→2/0/3（顺序为解梦/姓名/每日）。姓名本轮未观察到修复，解梦仍有闭集表达成本；每日新增否定变体误拒并受评委不一致影响。跨日计算事实、每日卡牌与模型采样不同，这些描述不能直接归因成PR的净因果效果。

运行与pro评委请求、返回均为 `deepseek-v4.1-flash`，同模型评分；没有独立评审。每日存在时区误读、原理由与布尔值冲突及不同模板评分不一致，也有本命/流月混淆等漏判，均保留原分并另记异议。中转费率未核实，费用未知，见 [pricing.yaml](pricing.yaml)。

完整性审计通过：108个唯一题目/重复编号，每题0/1/2，single/pipeline成对覆盖，六组源码哈希相同且与被测文件一致，所有原始live哈希与发布清单一致，108条均有完整评分。源码指纹 `362d6a8edd2bb86b33368193041674a54d34c35b94c6616a63cfa22822e29eaf`。各组trace无model_error或limit_reached事件；有校验失败和评委解析重试，不能说全部请求一次成功。完整性通过不等于B通过。

原本机配置已按字节恢复，未提交。原始live、trace和数据库保留本机忽略目录；发布材料为合成测试证据，不含配置或密钥。执行步骤见 [reproduction.md](reproduction.md)，执行元数据见 [execution.json](execution.json)，文件哈希见 [evidence-manifest.json](evidence-manifest.json)。
