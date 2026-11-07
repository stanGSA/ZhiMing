# PR #57 合并后的离线修复

日期：2026-11-08。PR #57 已先合并到 `claude_modify_model`，合并提交为
`09e28901b6893a2a436367c59d8628709442b658`。

本次修复覆盖独立审查发现的两处新增回归，以及三处既有边界问题：

- 局部检查与最终提交校验都区分“否定位置”和“否定由位置推出的结论”。例如太阳实际在金牛座时，
  “并非本命太阳在金牛座就意味着固执”与“并不是太阳在白羊座”通过；否认实际位置和错误的双重否定仍拒绝。
- 月内分段按正文或标题中的行运星、本命星、相位及明确日期匹配计算事件，不再要求逐字包含事实表的日期、时区。
  同义相位、省略日期和未引用的手写相位也检查；纯引用列表不算正文断言。重复出现的同类相位由引用或日期消歧，
  完整事件键同时包含时间、行运星、本命星与相位。
- “我1990年3月5日生”“我是1990年的”等出生简写交回 agent 循环，不作为行运时间范围。
- 补充出生钟点时先核对同时给出的完整出生日期；与已有资料冲突，或仅重述出生年份时，交回 agent 循环。
  单纯补钟点及重复相同日期仍可继续流水线。

新增 `tests/pipeline/test_astro_pr57_regressions.py`，覆盖最终提交、修复与降级结果、分段事件身份和出生资料路由；
共享校验的三类文本字段测试也扩展了否定作用域反例。

测试使用独立 worktree 的仓库标准配置与本机星历数据，避免当前工作目录仅启用塔罗的个人配置影响星盘测试。
脚本模型与历史草稿回放均不调用外部模型。本次没有执行 r3 真实模型评测，也没有执行最终验收集；
这些离线结果不能替代新一轮质量、成本、延迟和降级率评测。

验证使用 Python 3.11，命令中的 `python` 指向本机虚拟环境：

```powershell
python -m pytest tests/pipeline/test_runner_astro.py -q --tb=short
python -m pytest tests/validation/test_fact_binding_in_prose.py tests/validation/test_layered_fact_binding.py tests/validation/test_negation_and_dates.py tests/runtime/test_input_contracts.py -q --tb=short
python -m pytest tests/pipeline/test_astro_pr57_regressions.py tests/pipeline/test_runner_astro.py::test_section_parts_of_the_month_hold_their_transits tests/pipeline/test_runner_astro.py::test_r2_degraded_drafts_are_no_longer_refused tests/pipeline/test_runner_astro.py::test_a_transit_written_in_the_wrong_part_is_still_refused -q --tb=short
```

- 原有星盘流水线：57 passed。该轮运行之后，分段匹配又补充了同类事件的引用消歧；最终版本由第三条命令复验。
- 共享事实绑定、否定、日期与输入契约：262 passed，6 xfailed。
- 最终版本的新增回归与三项分段／历史草稿复验：41 passed（38 项新增回归，3 项原有测试）。
- Ruff 检查、格式检查和 `git diff --check` 均通过。
