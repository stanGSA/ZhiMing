"""What the runner asks of each system it carries (plan §3.1, P1 tarot and P2 onwards).

The runner owns the steps every system shares: the stored run, the writing call and its one
repair, rendering, submission and degradation. A system supplies what differs: which messages
are its own, the planned calculation, the fact sheet, the writing request, the extra
closed-vocabulary checks and the readings code writes alone.
"""

from __future__ import annotations

from pipeline.factsheet import Fact


class System:
    name: str = ""
    kept = "计算结果"  # what a run keeps for 继续, named to the user

    def __init__(self, runtime):
        self.runtime = runtime

    def detect(self, runtime, message: str):
        """An Intent for a message this system answers, else None."""
        raise NotImplementedError

    def question(self, message: str) -> str:
        return message.strip() or message

    async def compute(self, runner, run):
        """Run the planned calculation; a TurnOutcome ends the turn (an error or a question)."""
        raise NotImplementedError

    def facts(self, session) -> list[Fact]:
        raise NotImplementedError

    def messages(self, run, facts, session, *, prior=None, extra="") -> list[dict]:
        raise NotImplementedError

    def question_type(self, run, session, followup: bool) -> str:
        raise NotImplementedError

    def problems(self, texts: list[str], session) -> list[str]:
        """Closed-vocabulary problems found before submission, all at once."""
        return []

    def complete(self, args: dict, session) -> None:
        """Add what code writes into every reading of this system (after rendering)."""

    def template(self, session, facts, question_type: str, risk_text: str):
        """(kind, arguments) of a reading code writes without a writing call, or None."""
        return None

    def degraded(self, session, facts, question_type, risk_text, followup, *, safety_only):
        raise NotImplementedError
