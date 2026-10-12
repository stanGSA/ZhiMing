import json
import subprocess
import sys

import pytest

from knowledge.kb import KnowledgeBase
from plugins.tarot.catalogue import DECK, SPREADS
from plugins.tarot.draw import draw_tarot
from plugins.tarot.tools import TarotPlugin


def test_complete_deck():
    assert len(DECK) == 78
    assert len({card[0] for card in DECK}) == 78
    assert len({card[1] for card in DECK}) == 78


@pytest.mark.parametrize("spread,count", [("single", 1), ("three_card", 3), ("decision", 3)])
def test_reproducible_draw_without_replacement(spread, count):
    expected = draw_tarot(spread, "合成问题", 42)
    assert all(draw_tarot(spread, "合成问题", 42) == expected for _ in range(100))
    assert len(expected["cards"]) == count
    assert len({card["card_id"] for card in expected["cards"]}) == count


def test_cross_process_reproducibility():
    program = "import json; from plugins.tarot.draw import draw_tarot; print(json.dumps(draw_tarot('three_card','q',42)))"
    result = subprocess.check_output([sys.executable, "-c", program], text=True)
    assert json.loads(result) == draw_tarot("three_card", "q", 42)


def test_seed_changes_and_both_orientations():
    results = [draw_tarot("three_card", "q", seed) for seed in range(100)]
    assert len({json.dumps(r["cards"], sort_keys=True) for r in results}) > 95
    assert {c["reversed"] for r in results for c in r["cards"]} == {True, False}


@pytest.mark.parametrize("spread,seed", [("unknown", 0), ("single", -1), ("single", 2**64)])
def test_invalid_inputs(spread, seed):
    with pytest.raises(ValueError):
        draw_tarot(spread, "q", seed)


def test_every_possible_card_state_and_position_has_meaning(project):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        for card_id, _ in DECK:
            for orientation in ("upright", "reversed"):
                assert kb.lookup("tarot", "card", f"{card_id}:{orientation}")
        for spread, positions in SPREADS.items():
            for i in range(len(positions)):
                assert kb.lookup("tarot", "position", f"{spread}:{i + 1}")
    finally:
        kb.close()


def test_signals_come_from_kb_and_are_immutable(runtime):
    runtime.session.start_reading("q")
    result = draw_tarot("three_card", "q", 42)
    result["reading_id"] = runtime.session.state["active_reading_id"]
    signals = TarotPlugin(runtime.kb).extract_signals([result])
    assert signals
    assert {s.horizon for s in signals} == {"moment"}
    assert all(s.kb_ref.endswith(runtime.kb.version) for s in signals)
    assert all(s.reviewed is False for s in signals)
    with pytest.raises(ValueError):
        signals[0].valence = 1
