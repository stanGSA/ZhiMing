from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Budget:
    """Token and wall-clock budget shared by a turn and any child sessions it spawns.

    Charges propagate to every ancestor, so a child can never spend what its parent no
    longer has; ``reserve`` keeps part of the parent's budget for the parent itself.
    """

    tokens: int
    deadline: float | None = None
    parent: Budget | None = None
    reserve: int = 0
    used: int = 0

    def charge(self, amount: int) -> None:
        self.used += amount
        if self.parent is not None:
            self.parent.charge(amount)

    def remaining(self) -> int:
        own = self.tokens - self.used
        if self.parent is None:
            return own
        return min(own, self.parent.remaining() - self.reserve)

    def expired(self) -> bool:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return True
        return self.parent is not None and self.parent.expired()

    def child(self, tokens: int, seconds: float | None = None, reserve: int = 0) -> Budget:
        deadline = None if seconds is None else time.monotonic() + seconds
        return Budget(tokens=tokens, deadline=deadline, parent=self, reserve=reserve)
