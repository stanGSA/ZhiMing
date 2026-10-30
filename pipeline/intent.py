"""What a message asks for, decided by code (plan §3.4).

P1 routes tarot only. The tarot page fixes the system; elsewhere a message must ask for tarot
and nothing else. Anything else returns None and keeps the agent loop. A model is not needed to
decide this for tarot; it is added in P3 for questions that span systems.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.state import RESUMABLE

TAROT = re.compile(r"塔罗|牌阵|抽[一二两三]?张|[一二两三单]张牌")
OTHER_SYSTEMS = re.compile(
    r"八字|四柱|命盘|占星|星盘|星座|行运|本命|姓名|名字|五格|解梦|梦见|梦到|做梦|"
    r"每日运势|今日运势|今天运势|流日|流年|大运"
)
FOLLOWUP = re.compile(
    r"第[一二三1-3]张|这张牌|那张牌|刚才|上一条|上次|那次|之前|原记录|"
    r"不要?重新抽|不重抽|不用重抽|什么意思|再解释|详细说说|具体说说"
)
# “不要重新抽牌” asks for the opposite of a redraw.
REDRAW = re.compile(r"(?<!不要)(?<!不用)(?<![不别])(?:重新抽|重抽|再抽|重新占)")
CONTINUE = re.compile(r"^\s*(?:请)?(?:继续|接着|重试|再试)")


@dataclass
class Intent:
    system: str
    kind: str  # "new", "followup" or "resume"
    reading_id: str | None = None
    run: dict | None = None  # the stored unfinished run to resume


def tarot_only(saved: dict | None) -> bool:
    return bool(saved) and saved.get("systems_used") == ["tarot"]


def followup_target(runtime) -> str | None:
    """The tarot reading a follow-up refers to: this session's, else the user's latest."""
    session, store = runtime.session, runtime.store
    state = session.state
    if state.get("complete") and state.get("tarot_result") and state.get("active_reading_id"):
        saved = store.get_reading(session.user_id, state["active_reading_id"])
        if tarot_only(saved):
            return saved["reading_id"]
    recent = store.recent_readings(session.user_id, limit=1)
    if recent:
        saved = store.get_reading(session.user_id, recent[0]["reading_id"])
        if tarot_only(saved):
            return saved["reading_id"]
    return None


def detect(runtime, message: str) -> Intent | None:
    if "tarot" not in runtime.pipeline_systems:
        return None
    session = runtime.session
    state = session.state
    selected = state.get("selected_systems")
    if selected not in (None, ["tarot"]):
        return None
    if session.pinned_reading_id:
        saved = runtime.store.get_reading(session.user_id, session.pinned_reading_id)
        return Intent("tarot", "followup", saved["reading_id"]) if tarot_only(saved) else None
    explicit = selected == ["tarot"] or bool(
        TAROT.search(message) and not OTHER_SYSTEMS.search(message)
    )
    redraw = bool(REDRAW.search(message))
    # A draw of this session not answered yet is answered from the same cards; only an
    # explicit redraw replaces it, exactly as start_reading requires.
    if state.get("tarot_drawn") and not state.get("complete") and not redraw:
        if explicit or CONTINUE.search(message):
            return Intent("tarot", "resume")
    run = runtime.store.unfinished_pipeline_run(session.user_id)
    if (
        run
        and run["stage"] in RESUMABLE
        and run["state"].get("system") == "tarot"
        and not redraw
        and (CONTINUE.search(message) or message.strip() == run["state"]["question"].strip())
    ):
        return Intent("tarot", "resume", run=run)
    if FOLLOWUP.search(message) and not redraw:
        target = followup_target(runtime)
        if target:
            return Intent("tarot", "followup", target)
    # “请重新抽一次” after a tarot reading asks for a new draw of the same kind.
    if redraw and not OTHER_SYSTEMS.search(message) and followup_target(runtime):
        return Intent("tarot", "new")
    return Intent("tarot", "new") if explicit else None
