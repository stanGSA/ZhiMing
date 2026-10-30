"""Recorded failure chains replayed through the runtime (P0.4 of docs/根因整改实施计划.md).

The legacy agent must still answer each recorded call the way the live run recorded. A chain
whose system the pipeline handles (config.yaml ``pipeline.systems``) also runs through the
pipeline, with the writer drafts its ``pipeline`` section names; the others stay data until
their phase moves them.
"""

import pytest
import yaml

from app import ROOT, create_runtime
from tests.pipeline.drafts import DRAFTS, Composer
from tests.pipeline.replay import CATEGORIES, ScriptedReplay, load_all, mismatches

CASES = load_all()
PIPELINE_SYSTEMS = set(
    yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["pipeline"]["systems"]
)
MOVED = [case for case in CASES if case["systems"] and set(case["systems"]) <= PIPELINE_SYSTEMS]


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


def test_every_moved_chain_has_pipeline_drafts():
    assert MOVED, "the tarot pilot must replay its chains through the pipeline"
    for case in MOVED:
        assert set(case["pipeline"]["drafts"]) <= set(DRAFTS), case["id"]


@pytest.mark.parametrize("case", MOVED, ids=[case["id"] for case in MOVED])
async def test_pipeline_answers_the_recorded_chain(project, case):
    expected = case["pipeline"]
    composer = Composer(*(DRAFTS[name] for name in expected["drafts"]))
    runtime = create_runtime(
        root=project, user_id="replay", seed=42, model=composer, mode="pipeline"
    )
    events = []
    runtime.tracer.listeners.append(events.append)
    try:
        for message in case["turns"]:
            before = len(events)
            outcome = await runtime.turn(message)
            calls = [e for e in events[before:] if e["event"] == "model_response"]
            assert len(calls) <= expected["max_model_calls_per_turn"], message
        assert outcome.status == expected["outcome"]
        info = outcome.data["pipeline"]
        assert info["repairs"] == expected["repairs"]
        assert info["degraded"] == expected["degraded"]
        # The final facts are the draw's own: every card as drawn, every reference citable.
        state = runtime.session.state
        for card in state["tarot_result"]["cards"]:
            side = "逆位" if card["reversed"] else "正位"
            assert f"【{card['name']}】{side}" in outcome.text
        evidence = {e["ref_id"] for e in outcome.data["reading"]["evidence"]}
        assert evidence <= state["allowed_refs"]
        assert runtime.store.unfinished_pipeline_run("replay") is None
    finally:
        runtime.close()
