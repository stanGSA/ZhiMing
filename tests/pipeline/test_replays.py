"""Recorded failure chains replayed through the runtime (P0.4 of docs/根因整改实施计划.md).

The legacy agent must still answer each recorded call the way the live run recorded. The
``pipeline`` sections are data until P1 routes a system through the pipeline; from then on its
tests run the same files through it.
"""

import pytest

from tests.pipeline.replay import CATEGORIES, ScriptedReplay, load_all, mismatches

CASES = load_all()


def test_replays_cover_the_main_failure_categories():
    assert len(CASES) >= 8
    assert {"B", "C", "D", "E", "Z"} <= {case["category"][0] for case in CASES} <= set(CATEGORIES)
    # The tarot pilot (P1) needs its own chains.
    assert sum(case["systems"] == ["tarot"] for case in CASES) >= 2
    for case in CASES:
        # The plan's limit: intent, compose and at most one repair per user message.
        assert case["pipeline"]["max_model_calls_per_turn"] <= 3, case["id"]
        assert case["pipeline"]["outcome"] in ("submit_reading", "ask_user"), case["id"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_legacy_agent_answers_the_recorded_calls(runtime, case):
    model = ScriptedReplay(case["legacy"]["steps"], runtime.session)
    runtime.model = model
    outcome = None
    for message in case["turns"]:
        outcome = await runtime.turn(message)
    assert mismatches(model, runtime.session) == []
    assert outcome.status == case["legacy"]["outcome"]
