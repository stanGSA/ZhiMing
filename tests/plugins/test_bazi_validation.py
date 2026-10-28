from copy import deepcopy

import pytest

from common.evidence import fact_text, fill_evidence
from common.schemas import Reading, Section
from plugins.bazi.validation import validate_output


@pytest.fixture
def state():
    natal = dict(
        pillars=dict(year="辛巳", month="己亥", day="壬辰", time="乙巳"),
        day_master="壬",
        time_known=True,
    )
    period = dict(
        periods=[dict(pillars=dict(year="丁未", month="壬寅", day="甲子"))],
        interpretations=[
            dict(
                ref_id="flow-year",
                fact="period:2027-02-04T01:46:18+00:00:year:丁未:正财",
            )
        ],
    )
    return dict(
        bazi_result=natal,
        bazi_period_result=period,
        calculations=dict(bazi_result=natal, bazi_period_result=period),
    )


def draft(text="先处理眼前的任务。", field="summary"):
    reading = Reading(
        question_type="timing",
        systems_used=["bazi"],
        summary="先处理眼前的任务。",
        evidence=[dict(ref_id="flow-year")],
        confidence=dict(level="low", reason="传统象征解读"),
        safety=dict(flag=False, note=""),
    )
    if field == "evidence":
        reading.evidence[0].reading = text
    elif field == "body":
        reading.sections = [Section(title="节奏", body=text)]
    else:
        setattr(reading, field, text)
    return reading


def test_generated_flow_evidence_is_not_a_natal_pillar(state):
    reading = draft()
    assert not fill_evidence(reading, state)
    assert "年柱:丁未" in reading.evidence[0].reading
    assert validate_output(reading, state) is None


@pytest.mark.parametrize("field", ["summary", "body", "evidence"])
@pytest.mark.parametrize(
    "text",
    [
        "原局年柱辛巳，流年年柱丁未。",
        "流年为丁未，流月月柱为壬寅，流日日柱是甲子。",
        "流年柱为丁未，流月柱壬寅，流日柱甲子。",
        "候选年柱为辛巳。",
    ],
)
def test_scoped_pillars_use_their_own_calculations(state, field, text):
    reading = draft(text, field)
    fill_evidence(reading, state)
    assert validate_output(reading, state) is None


@pytest.mark.parametrize("field", ["summary", "body", "evidence"])
@pytest.mark.parametrize(
    "text",
    [
        "原局年柱丁未。",  # A computed flow year cannot be used as the natal year.
        "你的年柱丁未。",
        "流年年柱辛巳。",  # A natal year cannot be used as a computed flow year.
        "流期月柱丁未。",  # A known year value cannot be used as the flow month.
        "流年月柱丁未。",
    ],
)
def test_scopes_and_pillar_positions_cannot_be_swapped(state, field, text):
    reading = draft(text, field)
    fill_evidence(reading, state)
    assert "柱位与干支不符" in validate_output(reading, state)


def test_generated_fact_requires_matching_reference_and_exact_text(state):
    text = fact_text(state["bazi_period_result"]["interpretations"][0])
    forged = draft(text, "evidence")
    forged.evidence[0].ref_id = "another-ref"
    assert validate_output(forged, state)
    altered = draft(text + "，原局年柱丁未。", "evidence")
    assert validate_output(altered, state)


def test_unknown_time_candidates_and_uncomputed_flows_stay_guarded(state):
    state = deepcopy(state)
    state["bazi_result"]["time_known"] = False
    state["bazi_result"]["pillars"]["time"] = None
    state["bazi_result"]["alternatives"] = [dict(month="壬寅")]
    assert validate_output(draft("候选月柱壬寅。"), state) is None
    assert validate_output(draft("月柱壬寅。"), state)
    assert validate_output(draft("时柱乙巳。"), state)
    state["bazi_period_result"]["periods"] = []
    assert validate_output(draft("流年丁未。"), state)


def test_unknown_time_does_not_block_flow_day_evidence(state):
    state["bazi_result"]["time_known"] = False
    state["bazi_result"]["pillars"]["time"] = None
    assert validate_output(draft("流日日柱甲子。"), state) is None
