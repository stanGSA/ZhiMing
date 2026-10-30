"""execute_calls runs planned calls without a model (P0.5 of docs/根因整改实施计划.md).

The pipeline's planner issues the calculation calls itself. They must take the same path as a
model's calls: the Guard first, then commit, cache, exclusivity, model-visible projection and
trace, with the message protocol kept complete.
"""

import json

from harness.loop import execute_calls
from harness.models import ModelResponse, ToolCall

QUESTION = "只用塔罗，抽三张牌帮我看看近期事业状态。"


def planned(*calls):
    return ModelResponse(
        planned=True,
        tool_calls=[
            ToolCall(id=f"plan-{i}", name=name, arguments=args)
            for i, (name, args) in enumerate(calls)
        ],
    )


async def run(runtime, response, failed_attempts=None):
    runtime.session.messages.append(response.assistant_message())
    return await execute_calls(
        runtime.session,
        runtime.registry,
        runtime.tracer,
        response.tool_calls,
        failed_attempts=failed_attempts,
    )


def tool_messages(session):
    return [json.loads(m["content"]) for m in session.messages if m["role"] == "tool"]


async def test_planned_calls_commit_like_model_calls(runtime):
    session = runtime.session
    session.append_user(QUESTION)
    terminal = await run(
        runtime,
        planned(
            ("start_reading", dict(question=QUESTION, systems=["tarot"])),
            ("draw_tarot", dict(spread="three_card", question=QUESTION)),
        ),
    )
    assert terminal is None
    started, drawn = tool_messages(session)
    assert started["ok"] and drawn["ok"]
    assert len(session.state["tarot_result"]["cards"]) == 3
    assert session.state["tarot_drawn"]  # exclusive_key committed
    # The model-visible copy uses the session's R-numbers, never full identifiers.
    assert all(card["ref_id"].startswith("R") for card in drawn["data"]["cards"])


async def test_the_guard_still_decides_planned_calls(runtime):
    session = runtime.session
    session.append_user(QUESTION)
    await run(
        runtime,
        planned(
            ("start_reading", dict(question=QUESTION, systems=["tarot"])),
            ("draw_tarot", dict(spread="three_card", question=QUESTION)),
        ),
    )
    cards = session.state["tarot_result"]["cards"]
    # A second draw for the same reading is refused, and the first draw stands.
    assert (
        await run(runtime, planned(("draw_tarot", dict(spread="single", question=QUESTION))))
        is None
    )
    refused = tool_messages(session)[-1]
    assert not refused["ok"]
    assert session.state["tarot_result"]["cards"] == cards


async def test_repeated_failures_are_counted_across_calls(runtime):
    runtime.session.append_user(QUESTION)
    failed: dict[tuple, int] = {}
    # No reading was started, so the Guard refuses the same call each time.
    bad = planned(("compute_bazi", dict(birth_local="1993-08-17 23:20", location_id="nowhere")))
    outcomes = [await run(runtime, bad, failed) for _ in range(3)]
    assert outcomes[:2] == [None, None]
    assert outcomes[2].status == "retry_limit"
