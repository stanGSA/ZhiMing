"""Daily aspect claims use event membership after normalizing wording and roles."""

import pytest

from pipeline.daily import Daily, daily_aspect_assertions


@pytest.mark.parametrize(
    "word, aspect",
    [
        ("合相", "conjunction"),
        ("合", "conjunction"),
        ("对分", "opposition"),
        ("对冲", "opposition"),
        ("冲相", "opposition"),
        ("冲", "opposition"),
        ("三分", "trine"),
        ("拱相", "trine"),
        ("拱", "trine"),
        ("四分", "square"),
        ("刑相", "square"),
        ("刑", "square"),
        ("刑克", "square"),
        ("六分", "sextile"),
        ("六合", "sextile"),
    ],
)
@pytest.mark.parametrize(
    "template",
    [
        "月亮与本命冥王星的{word}。",
        "月亮{word}本命冥王星。",
        "本命冥王星与行运月亮{word}。",
        "本命的冥王星{word}行运的月亮。",
    ],
)
def test_daily_aspect_wording_must_match_an_actual_event(word, aspect, template):
    claim = template.format(word=word)
    result = {
        "bazi": {"day_master": "丁火"},
        "day": {"element": "火"},
        "date": "2026-10-31",
        "events": [],
    }
    assert Daily.fact_claim_problems(claim, result)
    result["events"] = [{"transit_body": "Moon", "natal_body": "Pluto", "aspect": aspect}]
    assert Daily.fact_claim_problems(claim, result) == []


@pytest.mark.parametrize(
    "claim, expected",
    [
        (
            "月亮与本命太阳、木星的六分相。",
            [("Moon", "Sun", "sextile"), ("Moon", "Jupiter", "sextile")],
        ),
        (
            "本命的木星与行运的月亮、水星六合。",
            [("Moon", "Jupiter", "sextile"), ("Mercury", "Jupiter", "sextile")],
        ),
        (
            "本命木星与本命太阳、月亮三分相。",
            [],
        ),
        (
            "本命木星与太阳、月亮三分相。",
            [],
        ),
        (
            "本命木星与行运月亮、本命太阳六合。",
            [("Moon", "Jupiter", "sextile")],
        ),
        (
            "行运木星与行运太阳、月亮三分相。",
            [],
        ),
        (
            "月亮与本命冥王星冲突，先把分歧说清楚。",
            [],
        ),
        (
            "月亮与本命木星对冲，行运水星与本命木星六合。",
            [("Moon", "Jupiter", "opposition"), ("Mercury", "Jupiter", "sextile")],
        ),
    ],
)
def test_daily_aspect_lists_and_unrelated_uses(claim, expected):
    assert list(daily_aspect_assertions(claim)) == expected
