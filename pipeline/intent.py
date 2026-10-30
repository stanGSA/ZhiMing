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
# A follow-up names the reading or its cards. “什么意思” or “刚才” alone does not: “用八字解释
# 日主是什么意思” and “用塔罗看看我刚才面试的结果” are new questions.
REFERS_TO_READING = re.compile(
    r"第[一二三四1-4]张|[这那]张牌|[这那]几张|[这那]些牌|牌面|牌阵里|"
    r"(?:上一条|上一次|上次|刚才|之前|那次|原来|原先)(?:那次|那条|的)?"
    r"(?:占卜|解读|抽牌|抽的牌|的牌|记录)|原记录|不要?重新抽|不用重抽|不重新?抽"
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
    # Another system named outside the tarot page is that system's question (or several
    # systems'), whatever else the message says.
    if selected is None and OTHER_SYSTEMS.search(message):
        return None
    explicit = selected == ["tarot"] or bool(TAROT.search(message))
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
    if REFERS_TO_READING.search(message) and not redraw:
        target = followup_target(runtime)
        if target:
            return Intent("tarot", "followup", target)
    # “请重新抽一次” after a tarot reading asks for a new draw of the same kind.
    if redraw and followup_target(runtime):
        return Intent("tarot", "new")
    return Intent("tarot", "new") if explicit else None
