from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    user_id: str
    role: str = "orchestrator"
    partition: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    parent_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)
    total_tokens: int = 0
    user_messages: list[str] = field(default_factory=list)
    default_seed: int | None = None

    def append_user(self, text: str) -> None:
        self.user_messages.append(text)
        self.messages.append({"role": "user", "content": text})
        self.state["asked_this_turn"] = False

    def start_reading(self, question: str) -> str:
        previous = self.state.get("active_reading_id")
        # Fixture injection controls only the first draw, never later redraws.
        seed = self.default_seed if self.default_seed is not None else secrets.randbits(64)
        self.default_seed = None
        while seed == self.state.get("seed"):
            seed = secrets.randbits(64)
        self.cache.clear()
        self.state = {
            "active_reading_id": uuid.uuid4().hex,
            "parent_reading_id": previous,
            "question": question,
            "seed": seed,
            "signals": [],
            "facts": [],
            "allowed_refs": set(),
            "kb_refs": set(),
            "asked_this_turn": self.state.get("asked_this_turn", False),
            "complete": False,
        }
        return self.state["active_reading_id"]
