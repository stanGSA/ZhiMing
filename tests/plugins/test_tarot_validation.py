import pytest

from common.schemas import Reading, Timeline
from plugins.tarot.validation import validate_output


def reading_with(text, field="body"):
    reading = Reading(
        question_type="daily",
        systems_used=["daily"],
        summary="今天宜稳步推进。",
        sections=[dict(title="今天的提示", body="先处理一个分歧。")],
        evidence=[dict(ref_id="card:reversed", reading="宝剑二逆位。")],
        confidence=dict(level="low", reason="象征性解读"),
        safety=dict(flag=False, note=""),
    )
    if field == "body":
        reading.sections[0].body = text
    elif field == "evidence":
        reading.evidence[0].reading = text
    elif field == "timeline":
        reading.timeline = [Timeline(period="今日", note=text)]
    else:
        setattr(reading, field, text)
    return reading


def card_state(reversed=True):
    return dict(
        facts=["宝剑二"],
        daily_result=dict(card=dict(name="宝剑二", reversed=reversed, ref_id="card:reversed")),
    )


@pytest.mark.parametrize("field", ["body", "evidence", "summary", "timeline", "closing"])
@pytest.mark.parametrize("reversed", [True, False])
def test_orientation_definitions_do_not_change_the_draw(field, reversed):
    right, other = ("逆位", "正位") if reversed else ("正位", "逆位")
    text = (
        f"每日一牌抽到宝剑二{right}。"
        f"宝剑二{other}是双手交叉、蒙眼坐着，象征僵持；{right}则表示另一种提示。"
    )
    reading = reading_with(text, field)
    reading.evidence[0].reading = text if field == "evidence" else f"宝剑二{right}。"
    assert validate_output(reading, card_state(reversed)) is None


@pytest.mark.parametrize("field", ["body", "evidence", "summary", "timeline", "closing"])
@pytest.mark.parametrize(
    "wrong",
    [
        "每日一牌抽到宝剑二正位。",
        "宝剑二正位提醒你放慢。",
        "今天抽到宝剑二正位，是僵持的象征。",
        "本次宝剑二正位通常表示僵持。",
        "宝剑二正位是今天的提示牌。",
        "这张【宝剑二】（正位）代表僵持。",
        "宝剑二（正位）提醒你放慢。",
    ],
)
def test_real_orientation_conflicts_still_fail_with_specific_feedback(field, wrong):
    # A correct mention elsewhere must not hide a contradictory claim.
    reading = reading_with("宝剑二逆位。" + wrong, field)
    error = validate_output(reading, card_state())
    assert "方向错误" in error
    assert "本次应为逆位" in error
    assert wrong.rstrip("。") in error
    assert "勿重新抽牌" in error


def test_unanchored_opposite_orientation_is_not_treated_as_a_comparison():
    assert "方向错误" in validate_output(reading_with("宝剑二正位通常表示僵持。"), card_state())


def test_comparison_does_not_allow_undrawn_cards():
    text = "宝剑二逆位。宝剑二正位通常表示僵持。圣杯二正位代表沟通。"
    assert "未抽出的牌" in validate_output(reading_with(text), card_state())


def test_evidence_is_bound_to_its_own_card_orientation():
    state = card_state()
    state["tarot_result"] = dict(cards=[dict(name="宝剑二", reversed=False, ref_id="card:upright")])
    assert "方向错误" in validate_output(reading_with("宝剑二正位。", "evidence"), state)
