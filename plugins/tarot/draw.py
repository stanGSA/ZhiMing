from __future__ import annotations

import hashlib
import json

from plugins.tarot.catalogue import DECK, SPREADS


def draw_tarot(spread: str, question: str, seed: int) -> dict:
    """Pure, versioned hash ranking; independent of Python random/hash implementation."""
    if spread not in SPREADS:
        raise ValueError("Unsupported spread")
    if not 0 <= seed < 2**64:
        raise ValueError("Seed out of range")

    def digest(card_id: str, tag: str) -> bytes:
        payload = json.dumps(["tarot-sha256-v1", seed, tag, card_id], separators=(",", ":"))
        return hashlib.sha256(payload.encode()).digest()

    chosen = sorted(DECK, key=lambda c: digest(c[0], "order"))[: len(SPREADS[spread])]
    return {
        "spread": spread,
        "question": question,
        "seed": seed,
        "algorithm": "tarot-sha256-v1",
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
