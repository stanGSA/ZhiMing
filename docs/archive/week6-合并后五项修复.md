# 第六周：PR #5 合并后五项修复

日期：2026-10-14（Asia/Shanghai）。基线为 PR #5 合并提交 `7b8e3c2`，修复分支 `codex/week6-followup-fixes`。

本次修复复审中仍未闭环的五个问题，未改变计算数据、知识库或模型配置。所有验证均使用合成用户资料与离线确定性工具。

## 修复内容

| 问题 | 实现 | 验证重点 |
|---|---|---|
| 无效日期更正后仍被旧消息阻断 | `requested_date`保存咨询目标、待确认错误及已处理消息位置；后续明确更正替代旧错误；同一句中较后的更正也生效 | `2026-02-30`被拒后，同一reading更正为`2026-02-28`即可成功；保留错误日期时继续拒绝 |
| 附带日期词覆盖咨询目标 | 只从咨询/日期更改语境或直接日期回答取证；忽略“我今天补充资料”“不用重算，我今天只是问刚才那张牌”及否定更改 | 原目标明天保持不变，明确“改成后天”才改变 |
| 意象来源仍允许无序字符拼词 | 删除通用字符集合例外；只接受原文意象/别名或明确列出的掉牙、被追句式 | 手机飞到手里≠飞机、火烧到车旁边≠火车；掉牙、被狗追与大狗规范化保持可用 |
| 未收录说明豁免整句 | 未收录/不解读说明按分句及具体意象定位；豁免范围在下一意象前结束；保留引号短语和“的出现/这个形象”等解释主体 | “无人机未收录，但蛇象征变化”及无逗号、倒置顺序、修饰主体变体均被拒绝；正常未收录说明仍接受 |
| 歧义说明藏在不展示字段 | `public_texts`继续检查全部文本；新增`rendered_texts`只用于判断是否已向用户披露。confidence.reason、followups、resonances和未启用的safety.note不能满足必需披露 | 只放隐藏字段被拒绝；放到advice后提交成功，最终显示文本与存储后再渲染均包含说明 |
| 歧义数字没有绑定字形 | 逐一核验实际`(字形, 笔画)`，要求默认字形与计算一致并保留待确认请求；不能用无关字的数字凑齐，也不能无凭据宣称已确认 | “杰…王12画、李8画”、错误默认方案、虚假“已确认”均被拒绝 |

上表将日期问题的两个表现分别列出，对应复审报告中的五项修复点。涉及文件：

- `plugins/daily/tools.py`
- `plugins/dream/match.py`、`plugins/dream/validation.py`
- `common/facts.py`
- `plugins/name/tools.py`、`plugins/name/validation.py`
- 编排者与姓名专家提示词

姓名工具新增`confirmation_prompts`，文案由计算结果生成，例如：

> 赵杰的“杰”默认按傑12画，备选写法为杰8画，请按证件写法确认。

模型可将该文案直接放进最终advice；姓名专家放入points。最终校验仍要求说明出现在真实显示的字段中。已由用户确认的写法不再产生该待确认要求。

## 回归与验证

新增 `tests/test_week6_followup_fixes.py`，覆盖纠错恢复、来源语义、局部豁免、渲染披露及字形数字配对，同时保留正常映射和已确认写法的正例。

- 开始修复前，首批25个用例在合并基线上为18失败、7通过，证明能捕获被报告的缺陷。
- 最终新增28个用例；与原第六周42项合跑，**70/70通过**。
- 第六周离线关口通过：笔画200/200、五格8/8、同日10次一致、同seed抽牌100次一致；知识覆盖与89个种子意象覆盖通过。
- 知识库构建、doctor和Ruff检查通过。
- 全量 pytest：**416/416 通过**，耗时 387.02 秒（388 项原测试 + 28 项新增回归）。
- 80 题标注轨迹回放：**80/80 通过**，0 失败、0 跳过；这是标注路线的工具链回放，不是模型自主路由评测。
- 本次原始结果保存在本地 `reports/week6-followup-pytest.xml`、`reports/week6-followup/week6-031b23cc/` 与 `reports/week6-followup/trajectory-580fd117/`。

复现命令（先用 `python -m scripts.fetch_data` 准备星历、地理和 Unihan 数据）：

```powershell
python -m knowledge.build
python -m scripts.doctor
python -m pytest -q
python -m evals.run --suite week6 --output reports/week6-followup
python -m evals.run --suite trajectory --output reports/week6-followup
python -m ruff check harness agents common plugins knowledge memory signals scripts tests app.py cli.py evals
python -m ruff format --check harness agents common plugins knowledge memory signals scripts tests app.py cli.py evals
```

验证边界：本次没有运行真实模型；自然语言规则检查不等价于证明所有自由表述都正确。真实模型抽取/路由、多轮脚本、内容人工审核和字典核对仍按第六周验收报告保留为待办；向量兜底仍延期到第七周。
