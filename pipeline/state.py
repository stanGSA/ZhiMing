"""One pipeline run, stored after each stage so an interrupted run resumes (plan P1.1).

The calculation of a reading lives in the session until submit_reading saves it. A run that
stops after the draw (a model error, a timeout, a restart) keeps a snapshot of that state, so
the next turn writes the reading from the same cards instead of drawing again.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

# Stages after which the calculation exists and the run can be resumed.
RESUMABLE = ("computed", "composed")
# Session state that belongs to the conversation, not to the reading being computed.
NOT_SNAPSHOTTED = ("ref_alias", "asked_this_turn", "output_warnings", "output")
SET_KEYS = ("allowed_refs", "kb_refs")


@dataclass
class PipelineRun:
    system: str
    kind: str  # "new" or "followup"
    question: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    stage: str = "intent"
    snapshot: dict = field(default_factory=dict)
    drafts: list[str] = field(default_factory=list)
    problems: list[list[str]] = field(default_factory=list)
    model_calls: int = 0
    repairs: int = 0

    def save(self, store, session, stage: str) -> None:
        self.stage = stage
        store.save_pipeline_run(
            self.run_id,
            session.user_id,
            session.id,
            session.state.get("active_reading_id"),
            stage,
            asdict(self),
        )

    @classmethod
    def load(cls, row: dict) -> PipelineRun:
        fields = {k: v for k, v in row["state"].items() if k in cls.__dataclass_fields__}
        return cls(**fields)


def snapshot(state: dict) -> dict:
    """The reading's state as JSON: sets become sorted lists."""
    return {
        key: sorted(value) if key in SET_KEYS else value
        for key, value in state.items()
        if key not in NOT_SNAPSHOTTED
    }


def restore(session, saved: dict) -> None:
    """Put a snapshot back into the session; this conversation's R-numbers stay its own."""
    state = {key: set(value) if key in SET_KEYS else value for key, value in saved.items()}
    state["ref_alias"] = session.state.get("ref_alias", {})
    # The question that started the run is not among this session's messages.
    state["question_message_index"] = -1
    state["complete"] = False
    session.state = state
    session.cache.clear()
