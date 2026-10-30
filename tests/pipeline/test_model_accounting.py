"""Budget and saved call counts at PR #35's remaining review boundaries."""

import asyncio

import pytest

from common.policy_judge import PolicyJudge
from harness.models import ModelResponse
from tests.pipeline.drafts import QUESTION, followup_answer, good
from tests.pipeline.test_runner_tarot import make as make

SAFE = '{"certainty":false,"discourage_care":false}'


def candidate(messages):
    return good(messages).replace("先理顺：", "不一定会失败，先理顺：")


def two_candidates(messages):
    return candidate(messages).replace("再推进：", "不一定能马上解决，再推进：")


def policy(runtime, composer):
    runtime.session.policy_judge = PolicyJudge(composer, runtime.tracer)


def saved_record(runtime, outcome):
    user = runtime.session.user_id
    if response_id := outcome.data.get("response_id"):
        record = runtime.store.get_response(user, response_id)
    else:
        record = runtime.store.get_reading(user, outcome.data["reading_id"])
    assert record["pipeline_json"] == outcome.data["pipeline"]
    return record["pipeline_json"]


async def test_overdrawn_response_is_counted_in_saved_and_exported_record(make):
    def expensive(messages):
        return ModelResponse(text=good(messages), input_tokens=10000, output_tokens=1)

    runtime, composer, _ = make(expensive)
    runtime.token_budget = 10000
    outcome = await runtime.turn(QUESTION)
    record = saved_record(runtime, outcome)
    assert record["model_calls"] == len(composer.seen) == 1
    assert record["degraded"] == "keywords"
    assert runtime.session.budget.used == 10001
    (exported,) = runtime.store.export_user(runtime.session.user_id)["readings"]
    assert exported["pipeline"] == record


@pytest.mark.parametrize("new_session", [False, True])
async def test_unmetered_response_is_kept_in_count_when_resumed(make, new_session):
    def unmetered(messages):
        return ModelResponse(text=good(messages), usage_available=False)

    runtime, _, _ = make(unmetered, good)
    assert (await runtime.turn(QUESTION)).status == "usage_unavailable"
    run = runtime.store.unfinished_pipeline_run(runtime.session.user_id)
    assert run["state"]["model_calls"] == 1
    later = make(good)[0] if new_session else runtime
    outcome = await later.turn("继续")
    assert saved_record(later, outcome)["model_calls"] == 2


async def test_semantic_judge_uses_current_budget_and_is_saved_in_call_count(make):
    judgment = ModelResponse(text=SAFE, input_tokens=20, output_tokens=5)
    runtime, composer, events = make(candidate, judgment, followup_answer)
    policy(runtime, composer)
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    assert saved_record(runtime, outcome)["model_calls"] == 2
    assert runtime.session.turn_budget is runtime.session.budget
    assert runtime.session.budget.used == runtime.session.total_tokens == 205
    assert runtime.session.budget.model_calls == len(composer.seen) == 2
    assert "pipeline_run" not in runtime.session.state
    # The observer is scoped to one write, including later responses on the same session.
    assert len(runtime.tracer.listeners) == 1
    second = await runtime.turn("第二张牌具体什么意思？不要重新抽牌。")
    assert saved_record(runtime, second)["model_calls"] == 1
    assert len(runtime.tracer.listeners) == 1
    assert [e["purpose"] for e in events if e["event"] == "model_response"] == [
        "compose",
        "policy_judge",
        "compose",
    ]


async def test_semantic_judge_cannot_submit_overdrawn_response(make):
    judgment = ModelResponse(text=SAFE, input_tokens=20000, output_tokens=5)
    runtime, composer, _ = make(candidate, judgment)
    runtime.token_budget = 10000
    policy(runtime, composer)
    outcome = await runtime.turn(QUESTION)
    record = saved_record(runtime, outcome)
    assert record["degraded"] == "keywords"
    assert record["model_calls"] == len(composer.seen) == 2
    assert runtime.session.budget.used == runtime.session.total_tokens == 20185
    assert "不一定会失败" not in outcome.text


async def test_semantic_checks_and_repair_share_two_dispatches(make):
    runtime, composer, events = make(two_candidates, ModelResponse(text=SAFE))
    policy(runtime, composer)
    outcome = await runtime.turn(QUESTION)
    record = saved_record(runtime, outcome)
    assert record["degraded"] == "keywords"
    assert record["model_calls"] == len(composer.seen) == 2
    assert runtime.session.budget.held == 0
    assert any(e["event"] == "model_call_limit" for e in events)


async def test_semantic_judge_is_denied_when_writer_used_remaining_tokens(make):
    def nearly_exhausted(messages):
        return ModelResponse(text=candidate(messages), input_tokens=9999, output_tokens=1)

    runtime, composer, _ = make(nearly_exhausted)
    runtime.token_budget = 10000
    policy(runtime, composer)
    outcome = await runtime.turn(QUESTION)
    assert saved_record(runtime, outcome)["degraded"] == "keywords"
    assert len(composer.seen) == 1
    assert runtime.session.budget.used == 10000


async def test_pipeline_replaces_previous_agent_budget(make):
    reply = ModelResponse(text="日主是八字中的日干。", input_tokens=10, output_tokens=5)
    runtime, composer, _ = make(reply, candidate, ModelResponse(text=SAFE, input_tokens=20))
    policy(runtime, composer)
    assert (await runtime.turn("请用八字解释日主是什么意思？")).status == "text"
    previous = runtime.session.turn_budget
    previous.used = previous.tokens  # The previous request has no admissible budget left.
    outcome = await runtime.turn(QUESTION)
    assert outcome.status == "submit_reading"
    assert saved_record(runtime, outcome)["degraded"] is None
    assert runtime.session.turn_budget is runtime.session.budget
    assert runtime.session.turn_budget is not previous
    assert runtime.session.budget.used == 200
    assert previous.used == previous.tokens


async def test_cancellation_preserves_returned_draft_count_and_removes_observer(make):
    def cancelled(messages):
        raise asyncio.CancelledError()

    runtime, composer, _ = make("没有格式。", cancelled, good)
    with pytest.raises(asyncio.CancelledError):
        await runtime.turn(QUESTION)
    run = runtime.store.unfinished_pipeline_run(runtime.session.user_id)
    assert run["state"]["model_calls"] == 1
    assert len(runtime.tracer.listeners) == 1
    outcome = await runtime.turn("继续")
    assert saved_record(runtime, outcome)["model_calls"] == 2
