"""Post-merge regressions: facts keep their identity across prose and punctuation."""

import copy

import pytest

from common.output_policy import care_advice, care_error, certainty_claim
from plugins.astro.validation import validate_output
from tests.test_pr7_review_fixes import STATE, astro_reading, check, section, tarot_draft


@pytest.mark.parametrize("field", ["sections", "evidence", "summary"])
def test_transit_fact_cannot_prove_an_explicit_natal_claim(field):
    text = "本命木星拱太阳，适合沟通。"
    reading = astro_reading()
    if field == "sections":
        reading = astro_reading(sections=[section(text)])
    elif field == "evidence":
        reading.evidence[0].reading = text
    else:
        reading.summary = text
    assert "本命" in validate_output(reading, STATE)


@pytest.mark.parametrize(
    "body",
    [
        "行运木星拱本命太阳，而本命太阳拱月亮，机会与情绪相互支持。",
        "本命太阳拱月亮，而行运木星拱本命太阳，机会与情绪相互支持。",
        "本命盘中的太阳拱月亮。行运木星拱本命太阳。",
    ],
)
def test_mixed_relations_keep_their_own_context(body):
    assert validate_output(astro_reading(sections=[section(body)]), STATE) is None


@pytest.mark.parametrize(
    "body",
    [
        "2026年11月{day}日，行运木星拱本命太阳。",
        "在2026年11月{day}日，行运木星拱本命太阳。",
        "行运木星拱本命太阳，发生在2026年11月{day}日。",
        "行运木星拱本命太阳。发生于2026年11月{day}日。",
        "行运：2026年11月{day}日木星拱本命太阳。",
    ],
)
def test_dates_bind_across_common_word_order_and_punctuation(body):
    for day, valid in ((5, True), (12, False)):
        error = validate_output(astro_reading(sections=[section(body.format(day=day))]), STATE)
        assert (error is None) == valid, (body, day, error)


def test_prefix_date_for_second_event_does_not_bind_to_first():
    body = "11月5日，行运木星拱太阳，11月20日，行运土星刑月亮。"
    reading = astro_reading(sections=[section(body, ("jupiter", "saturn"))])
    assert validate_output(reading, STATE) is None
    reading.sections[0].body = body.replace("11月20日", "11月5日")
    assert validate_output(reading, STATE)


def test_calendar_and_action_dates_are_not_transit_dates():
    body = "行运木星拱太阳，10月8日寒露后换月。11月12日，我安排练习面试。"
    assert validate_output(astro_reading(sections=[section(body)]), STATE) is None


def test_date_continuation_uses_local_or_utc_date_as_labeled():
    state = copy.deepcopy(STATE)
    state["transit_result"]["events"][0]["exact_date"] = "2026-11-06"
    body = "UTC 11月5日，行运木星拱太阳。"
    assert (
        validate_output(
            astro_reading(evidence_text="先核实条件。", sections=[section(body)]), state
        )
        is None
    )
    body = body.replace("UTC", "当地")
    assert validate_output(
        astro_reading(evidence_text="先核实条件。", sections=[section(body)]), state
    )


@pytest.mark.parametrize(
    "text",
    [
        "身体不适也不建议就医。",
        "身体不适也不应就医。",
        "身体不适不需要马上就医。",
        "身体不适也不应该去医院。",
    ],
)
async def test_negative_medical_advice_is_rejected_by_full_validation(runtime, text):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = text
    error, _ = check(runtime, draft)
    assert error and "不能劝阻就医" in error
    assert care_advice([text])[0] is False


@pytest.mark.parametrize(
    "text",
    [
        "不要以为不必就医。",
        "并非不需要就医。",
        "不能认为身体不适时不需要马上就医。",
        "如有不适请及时就医。",
    ],
)
def test_negating_discouragement_is_not_discouragement(text):
    assert care_error([text]) is None
    assert care_advice([text])[0]


@pytest.mark.parametrize(
    "text,claim",
    [
        ("并非你一定会失败。", None),
        ("这不是你最终必然失败的意思。", None),
        ("并非你这个月一定会失败。", None),
        ("不久后你一定会升职。", "一定会"),
        ("并非没有机会但你一定会失败。", "一定会"),
        ("不代表过去不好但你一定会升职。", "一定会"),
        ("无论如何都一定会顺利。", "一定会"),
    ],
)
def test_negation_scope_allows_subjects_but_stops_at_contrasts(text, claim):
    assert certainty_claim([text]) == claim
