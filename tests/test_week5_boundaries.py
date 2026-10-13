"""Post-merge regressions: preference evidence, disclosure and elapsed-time weighting."""

import pytest

from common.schemas import Reading
from signals.merge import merge_signals, undisclosed
from tests.test_week5 import LOW, reversed_signals, sig
from tests.test_week23_integration import invoke


@pytest.mark.parametrize(
    "evidence",
    ["我不是不信八字", "我并不是不太信八字", "我并非不看重八字", "八字不是唯一依据"],
)
async def test_ambiguous_negation_cannot_persist_discount(runtime, evidence):
    runtime.session.append_user("我更信八字")
    assert (
        await invoke(
            runtime,
            "update_profile",
            dict(field="system_weights", value={"bazi": 1.5}, evidence="我更信八字"),
        )
    ).ok
    before = runtime.store.get_profile(runtime.session.user_id)
    runtime.session.append_user(evidence)
    result = await invoke(
        runtime,
        "update_profile",
        dict(field="system_weights", value={"bazi": 0.5}, evidence=evidence),
    )
    assert not result.ok
    assert runtime.store.get_profile(runtime.session.user_id) == before


async def test_unrelated_negation_does_not_cancel_explicit_preference(runtime):
    evidence = "八字不是唯一依据，但我更信八字"
    runtime.session.append_user(evidence)
    result = await invoke(
        runtime,
        "update_profile",
        dict(field="system_weights", value={"bazi": 1.5}, evidence=evidence),
    )
    assert result.ok, result.error
    assert runtime.store.get_profile(runtime.session.user_id)["system_weights"] == {"bazi": 1.5}


@pytest.mark.parametrize("field", ["theme", "sides", "how_to_read"])
def test_disclosure_date_in_any_visible_tension_field(field):
    tensions = []
    for day, sides in [
        ("11月1日", ["占星：有利", "八字：压力"]),
        ("11月20日", ["占星：压力", "八字：有利"]),
    ]:
        item = dict(theme="career", sides=sides, how_to_read="机会和压力并存")
        if field == "sides":
            item[field][0] += day
        else:
            item[field] += f"（{day}）"
        tensions.append(item)
    reading = Reading(
        question_type="timing",
        systems_used=["astro", "bazi"],
        summary="有条件适合。",
        evidence=[dict(ref_id="r", reading="合成依据")],
        tensions=tensions,
        confidence=LOW,
        safety=dict(flag=False, note=""),
    )
    merged = merge_signals(reversed_signals())
    assert undisclosed(merged, reading) == []
    reading.tensions.pop()
    assert len(undisclosed(merged, reading)) == 1


@pytest.mark.parametrize(
    ("first", "second", "span", "hours"),
    [
        ("2026-03-08", "2026-03-09", "2026-03-01T00:00:00+00:00/2026-03-15T00:00:00+00:00", 23),
        ("2026-11-01", "2026-11-02", "2026-10-08T00:00:00+00:00/2026-11-07T00:00:00+00:00", 25),
        ("2026-11-02", "2026-11-03", "2026-10-08T00:00:00+00:00/2026-11-07T00:00:00+00:00", 24),
    ],
)
def test_fold_uses_elapsed_hours_across_dst(first, second, span, hours):
    # Production-shaped inputs: astro uses local dates, bazi uses UTC period boundaries.
    signals = [
        sig("astro", "career", 0.1, 0.6, "timing", first, "a1"),
        sig("astro", "career", 0.9, 0.6, "timing", second, "a2"),
        sig("bazi", "career", -0.2, 0.6, "timing", span, "b"),
    ]
    merged = merge_signals(signals, tz="America/New_York")
    window = merged["tensions"][0]["windows"][0]
    expected_astro = round((hours * 0.1 + 24 * 0.9) / (hours + 24), 4)
    assert window["sides"][0]["valence"] == expected_astro
    assert window["combined_valence"] == round((expected_astro - 0.2) / 2, 4)
    assert [s["combined_valence"] for s in window["segments"]] == [-0.05, 0.35]
    assert window["window"] == f"{first}/{second}"
    assert merged["merge_version"] == 3
