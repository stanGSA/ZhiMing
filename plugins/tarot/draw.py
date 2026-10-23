from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from plugins.tarot.catalogue import DECK, SPREADS


def valid_picks(picks: Sequence[int], spread: str) -> bool:
    """One distinct deck position (0-77) per position of the spread."""
    return (
        len(picks) == len(SPREADS[spread])
        and len(set(picks)) == len(picks)
        and all(type(p) is int and 0 <= p < len(DECK) for p in picks)
    )


def draw_tarot(spread: str, question: str, seed: int, picks: Sequence[int] | None = None) -> dict:
    """Pure, versioned hash ranking; independent of Python random/hash implementation.

    The seed orders the whole deck face down. Without picks the top cards are dealt; with
    picks, the cards at the positions the person chose from that face-down deck, in order.
    """
    if spread not in SPREADS:
        raise ValueError("Unsupported spread")
    if not 0 <= seed < 2**64:
        raise ValueError("Seed out of range")
    if picks is not None and not valid_picks(picks, spread):
        raise ValueError("Picks must be distinct deck positions, one per spread position")

    def digest(card_id: str, tag: str) -> bytes:
        payload = json.dumps(["tarot-sha256-v1", seed, tag, card_id], separators=(",", ":"))
        return hashlib.sha256(payload.encode()).digest()

    order = sorted(DECK, key=lambda c: digest(c[0], "order"))
    chosen = order[: len(SPREADS[spread])] if picks is None else [order[p] for p in picks]
    return {
        "spread": spread,
        "question": question,
        "seed": seed,
        "algorithm": "tarot-sha256-v1",
        **({} if picks is None else {"picks": list(picks)}),
        "cards": [
            {
                "pos": i + 1,
                "label": SPREADS[spread][i],
                "card_id": card_id,
                "name": name,
                "reversed": bool(digest(card_id, "orientation")[0] & 1),
            }
            for i, (card_id, name) in enumerate(chosen)
        ],
    }
