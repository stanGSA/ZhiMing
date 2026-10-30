# 测试

测试按被测模块分目录，全部离线运行：模型由 `tests/conftest.py` 的脚本化模型或 `--provider demo` 代替，不调用真实 API。

```bash
uv run pytest -q                      # 全部
uv run pytest -q tests/harness        # 只跑某个模块
```

| 目录 | 覆盖 |
| --- | --- |
| `harness/` | agent 循环、Guard、预算与截止时间、OpenAI/Anthropic/DeepSeek 适配器 |
| `agents/` | 多 Agent 编排、专家隔离与重试、状态恢复、跨体系合并与审校 |
| `runtime/` | 端到端运行时：抽牌与追问、安全与危机、日历与时区、输入来源校验、澄清、地名 |
| `validation/` | 回答校验：表达层修正、分层正文的事实绑定、否定与日期 |
| `plugins/` | 塔罗、占星与八字计算和集成、姓名五格、解梦、每日运势 |
| `knowledge/` | 知识库构建、审核三态与账本、模型交叉审核、校准与活动验收 |
| `web/` | 网页 API、账号与云端记录、足迹管理与导出、统一错误回复与隐私说明、朋友体验分享、浏览器回归（Playwright，仅 Linux CI 运行） |
| `mcp_server/` | MCP server：用 SDK 的内存客户端调用全部工具，比对参考盘、八字边界与固定 seed 抽牌，结构化报错，另有一次 stdio 启动；需要 `--extra mcp`，未安装时跳过 |
| `pipeline/` | 根因整改的失败回放：`replays/*.yaml` 每份是一条真实失败链（用户原话、模型调用、当时的结果），旧 agent 与各阶段流水线都用同一批回放验证 |
| `tooling/` | `scripts/` 下的诊断、数据下载和对照工具，`evals.report` 评测总表 |

`tests/plugins/test_astro_bazi_calculations.py` 中的 Skyfield 独立核验以及 `tests/tooling/test_scripts.py` 的 doctor 检查需要 `data/ephe/de440s.bsp`，请先运行 `python -m scripts.fetch_data`。

## 旧文件名对照

2026-10-23 之前测试按开发周次和 PR 命名，历史文档里引用的是旧名称：

| 旧文件 | 新文件 |
| --- | --- |
| `test_harness.py` | `harness/test_loop_and_guard.py` |
| `test_adapters.py` | `harness/test_llm_adapters.py` |
| `test_deepseek.py` | `harness/test_deepseek_adapter.py` |
| `test_multi_agent.py` | `agents/test_multi_agent.py` |
| `test_multi_agent_review.py` | `agents/test_multi_agent_retries_and_deadlines.py` |
| `test_week4_state_recovery.py` | `agents/test_specialist_state_recovery.py` |
| `test_week5.py` | `agents/test_merge_and_reviewer.py` |
| `test_week5_boundaries.py` | `agents/test_merge_and_reviewer_boundaries.py` |
| `test_runtime.py` | `runtime/test_runtime.py` |
| `test_review_fixes.py` | `runtime/test_draws_safety_and_followups.py` |
| `test_stage0.py` | `runtime/test_calendar_identity_and_crisis.py` |
| `test_pr1_remediation.py` | `runtime/test_input_contracts.py` |
| `test_v2_followup.py` | `runtime/test_clarification.py` |
| `test_regions.py` | `runtime/test_regions.py` |
| `test_expression_policy.py` | `validation/test_expression_policy.py` |
| `test_pr7_review_fixes.py` | `validation/test_layered_fact_binding.py` |
| `test_pr7_followup_fixes.py` | `validation/test_fact_binding_in_prose.py` |
| `test_pr8_review_fixes.py` | `validation/test_negation_and_dates.py` |
| `test_tarot.py` | `plugins/test_tarot.py` |
| `test_week23_calculations.py` | `plugins/test_astro_bazi_calculations.py` |
| `test_week23_integration.py` | `plugins/test_astro_bazi_integration.py` |
| `test_week6.py` | `plugins/test_name_dream_daily.py` |
| `test_week6_review.py` | `plugins/test_name_dream_daily_accept_paths.py` |
| `test_week6_followup_fixes.py` | `plugins/test_name_dream_daily_disclosures.py` |
| `test_kb.py` | `knowledge/test_kb_build.py` |
| `test_stage1_b1.py` | `knowledge/test_relationship_finance_directions.py` |
| `test_stage1_review.py` | `knowledge/test_review_levels_and_ledger.py` |
| `test_model_review_kb.py` | `knowledge/test_model_review.py` |
| `test_kb_review_campaign.py` | `knowledge/test_review_campaign.py` |
| `test_kb_review_r2.py` | `knowledge/test_review_calibration.py` |
| `test_kb_review_role_options.py` | `knowledge/test_review_role_options.py` |
| `test_pr15_review_fixes.py` | `knowledge/test_review_revocation.py` |
| `test_stage1_live_review.py` | `knowledge/test_live_review_regressions.py` |
| `test_web.py` | `web/test_web_api.py` |
| `test_web_browser.py` | `web/test_web_browser.py` |
| `test_web_share.py` | `web/test_web_share.py` |
| `test_scripts.py` | `tooling/test_scripts.py` |
