"""Shared output contracts; domain checks are registered by plugins."""

import re
from typing import Literal

from common.input_evidence import question_range

# A value named right after a governing negation (“不是正义正位”“不在处女座”) is the value the
# sentence denies, not one it asserts. Only the words directly before the value count. A denied
# value is still a checkable claim: denying the computed value is as wrong as asserting another.
NEGATED_VALUE = re.compile(
    r"(?:不是|并不是|并非|而非|不再是|不在|并不在|不落在|没有落在|没落在)\s*[【「《“\"]?$"
)
# “并非不在白羊座” denies the denial, so the value is asserted.
DENIED_NEGATION = re.compile(r"(?:不是|并不是|并非|绝非|非)\s*$")
INFERENCE_TAIL = re.compile(
    r"[\s】」》”\"'）)]*(?:就(?:意味着|代表|说明|等于|会|一定|必然)|(?:的)?人(?:都|就))"
)


def value_claim(text: str, start: int, end: int) -> Literal["asserted", "denied"] | None:
    """Classify a complete value mention; None means a negated inference, not a fact claim.

    “并非狮子座就一定外向” denies an inference, not the sign. Inspect only the syntax immediately
    after this value, so a later inference cannot hide an independent denial of the actual value.
    """
    window = text[max(0, start - 12) : start]
    negation = NEGATED_VALUE.search(window)
    if not negation or DENIED_NEGATION.search(window[: negation.start()]):
        return "asserted"
    if re.match(r"并不是|不是|并非|而非", negation.group()) and INFERENCE_TAIL.match(text, end):
        return None
    return "denied"


def validate_calculation_facts(reading, state):
    from plugins.bazi.intent import dayun_overview_state

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
                # A computed luck-cycle table is evidence for its own explanation, not
                # evidence for arbitrary annual/monthly forecasts or another system.
                if (
                    system == "bazi"
                    and dayun_overview_state(state)
                    and (state.get("bazi_result") or {}).get("dayun")
                    and not state.get("timeframe_required")
                ):
                    continue
                return "时间范围问题需要相应行运或流期计算，不能只用原局"
    return None


def public_texts(reading) -> list[str]:
    """All authored text to validate, including metadata that is not always rendered."""
    return [
        reading.summary,
        *section_texts(reading),
        *[e.reading for e in reading.evidence],
        *reading.advice,
        reading.closing,
        *reading.resonances,
        *[part for t in reading.tensions for part in (t.theme, *t.sides, t.how_to_read)],
        *[part for t in reading.timeline for part in (t.period, t.note)],
        *reading.followups,
        reading.confidence.reason,
        reading.safety.note,
    ]


def rendered_texts(reading) -> list[str]:
    """Texts actually displayed by render_reading; mandatory disclosures belong here.

    Confidence.reason and followups remain structured metadata. A layered reading shows only
    the number of its evidence items (the web panel folds them), so its evidence is not
    counted as shown; a reading without sections still lists its evidence in full.
    Checking any of these for false claims must not count as disclosing them to the user.
    """
    return [
        reading.summary,
        *section_texts(reading),
        *reading.advice,
        *[part for t in reading.timeline for part in (t.period, t.note)],
        *reading.resonances,
        *[part for t in reading.tensions for part in (t.theme, *t.sides, t.how_to_read)],
        getattr(reading, "closing", ""),
        *([] if section_texts(reading) else [e.reading for e in reading.evidence]),
        *([reading.safety.note] if reading.safety.flag else []),
    ]


def section_texts(reading) -> list[str]:
    """Titles and bodies of the layered analysis (absent on readings saved before it)."""
    return [part for s in getattr(reading, "sections", []) for part in (s.title, s.body)]
