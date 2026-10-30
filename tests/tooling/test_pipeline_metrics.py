from harness.models import TurnOutcome
from scripts.failure_taxonomy import summarize
from scripts.live_test import pipeline_record


def row(status="submit_reading", errors=(), pipeline=None):
    return dict(
        id="q",
        status=status,
        checks={"expected_status": status == "submit_reading", "zero_tool_errors": not errors},
        tool_errors=list(errors),
        latency_s=1.0,
        pipeline=pipeline,
    )


def test_a_clean_pass_needs_no_tool_error_repair_or_degrading():
    rows = [
        row(),  # the agent loop, no tool error
        row(pipeline={"repairs": 0, "degraded": None}),
        row(pipeline={"repairs": 1, "degraded": None}),
        row(pipeline={"repairs": 1, "degraded": "keywords"}),
        row(errors=[{"tool": "draw_tarot", "code": "x", "error": "y"}]),
        row(status="model_error", pipeline={"repairs": 0, "degraded": None}),
    ]
    s = summarize({"results": rows})
    assert (s["repaired"], s["degraded"]) == (2, 1)
    assert s["first_try_clean"] == 5 and s["clean_success"] == 2


def test_the_report_keeps_the_record_without_the_drafts_problem_texts():
    outcome = TurnOutcome(
        status="submit_reading",
        text="",
        data={
            "pipeline": {
                "run_id": "r",
                "kind": "new",
                "model_calls": 2,
                "repairs": 1,
                "degraded": None,
                "problems": [["牌位不符", "格式"]],
            }
        },
    )
    assert pipeline_record(outcome) == {
        "kind": "new",
        "model_calls": 2,
        "repairs": 1,
        "degraded": None,
        "problems": [2],
    }
    assert pipeline_record(TurnOutcome(status="text", text="")) is None
