"""Shared output contracts; domain checks are registered by plugins."""

import re

from common.input_evidence import question_range


def validate_calculation_facts(reading, state):
    if state.get("response_mode") == "followup":
        return None
    if (
        reading.question_type == "timing"
        or question_range(state.get("question", ""))
        or re.search(
            r"下个月|本月|这个月|今年|明年|时机",
            state.get("question", ""),
        )
    ):
        temporal = {
            s["system"] for s in state["signals"] if s["horizon"] in ("timing", "short_term")
        }
        for system in set(reading.systems_used) & set(
            state.get("temporal_systems", ("astro", "bazi"))
        ):
            if system not in temporal:
                return "时间范围问题需要相应行运或流期计算，不能只用原局"
    return None
