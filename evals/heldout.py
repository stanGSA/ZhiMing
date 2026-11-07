"""Held-out assertions shared by scripts.live_test and the offline re-scoring (plan P3.0).

``direct_timing_answer`` asks whether the summary's first sentence answers “下个月适合跳槽吗”
head-on. Until P3 it accepted one word order only: the stance before 跳槽 (“下个月适合跳槽”,
“不建议下个月跳槽”). “下个月跳槽不太适合” answers just as directly and was failed. P3.0 accepts
both orders; the old assertion is kept as ``legacy`` so earlier batches can be reported under
both readings, side by side.

The new order is accepted only where the stance closes the clause about next month's job
change. A stance that governs something else (“下个月跳槽前更适合先准备”, “下个月跳槽不如换部门
适合”), a stance behind an outer hedge (“很难说下个月跳槽适合”) or an undecided one (“下个月跳槽
不一定适合”) is not a direct answer.
"""

from __future__ import annotations

import re

STANCE_BEFORE = re.compile(
    r"下个月.*(?:适合|适宜|不宜|建议|可以).*跳槽|(?:适合|不适合|不宜|建议).*下个月.*跳槽"
)
# The stance after 跳槽, within its own clause. Longest first, so 不太适合 is one stance.
STANCES = "不太适合|不大适合|不适合|不适宜|不宜|不建议|不可以|不可|不行|适合|适宜|宜|建议|可以|可行"
# What may stand between 跳槽 and the stance: a short qualifier, not another clause or object.
BETWEEN = r"[^，,。；;？?！!：:]{0,8}?"
STANCE_AFTER = re.compile(
    rf"下个月[^，,。；;？?！!]{{0,4}}?跳槽(?P<between>{BETWEEN})(?P<stance>{STANCES})"
    # The stance ends the clause: it is not the verb of something done instead (适合先准备).
    r"(?=[的了啊吧]?(?:$|[，,。；;？?！!、：:]|但|不过|只是))"
)
# Between 跳槽 and the stance, these make the stance about something else or about the time
# around the change, not the change itself.
ELSEWHERE = re.compile(r"前|之前|以前|后|之后|以后|不如|比|相比|还是|而是|或者|倒是|反而|换|转|留")
# An undecided stance or an outer hedge is not an answer.
UNDECIDED = re.compile(r"不一定|未必|说不准|说不好|难说|不好说|看情况|视情况")
HEDGE_BEFORE = re.compile(
    r"(?:很难说|难以说|不好说|不能说|不可能说|无法说|说不上|不敢说|不是说|并不是说|"
    r"不能断言|无法断言|不能确定)"
    r"[^，,。；;？?！!]{0,6}$"
)


def first_sentence(summary: str | None) -> str:
    return (summary or "").split("。")[0]


def timing_answer_legacy(summary: str | None) -> bool:
    """The assertion as it stood in P1 and P2: the stance before 跳槽 only."""
    return bool(STANCE_BEFORE.search(first_sentence(summary)))


def stance_after(sentence: str) -> bool:
    for match in STANCE_AFTER.finditer(sentence):
        between = match["between"]
        if ELSEWHERE.search(between) or UNDECIDED.search(between):
            continue
        if HEDGE_BEFORE.search(sentence[: match.start()]):
            continue
        return True
    return False


def timing_answer(summary: str | None) -> bool:
    """P3.0: either word order, “下个月适合跳槽” or “下个月跳槽不太适合”."""
    sentence = first_sentence(summary)
    return bool(STANCE_BEFORE.search(sentence)) or stance_after(sentence)
