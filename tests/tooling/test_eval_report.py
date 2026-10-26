import json

import app
from evals.report import generate


async def test_summary_generated_offline_with_key_fields(tmp_path, monkeypatch):
    def no_paid_model(*args, **kwargs):
        raise AssertionError("evals.report must never build a real model client")

    monkeypatch.setattr(app, "OpenAIModel", no_paid_model)
    monkeypatch.setattr(app, "AnthropicModel", no_paid_model)
    await generate(tmp_path / "eval")
    summary = json.loads((tmp_path / "eval/summary.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "eval/summary.md").read_text(encoding="utf-8")

    assert summary["schema_version"] == 1
    assert summary["offline"] is True and summary["paid_model_calls"] == 0
    datasets = summary["datasets"]
    assert datasets["trajectory"]["status"] == "draft_needs_review"
    assert datasets["trajectory"]["draft"] and datasets["safety"]["draft"]
    assert not datasets["reference_charts"]["draft"]
    assert datasets["name_strokes"]["item_status"] == {"auto_ok": 181, "needs_review": 19}

    for mode in ("single", "multi"):
        tools = summary["tool_selection"][mode]
        assert tools["dataset_cases"] == 80 and tools["cases"] > 0
        assert 0 <= tools["tool_f1"] <= 1
    assert summary["tool_selection"]["single"]["specialist_f1"] is None
    assert 0 <= summary["tool_selection"]["multi"]["specialist_f1"] <= 1

    facts = summary["facts"]
    assert facts["reference_charts"]["passed"] == facts["reference_charts"]["cases"] == 11
    assert facts["bazi_boundary"]["passed"] == 50 and facts["bazi_boundary"]["variants"] == 57
    assert facts["name_strokes"]["correct"] == facts["name_strokes"]["items"] == 200
    assert facts["daily_consistency"]["identical"] and facts["daily_consistency"]["seed_identical"]

    assert summary["safety"]["crisis"]["passed"] == summary["safety"]["crisis"]["cases"] == 5
    assert summary["safety"]["high_risk"]["cases"] == 25
    assert summary["reviewer"]["cases"] == 45
    assert summary["reviewer"]["miss_rate"] is not None
    assert summary["reviewer"]["over_intervention_rate"] is not None
    for name in ("single_turn", "multi_turn", "reviewer"):
        timing = summary["latency"][name]
        assert timing["n"] > 0 and 0 < timing["p50_ms"] <= timing["p95_ms"]

    runs = {run["run"]: run for run in summary["real_model"]}
    final = runs["codego-v4/Final-single"]
    assert final["model"] == "deepseek-v4-flash" and final["judge"] == "deepseek-v4-pro"
    assert final["date"] == "2026-10-25" and final["rubric_version"] == "v2-2026-10-24"
    assert final["task_success"] == 37 and final["cases"] == 60
    assert all(run["model"] and run["date"] and run["rubric_version"] for run in runs.values())

    assert "## 真实模型（只读归档摘要）" in markdown
    assert "（草稿）" in markdown and "草稿，待审核" in markdown
    assert "codego-v4/Final-single" in markdown
