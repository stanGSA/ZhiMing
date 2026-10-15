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
