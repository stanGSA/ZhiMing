from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CALENDAR_TZ = "Asia/Shanghai"


def valid_timezone(name: Any) -> bool:
    if not isinstance(name, str) or not name:
        return False
    try:
        ZoneInfo(name)
    except (ValueError, OSError, ZoneInfoNotFoundError):
        return False
    return True


def profile_timezone(profile: dict[str, Any]) -> str | None:
    """Consultation timezone first, then birth timezone; invalid stored values are skipped."""
    return next(
        (profile[f] for f in ("consultation_tz", "tz") if valid_timezone(profile.get(f))), None
    )


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
    # Deck positions chosen in the browser for the next draw; start_reading consumes them.
    pending_picks: tuple[int, ...] | None = None
    calendar_anchor: str | None = None
    calendar_timezone: str = DEFAULT_CALENDAR_TZ
    calendar_instant: datetime | None = None
    safety_pending: bool = False
    policy_judge: Any = None
    # Trusted browser form snapshot for this request, independent of model-written profile.
    birth_binding: dict[str, Any] | None = None
    # Browser provenance travels separately from the model-editable profile/state.
    birth_context: dict[str, Any] | None = None
    birth_version_valid: Any = None
    pinned_reading_id: str | None = None
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
            calendar_timezone=self.calendar_timezone,
            calendar_instant=self.calendar_instant,
            output_validators=self.output_validators,
            birth_binding=self.birth_binding if partition in ("astro", "bazi") else None,
            birth_context=self.birth_context if partition in ("astro", "bazi") else None,
            birth_version_valid=self.birth_version_valid,
            pinned_reading_id=self.pinned_reading_id,
            budget=budget,
            parent_call_id=parent_call_id,
            continue_prompt=continue_prompt,
        )

    def refresh_calendar(self, instant: datetime | None = None) -> None:
        instant = instant or self.calendar_instant
        if instant is None:
            return
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Calendar clock must return a timezone-aware datetime")
        timezone = profile_timezone(self.profile) or DEFAULT_CALENDAR_TZ
        self.calendar_anchor = instant.astimezone(ZoneInfo(timezone)).date().isoformat()
        self.calendar_timezone = timezone
        self.calendar_instant = instant
        prefix = "本轮日历基准（"
        self.messages[:] = [
            m
            for m in self.messages
            if not (m["role"] == "system" and m.get("content", "").startswith(prefix))
        ]
        self.messages.insert(
            1,
            {
                "role": "system",
                "content": f"{prefix}{timezone}）：{self.calendar_anchor}；"
                "按用户指定日期范围优先，不猜系统月份。",
            },
        )

    def append_user(self, text: str) -> None:
        self.user_messages.append(text)
        self.messages.append({"role": "user", "content": text})
        self.state["asked_this_turn"] = False

    def choose_picks(self, picks: tuple[int, ...] | None) -> None:
        """Deck positions sent with this request. A new reading takes them at start_reading; a
        reading still open (the reply to a clarifying question) takes them now, so the draw
        always uses the latest choice."""
        self.pending_picks = picks
        if picks and self.state.get("active_reading_id") and not self.state.get("complete"):
            self.state["picks"] = list(picks)

    def start_reading(self, question: str) -> str:
        previous = self.state.get("active_reading_id")
        # Fixture injection controls only the first draw, never later redraws.
        seed = self.default_seed if self.default_seed is not None else secrets.randbits(64)
        self.default_seed = None
        while seed == self.state.get("seed"):
            seed = secrets.randbits(64)
        self.cache.clear()
        selection = {
            k: self.state[k] for k in ("selected_systems", "selected_spread") if k in self.state
        }
        self.state = {
            **selection,
            # Tool messages from earlier readings remain in this model conversation.
            # Never reassign their aliases to a different calculation.
            "ref_alias": self.state.get("ref_alias", {}),
            "systems": selection.get("selected_systems"),
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
        if self.birth_binding and self.birth_binding.get("location"):
            location = self.birth_binding["location"]
            self.state["locations"] = {location["location_id"]: dict(location)}
        if self.pending_picks:
            self.state["picks"] = list(self.pending_picks)
        self.pending_picks = None
        return self.state["active_reading_id"]
