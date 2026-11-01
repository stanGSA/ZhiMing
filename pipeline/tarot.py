"""Tarot in the pipeline (P1): the draw, its fact sheet, the card checks, the code readings."""

from __future__ import annotations

import re

from harness.failures import failure
from pipeline import compose, intent, verify
from pipeline.factsheet import Fact, tarot_facts
from pipeline.render import safety_for
from pipeline.system import System
from plugins.tarot.catalogue import SPREADS

SPREAD_NAMES = {"single": "单张牌", "three_card": "三张牌", "decision": "二选一牌阵"}
TIMING = re.compile(r"什么时候|何时|时机|下个?月|下周|这周|本周|这个月|本月|今年|明年|下半年")
# The browser appends the chosen spread to the message; the reading keeps the question itself.
SPREAD_NOTE = re.compile(r"\n*我选择的牌阵为：[^\n]*")
SAFETY_FALLBACK = "这类问题牵涉重大的现实决定，请结合专业意见再做判断。"


class Tarot(System):
    name = "tarot"
    kept = "牌面"

    def detect(self, runtime, message):
        return intent.detect_tarot(runtime, message)

    def question(self, message):
        return SPREAD_NOTE.sub("", message).strip() or message

    async def compute(self, runner, run):
        results, _ = await runner.planned(
            [
                ("start_reading", {"question": run.question, "systems": ["tarot"]}),
                ("draw_tarot", {"question": run.question}),
            ]
        )
        if not all(result["ok"] for result in results):
            error = next(r for r in results if not r["ok"])
            return failure(runner.session, "tool_error", error.get("code"), error["error"])
        return None

    def facts(self, session):
        return tarot_facts(session)

    def messages(self, run, facts, session, *, prior=None, extra=""):
        spread = session.state["tarot_result"]["spread"]
        spread_note = f"{SPREAD_NAMES[spread]}（{'、'.join(SPREADS[spread])}）"
        return compose.tarot_messages(run.question, spread_note, facts, extra=extra, prior=prior)

    def question_type(self, run, session, followup):
        if followup:
            return "tarot"
        if session.state["tarot_result"]["spread"] == "decision":
            return "decision"
        return "timing" if TIMING.search(run.question) else "tarot"

    def problems(self, texts, session):
        return verify.tarot_problems(texts, verify.drawn_cards(session.state))

    def degraded(
        self, session, facts: list[Fact], question_type, risk_text, followup, *, safety_only
    ):
        """A reading made by code alone.

        Normally each card, its position and its keywords. When the drafts failed on a safety
        rule of a high-risk question, no interpretation at all: the cards and the safety note.
        """
        cards = {card["label"]: card for card in session.state["tarot_result"]["cards"]}
        listed = "、".join(f"{fact.label}位{fact.text}" for fact in facts)
        safety = safety_for(risk_text)
        evidence = [{"ref_id": fact.alias} for fact in facts]
        if safety_only:
            return {
                "question_type": question_type,
                "systems_used": ["tarot"],
                "summary": f"这次抽到{listed}。这个问题牵涉重大的现实决定，这次不根据牌面给出判断。"[
                    :200
                ],
                "sections": [],
                "evidence": evidence,
                "advice": ["先听专业意见：把实际情况交给相关专业人士评估，再决定下一步。"],
                "closing": "",
                "confidence": {"level": "low", "reason": "这次没有给出牌面解读。"},
                "safety": safety if safety["flag"] else {"flag": True, "note": SAFETY_FALLBACK},
            }
        sections = []
        for fact in facts:
            keywords = "、".join((cards[fact.label].get("meaning") or {}).get("keywords") or [])
            body = f"{fact.label}位是{fact.text}。"
            if keywords:
                body += f"这张牌常和{keywords}有关，可以对照你现在的处境想一想。"
            sections.append(
                {"title": f"{fact.label}位：{fact.text}", "body": body, "ref_ids": [fact.alias]}
            )
        summary = (
            f"你问到的牌面是：{listed}。下面先给出每张牌的一般含义，请结合自己的处境对照。"
            if followup
            else f"这次抽到{listed}。下面先给出每张牌的一般含义，请结合自己的处境对照。"
        )
        return {
            "question_type": question_type,
            "systems_used": ["tarot"],
            "summary": summary[:200],
            "sections": sections,
            "evidence": evidence,
            "advice": [
                "先对照：把每张牌的关键词和你最近的处境逐条对一对。",
                "再行动：选一件最能落地的小事先做，过一段时间再回头看。",
            ],
            "closing": "",
            "confidence": {"level": "low", "reason": "这次只给出了牌面的一般含义。"},
            "safety": safety,
        }
