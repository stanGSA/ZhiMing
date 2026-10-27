"""Original pillars and computed flow pillars retain distinct validation scopes."""

import copy

import pytest

from common.evidence import fact_text, fill_evidence
from common.schemas import Reading
from plugins.bazi.validation import validate_output

STATE = {
    "bazi_result": {
        "pillars": {"year": "辛巳", "month": "己亥", "day": "壬辰", "time": "乙巳"},
        "time_known": True,
    },
    "bazi_period_result": {
        "periods": [{"pillars": {"year": "丙午", "month": "甲午", "day": "丁未", "time": "戊申"}}]
    },
}


def reading(text="原局年柱辛巳，流年丙午。", **overrides):
    return Reading.model_validate(
        {
            "question_type": "trait",
            "systems_used": ["bazi"],
            "summary": text,
            "evidence": [{"ref_id": "period", "reading": "计算事实"}],
            "confidence": {"level": "low", "reason": "草稿"},
            "safety": {"flag": False, "note": ""},
            **overrides,
        }
    )


@pytest.mark.parametrize(
    "pillar,ganzhi,label",
    [
        ("year", "丙午", "流年"),
        ("month", "甲午", "节气流月"),
        ("day", "丁未", "流日"),
        ("time", "戊申", "流时"),
    ],
)
def test_code_generated_flow_evidence_is_not_a_natal_claim(pillar, ganzhi, label):
    atom = {
        "ref_id": "period",
        "fact": f"period:2026-02-03T20:02:08+00:00:{pillar}:{ganzhi}:天干合:year",
    }
    state = {**copy.deepcopy(STATE), "calculations": {"flow": {"interpretations": [atom]}}}
    output = reading(evidence=[{"ref_id": "period"}])
    assert not fill_evidence(output, state)
    assert f"{label}：{ganzhi}" in output.evidence[0].reading
    assert "作用于原局年柱" in output.evidence[0].reading
    assert validate_output(output, state) is None


@pytest.mark.parametrize(
    "text",
    [
        "流年年柱是丙午，原局年柱是辛巳。",
        "原局年柱辛巳，流年年柱丙午。",
        "流年丙午与你年柱辛巳天干相合，与你日柱壬辰天干相冲。",
        "流年与你的年柱辛巳相合。",
        "流年计算结果，年柱是丙午。",
        "流年柱丙午，流月柱甲午，流日柱丁未，流时柱戊申。",
        "节气流月月柱甲午，流日日柱丁未，流时时柱戊申。",
        # Saved evidence rendered before the scope fix must remain usable on follow-up.
        "period:2026-02-03T20:02:08+00:00:年柱:丙午:天干合:年柱",
    ],
)
def test_authored_and_legacy_flow_labels_pass(text):
    assert validate_output(reading(text), copy.deepcopy(STATE)) is None


@pytest.mark.parametrize(
    "text,error",
    [
        ("原局年柱丙午。", "原局年柱应为辛巳"),
        ("流年丙午，原局年柱是丙午。", "原局年柱应为辛巳"),
        ("流年年柱是己亥。", "流期柱位与干支不符"),
        ("流月月柱是丙午。", "流期柱位与干支不符"),
        ("年柱是甲子。", "没有该干支"),
    ],
)
def test_invented_or_misplaced_pillars_still_fail_with_actionable_details(text, error):
    result = validate_output(reading(text), copy.deepcopy(STATE))
    assert result.startswith("summary：") and error in result


def test_flow_scope_cannot_leak_between_fields_or_sentences():
    output = reading("流年丙午。", advice=["年柱是丙午。"])
    assert "advice.0：原局柱位与干支不符" in validate_output(output, copy.deepcopy(STATE))
    assert "原局柱位与干支不符" in validate_output(
        reading("流年丙午。年柱是丙午。"), copy.deepcopy(STATE)
    )


def test_unknown_birth_hour_does_not_prevent_computed_flow_hour():
    state = copy.deepcopy(STATE)
    state["bazi_result"]["time_known"] = False
    state["bazi_result"]["pillars"].pop("time")
    assert validate_output(reading("流时戊申。"), state) is None
    assert validate_output(reading("流时时柱戊申。"), state) is None
    assert validate_output(reading("时柱戊申。"), state)


def test_daily_flow_day_uses_daily_segments():
    state = {
        "daily_result": {
            "bazi": copy.deepcopy(STATE["bazi_result"]),
            "day": {"segments": [{"pillar": "丁未"}]},
        }
    }
    assert validate_output(reading("流日丁未。"), state) is None


def test_natal_fact_rendering_is_unchanged():
    assert fact_text({"fact": "year:辛巳:gan"}) == "年柱:辛巳:天干"
