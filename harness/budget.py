from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Budget:
    """Token and wall-clock budget shared by a turn and any child sessions it spawns.

    Admission control: before a model call its estimated cost is held at every level, so
    concurrent siblings cannot together be admitted beyond what the parent has left, and a
    child is never admitted into the parent's ``reserve``. After the response the hold is
    replaced by the real usage. The limit is therefore soft: usage above an estimate is
    recorded as an overrun, and only that excess can eat into a reserve.
    """

    tokens: int
    deadline: float | None = None
    parent: Budget | None = None
    reserve: int = 0
    used: int = 0
    held: int = 0
    max_model_calls: int | None = None
    model_calls: int = 0

    def start_model_call(self) -> bool:
        """Reserve one dispatch at every level, including optional semantic checks."""
        budget = self
        while budget is not None:
            if budget.max_model_calls is not None and budget.model_calls >= budget.max_model_calls:
                return False
            budget = budget.parent
        budget = self
        while budget is not None:
            budget.model_calls += 1
            budget = budget.parent
        return True

    def charge(self, amount: int) -> None:
        self.used += amount
        if self.parent is not None:
            self.parent.charge(amount)

    def hold(self, amount: int) -> None:
        self.held += amount
        if self.parent is not None:
            self.parent.hold(amount)

    def release(self, amount: int) -> None:
        self.held -= amount
        if self.parent is not None:
            self.parent.release(amount)

    def remaining(self) -> int:
        """Tokens still admissible here, net of in-flight holds and ancestors' reserves."""
        own = self.tokens - self.used - self.held
        if self.parent is None:
            return own
        return min(own, self.parent.remaining() - self.reserve)

    def admit(self, estimate: int) -> bool:
        remaining = self.remaining()
        if remaining <= 0 or estimate > remaining:
            return False
        self.hold(estimate)
        return True

    def settle(self, estimate: int, actual: int) -> None:
        self.release(estimate)
        self.charge(actual)

    def overdrawn(self) -> bool:
        """Real usage (not holds) went past this budget or into an ancestor's reserve."""
        if self.used > self.tokens:
            return True
        if self.parent is None:
            return False
        return self.parent.used > self.parent.tokens - self.reserve or self.parent.overdrawn()

    def time_left(self) -> float | None:
        limits = []
        budget = self
        while budget is not None:
            if budget.deadline is not None:
                limits.append(budget.deadline - time.monotonic())
            budget = budget.parent
        return min(limits) if limits else None

    def expired(self) -> bool:
        left = self.time_left()
        return left is not None and left <= 0

    def child(self, tokens: int, seconds: float | None = None, reserve: int = 0) -> Budget:
        deadline = None if seconds is None else time.monotonic() + seconds
        return Budget(tokens=tokens, deadline=deadline, parent=self, reserve=reserve)
