"""Medication directives must be refused regardless of mode or semantic judging."""

import copy

import pytest

from agents.schemas import ReportInput
from agents.specialists import validate_report
from common.output_policy import medication_error
from common.policy_judge import PolicyJudge
from common.schemas import Reading
from common.validation import validate_reading
from harness.trace import Tracer
from pipeline.verify import safety_rules


@pytest.mark.parametrize(
    "text",
    [
        "你可以停药。",
        "你必须停药。",
        "建议你立即停药。",
        "你应该自行停药。",
        "可以逐步停止服药。",
        "最好停止治疗。",
        "你不用再吃药。",
        "停药就好。",
        "不必担心，但你必须停药。",
        "不要以为只是情绪问题，你应该停用药物。",
        "“必须停药”是正确的建议。",
    ],
)
def test_affirmative_medication_instructions_are_refused(text):
    assert medication_error([text])
    assert "hard_claim" in safety_rules([text], "最近心情")


@pytest.mark.parametrize(
    "text",
    [
        "不要自行停药。",
        "不能擅自停药。",
        "不应随意停止服药。",
        "不建议你停药。",
        "你不必停药。",
        "不要认为你必须停药。",
        "不要认为你可以停药。",
        "是否停药，请先咨询医生。",
        "请医生判断是否需要停药。",
        "需要遵医嘱停药。",
        "“必须停药”这种说法没有依据。",
        "“必须停药”是不可靠的建议。",
        "用户提到停药，想了解最近的心情。",
        "不建议你可以停药。",
        "根据医嘱可以停药。",
    ],
)
def test_negated_instructions_and_clinician_referrals_are_allowed(text):
    assert medication_error([text]) is None
    assert safety_rules([text], "健康问题") == []


@pytest.mark.parametrize("judge", [False, True])
async def test_legacy_checks_do_not_reject_a_negated_medication_directive(runtime, tmp_path, judge):
    outcome = await runtime.turn("用塔罗看看最近心情")
    draft = copy.deepcopy(outcome.data["reading"])
    draft["closing"] = "不建议你可以停药。"
    if judge:

        class UnusedModel:
            async def chat(self, *args):
                raise AssertionError("A negated medication directive needs no semantic judging")

        runtime.session.policy_judge = PolicyJudge(UnusedModel(), Tracer(tmp_path))
        result = await runtime.session.policy_judge.check([draft["closing"]], runtime.session)
        assert result is None
    assert validate_reading(Reading.model_validate(draft), runtime.session) is None


@pytest.mark.parametrize("judge", [False, True])
@pytest.mark.parametrize("field", ["summary", "closing", "section"])
async def test_single_readings_refuse_medication_directives_in_visible_fields(
    runtime, judge, field
):
    outcome = await runtime.turn("用塔罗看看最近心情")
    draft = copy.deepcopy(outcome.data["reading"])
    if field == "section":
        draft["sections"] = [{"title": "照顾自己", "body": "你必须停药。", "ref_ids": []}]
    else:
        draft[field] = "你必须停药。"
    if judge:
        runtime.session.policy_judge = object()
    error = validate_reading(Reading.model_validate(draft), runtime.session)
    assert error and "停药建议" in error


async def test_specialist_reports_refuse_medication_directives(runtime):
    outcome = await runtime.turn("用塔罗看看最近心情")
    runtime.session.role = "tarot"
    ref = outcome.data["reading"]["evidence"][0]["ref_id"]
    report = ReportInput(
        answer="先照顾自己的心情。",
        analysis="你必须停药。",
        points=[{"ref_id": ref, "text": "可以先放慢节奏。"}],
        confidence={"level": "low", "reason": ""},
    )
    assert "停药建议" in validate_report(report, runtime.session)


async def test_policy_judge_does_not_call_a_model_for_a_medication_directive(runtime, tmp_path):
    class UnusedModel:
        async def chat(self, *args):
            raise AssertionError("A medication directive must fail before semantic judging")

    judge = PolicyJudge(UnusedModel(), Tracer(tmp_path))
    result = await judge.check(["你必须停药。"], runtime.session)
    assert result.code == "validation_failed" and "停药建议" in result.error
