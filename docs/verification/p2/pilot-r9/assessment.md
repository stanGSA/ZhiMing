# P2 r9 实验评估：未通过 B，不冻结

2026-11-06 按负责人指定命令完成六组串行调参实验，共 108 条，campaign 退出码 0。被测提交 `eed36596f9ce8a58a9804fb3be69a0087acd5966`，实验配置 SHA256 为 `d69dbaec587d1c91c843a0b45842d77cc381ed082a5ca1349b42e5d8bffd6cc3`。执行期间未修改产品源码、提示词或样本，没有替换、剔除、补跑失败样本，也没有改原始评分。执行记录见 [decisions.md](decisions.md)、[reproduction.md](reproduction.md)、[execution.json](execution.json)。

**108 条全部完成并有四维评分，B 不通过，不冻结，不运行 p2-final。**

实际执行时间为 2026-11-06 02:30:21–03:14:41（Asia/Shanghai），约44分20秒。预检独立于正式108条，未计入样本。

| 体系 | single：提交／提交后质量通过 | pipeline：提交／质量通过 | pipeline 最大模型调用 | 步数/预算失败 | pipeline 修复／降级 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 解梦 | 14/18；14/14 | 18/18；18/18 | 3 | 0 | 4/0 |
| 姓名 | 12/18；9/12 | 18/18；17/18 | 2 | 0 | 1/1 |
| 每日运势 | 17/18；13/17 | 18/18；14/18 | 1 | 0 | 0/0 |

质量通过率分母是已提交回答；追问、重试上限和工具错误保留为非提交。所有正式运行与 pro 评委返回模型均为 `deepseek-v4.1-flash`，thinking 和 policy_judge 关闭；评委与运行同模型，不是独立评审。中转费率未核实，费用未知，见 [pricing.yaml](pricing.yaml)。

三个 pipeline 都满足提交率 100%、模型调用不超过 3、无步数/预算失败；全部 108 条均已评分，pipeline 的事实类编造计数为 0。配对结果（pipeline 相对 single，按任务完成且质量通过）为解梦 4 胜/0 负/14 平，姓名 8/0/10，每日 5/4/9；三次重复不是独立样本，仅作描述。

## 阻止 B 的可定位校验缺陷

- `Dream-single / dream_hospital_health#2` 三次拒绝稿都把普通短语“给自己申请”中的“己申”当成八字干支，触发“本次工具结果没有该干支”；最小对照已重现，见 [bazi-false-positive-replay.json](bazi-false-positive-replay.json)。
- `Dream-pipeline / dream_late_grandmother#1` 将事实表已由“去世的奶奶”命中“祖父母”的来源短语，复述为“去世的奶奶”时误报“去世的亲人未命中”；去掉修饰语即可放行，见 [dream-validation-replay.json](dream-validation-replay.json)。
- `Name-single / name_compound_surname#1` 与 `name_career_grid#2` 把“三才……地格三者”中的“三者”解析为地格 3；实际地格分别为 15、17，三份实际拒绝稿均重现，见 [name-false-positive-replay.json](name-false-positive-replay.json) 与 [extra-name-single-review.json](extra-name-single-review.json)。
- `Name-pipeline / name_compare_two#3` 在“两个名字：都留意外格2”中因冒号打断集体指代，误报外格无归属；去掉冒号或逐一写“张伟的外格2、李娜的外格2”即可放行，见 [name-collective-replay.json](name-collective-replay.json)。
- `Name-single / name_without_lead_in#3` 的正确算式“外格由天格加地格减人格得18”被截为“人格得18”；真实人格25、外格18，算式17+26−25=18正确。后3稿因这处误归属达到重复失败上限，见 [extra-name-single-review.json](extra-name-single-review.json)。

r8 指定的掉牙复述、否定确定性和否定“稳赚”原句在当前代码的离线回放中通过；这不抵消本轮新增的校验边界缺陷。缺陷归因仅说明可复现行为，不宣称由 PR #51 单独引入。

以上五类缺陷均有实际稿件与离线对照，完整根因和守卫见 [validation-findings.md](validation-findings.md)。全部21条原始质量失败、5次pipeline修复、1条降级的逐行归因见 [quality-attribution.md](quality-attribution.md)，共覆盖25条异常/修复记录；最终回答质量通过不抹去此前校验误拒。

与r8相比，pipeline确认质量通过数为解梦18→18、姓名18→17、每日14→14（r8另有1条未知，本轮108条均已评分）；修复由7/0/3变为4/1/0，降级由1/0/1变为0/1/0（解梦/姓名/每日）。本轮三个体系提交后质量均不低于对应single，但同题重复、模型采样、跨日计算与每日卡牌变化并存，这些差异仅作描述，不解释为PR的净因果效果。

## 评分与复核边界

姓名 single 有 2 条叙述类编造失败；每日 single 的 3 条编造失败含 1 条事实类、3 条叙述类（同一条可同时计入两类），原评分与分类分开保存。每日 pipeline 的工作题和每日题存在 UTC/Asia-Shanghai 时段解释争议，保留原评委评分并在 [fact-review.json](fact-review.json) 中列出实际边界。离线归因和分类由助手完成，不是独立人工校准；所有原始 live、trace、数据库和配置仍保留在本机忽略目录，发布材料不含配置或密钥。

分类理由与评分异议见 [fabrication-review-notes.md](fabrication-review-notes.md)；不能因评委有时区误读而忽略single确实将UTC15:00写成本地下午三点的错误，也不以调整分数宣告B通过。三个pipeline均无model_error或limit_reached事件；Name-pipeline、Daily-single、Daily-pipeline各有1条评委解析重试后成功，不宣称所有请求均一次成功。自动comparison沿用P1/Pro/Flash模板用语，本轮实际P2与模型设置以执行记录为准。

完整性审计结果见 [integrity.json](integrity.json)，发布哈希见 [evidence-manifest.json](evidence-manifest.json)。本机原配置已按字节恢复，SHA256 `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24`。本轮未执行 p2-final。
