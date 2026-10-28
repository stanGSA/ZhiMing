"""Separate explaining calculated luck cycles from forecasting a requested period."""

import re

from common.input_evidence import question_range


def dayun_overview(question: str) -> bool:
    if not re.search(r"起运|大运|首运", question):
        return False
    # Birth dates are not consultation intervals. Mixed questions still need flow evidence.
    if question_range(question) or re.search(
        r"流年|流月|流日|今年|明年|去年|本月|下个?月|今天|明天|时机|"
        r"适合|适宜|是否|要不要|能不能|什么时候|何时|"
        r"\d{4}年(?:的)?(?:运势|事业|财运|感情)|运势|吉凶|预测",
        re.sub(r"(?:什么时候|何时)(?:开始)?(?:起运|走大运)", "起运", question),
    ):
        return False
    return True


def dayun_overview_state(state: dict) -> bool:
    question = state.get("question", "")
    return dayun_overview(question) and dayun_overview(state.get("question_source", question))
