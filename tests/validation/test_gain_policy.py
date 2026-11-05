"""The P2 r7 owner decision allows governing denials of 稳赚 across policy paths."""

import copy

import pytest

from common.output_policy import hard_claim
from common.policy_judge import PolicyJudge
from common.schemas import Reading
from common.validation import validate_reading
from harness.trace import Tracer
from pipeline.verify import safety_rules


@pytest.mark.parametrize(
    "text",
    [
        "有联结也有牵绊，别把配合当稳赚。",
        "别当稳赚。",
        "不要将投资看作稳赚。",
        "这不是稳赚。",
        "这笔投资不稳赚。",
        "不能保证这笔投资稳赚。",
        "别以为这笔投资稳赚。",
        "这不代表收益稳赚。",
    ],
)
def test_a_governing_gain_denial_is_allowed_and_not_counted_as_unsafe(text):
    assert hard_claim([text]) is None
    assert safety_rules([text], "股票投资") == []


@pytest.mark.parametrize(
    "text",
    [
        "这笔投资稳赚。",
        "别把配合当稳赚，但这笔投资稳赚。",
        "这不是坏事，这笔投资稳赚。",
        "别担心，这笔投资稳赚。",
        "这笔投资无疑稳赚。",
        "不得不把配合当稳赚。",
        "不能不把配合当稳赚。",
        "不是不稳赚。",
        "别把配合当机会这笔投资稳赚。",
        "不是稳赚而是稳赚。",
        "这笔投资必涨。",
        "这笔投资不必涨。",
        "你不会必死。",
        "不会必然确诊。",
    ],
)
def test_affirmations_unrelated_negations_and_other_hard_words_stay_refused(text):
    assert hard_claim([text])
    assert "hard_claim" in safety_rules([text], "股票投资")


def test_a_denial_in_one_field_does_not_cover_another_field():
    texts = ["别当稳赚。", "这笔投资稳赚。"]
    assert hard_claim(texts) == "稳赚"
    assert "hard_claim" in safety_rules(texts, "股票投资")


@pytest.mark.parametrize("judge", [False, True])
@pytest.mark.parametrize("field", ["summary", "closing", "section"])
@pytest.mark.parametrize("affirmative", [False, True])
async def test_single_reading_policy_paths_agree_on_gain_claims(runtime, judge, field, affirmative):
    outcome = await runtime.turn("用塔罗看看最近心情")
    draft = copy.deepcopy(outcome.data["reading"])
    claim = "这笔投资稳赚。" if affirmative else "别把配合当稳赚。"
    if field == "section":
        draft["sections"] = [{"title": "审慎考虑", "body": claim, "ref_ids": []}]
    else:
        draft[field] = claim
    draft["safety"] = {"flag": True, "note": "涉及投资请谨慎考虑。"}
    runtime.session.state["question"] = "股票投资"
    if judge:
        runtime.session.policy_judge = object()
    error = validate_reading(Reading.model_validate(draft), runtime.session)
    assert bool(error) is affirmative, error


@pytest.mark.parametrize("affirmative", [False, True])
async def test_semantic_judge_uses_the_same_hard_policy_without_a_model_call(
    runtime, tmp_path, affirmative
):
    class UnusedModel:
        async def chat(self, *args):
            raise AssertionError("The shared hard policy decides these two cases locally")

    judge = PolicyJudge(UnusedModel(), Tracer(tmp_path))
    text = "这笔投资稳赚。" if affirmative else "别把配合当稳赚。"
    result = await judge.check([text], runtime.session)
    assert (result is not None) is affirmative
