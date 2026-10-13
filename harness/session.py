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
    calendar_anchor: str | None = None
    output_validators: dict[str, Any] = field(default_factory=dict)
    # Outer budget for the whole request; run_turn exposes its own as turn_budget.
    budget: Any = None
    turn_budget: Any = None
    parent_call_id: str | None = None
    model_calls: int = 0
    continue_prompt: str = (
        "本轮尚未完成。计算已完成则请使用 submit_reading 提交带有效引用的结果；"
        "资料或地点需要确认则必须使用 ask_user 追问结束本轮。"
    )

    def spawn(
        self,
        role: str,
        partition: str | None,
        *,
        messages: list[dict[str, Any]],
        state: dict[str, Any],
        profile: dict[str, Any],
        parent_call_id: str | None,
        budget: Any,
        continue_prompt: str,
    ) -> Session:
        """Child session: own context, own state; the user's words are copied as evidence only."""
        return Session(
            user_id=self.user_id,
            role=role,
            partition=partition,
            parent_id=self.id,
            messages=messages,
            profile=profile,
            state=state,
            user_messages=list(self.user_messages),
            calendar_anchor=self.calendar_anchor,
            output_validators=self.output_validators,
            budget=budget,
            parent_call_id=parent_call_id,
            continue_prompt=continue_prompt,
        )

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
            "question_message_index": max(0, len(self.user_messages) - 1),
            "seed": seed,
            "signals": [],
            "facts": [],
            "allowed_refs": set(),
            "kb_refs": set(),
            "asked_this_turn": self.state.get("asked_this_turn", False),
            "complete": False,
        }
        return self.state["active_reading_id"]
