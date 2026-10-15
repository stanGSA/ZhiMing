"""Regression cases from the PR #7 review: layered text keeps the same factual guarantees."""

import copy

import pytest

from agents.schemas import ReportInput
from agents.specialists import as_reading
from common.output_policy import HEALTH_NOTE, certainty_claim
from common.schemas import Reading
from common.tools import render_reading
from common.validation import validate_reading
from plugins.astro.validation import validate_output

JUPITER = dict(
    transit_body="Jupiter",
    natal_body="Sun",
    aspect="trine",
    exact_utc="2026-11-05T10:00:00+00:00",
    exact_date="2026-11-05",
    orb_deg=0.0,
    allowed_orb_deg=1.0,
)
SATURN = dict(
    transit_body="Saturn",
    natal_body="Moon",
    aspect="square",
    exact_utc="2026-11-20T10:00:00+00:00",
    exact_date="2026-11-20",
    orb_deg=0.0,
    allowed_orb_deg=1.0,
)


def fact(event):
    return (
        f"transit:{event['exact_utc']}:{event['transit_body']}:"
        f"{event['natal_body']}:{event['aspect']}"
    )


STATE = dict(
    natal_result=dict(
        time_known=True,
        planets=[dict(body_zh="太阳", sign_zh="狮子", house=4)],
        aspects=[dict(a="Sun", b="Moon", type="trine")],
    ),
    transit_result=dict(
        events=[JUPITER, SATURN],
        interpretations=[
            dict(ref_id="jupiter", fact=fact(JUPITER)),
            dict(ref_id="saturn", fact=fact(SATURN)),
        ],
    ),
)


def astro_reading(evidence_text="11月5日行运木星拱本命太阳。", sections=()):
    return Reading.model_validate(
        dict(
            question_type="timing",
            systems_used=["astro"],
            summary="有条件适合推进",
            sections=list(sections),
            evidence=[dict(ref_id="jupiter", reading=evidence_text)],
            confidence=dict(level="low", reason="草稿"),
            safety=dict(flag=False, note=""),
        )
    )


def section(body, refs=("jupiter",), title="外部支持"):
    return dict(title=title, body=body, ref_ids=list(refs))


# --- 1. sections are bound to the events they cite -------------------------------------


def test_relation_moved_from_evidence_to_cited_section_still_passes():
    text = "木星拱太阳，容易得到支持。"
    assert validate_output(astro_reading(evidence_text=text), STATE) is None
    assert validate_output(astro_reading(sections=[section(text)]), STATE) is None


def test_wrong_date_in_cited_section_is_rejected():
    wrong = "木星拱太阳，容易得到支持。这一相位的精确日期是2026年11月12日。"
    assert validate_output(
        astro_reading(evidence_text="这一相位的精确日期是2026年11月12日。"), STATE
    )
    assert validate_output(astro_reading(sections=[section(wrong)]), STATE)
    right = wrong.replace("11月12日", "11月5日")
    assert validate_output(astro_reading(sections=[section(right)]), STATE) is None
    # A date written right before the relation is bound the same way.
    assert validate_output(astro_reading(sections=[section("11月12日木星拱太阳。")]), STATE)
    # So is a date after the relation that names it, in evidence and sections alike.
    trailing = "行运木星拱本命太阳，精确日期是2026年11月12日。"
    assert validate_output(astro_reading(evidence_text=trailing), STATE)
    assert validate_output(astro_reading(sections=[section(trailing)]), STATE)
    unrelated = "木星拱太阳带来支持，10月8日寒露后换月。"
    assert validate_output(astro_reading(sections=[section(unrelated)]), STATE) is None


def test_title_sets_transit_context_for_the_body():
    layer = section(
        "这一相位容易带来外部支持；木星拱太阳时适合主动沟通。",
        refs=(),
        title="行运木星拱本命太阳",
    )
    assert validate_output(astro_reading(sections=[layer]), STATE) is None
    layer["body"] += "这一相位的精确日期是11月12日。"
    assert validate_output(astro_reading(sections=[layer]), STATE)
    # Without the title's context the same body is read as a natal relation.
    layer = section("木星拱太阳时适合主动沟通。", refs=(), title="外部支持")
    assert validate_output(astro_reading(sections=[layer]), STATE)


def test_events_cited_by_one_section_are_not_mixed():
    both = ("jupiter", "saturn")
    ok = "11月5日木星拱太阳，11月20日土星刑月亮，先松后紧。"
    assert validate_output(astro_reading(sections=[section(ok, both)]), STATE) is None
    swapped = "木星拱太阳，精确日期是2026年11月20日。"
    assert validate_output(astro_reading(sections=[section(swapped, both)]), STATE)
    # Dates written after each relation stay with their own clause.
    after = "木星拱太阳在11月5日精确，土星刑月亮在11月20日精确。"
    assert validate_output(astro_reading(sections=[section(after, both)]), STATE) is None
    crossed = "木星拱太阳在11月20日精确，土星刑月亮在11月5日精确。"
    assert validate_output(astro_reading(sections=[section(crossed, both)]), STATE)
    # A relation the section does not cite cannot borrow another layer's event.
    uncited = section("行运土星刑月亮，压力上升。", refs=("jupiter",))
    assert "ref_ids" in validate_output(astro_reading(sections=[uncited]), STATE)


def test_natal_relation_may_sit_in_a_transit_layer():
    layer = section("木星拱太阳带来助力，而太阳拱月亮让你情绪稳定。")
    assert validate_output(astro_reading(sections=[layer]), STATE) is None


def test_orb_in_section_is_checked_against_the_cited_event():
    layer = section("木星拱太阳，容许度为1度。")
    assert validate_output(astro_reading(sections=[layer]), STATE) is None
    layer["body"] = "木星拱太阳，容许度为7度。"
    assert validate_output(astro_reading(sections=[layer]), STATE)


def test_specialist_analysis_is_bound_to_its_points():
    def report(analysis):
        return ReportInput.model_validate(
            dict(
                answer="倾向先稳住节奏。",
                analysis=analysis,
                points=[{"ref_id": "jupiter", "text": "11月5日行运木星拱本命太阳。"}],
                confidence={"level": "low", "reason": "草稿"},
            )
        )

    good = as_reading(report("木星拱太阳，容易得到支持。"), "astro")
    assert validate_output(good, STATE) is None
    bad = as_reading(report("木星拱太阳。这一相位的精确日期是2026年11月12日。"), "astro")
    assert validate_output(bad, STATE)


# --- 2. a health remark needs visible, affirmative advice; discouraging care is rejected


async def tarot_draft(runtime):
    outcome = await runtime.turn("看看近期状态")
    assert outcome.status == "submit_reading"
    draft = copy.deepcopy(outcome.data["reading"])
    ref = draft["evidence"][0]["ref_id"]
    draft["sections"] = [{"title": "能量调整", "body": "过去的模糊正在澄清。", "ref_ids": [ref]}]
    return draft


def check(runtime, draft):
    reading = Reading.model_validate(draft)
    return validate_reading(reading, runtime.session), reading


async def test_discouraging_medical_care_is_rejected(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "肾属水，肾脏不适无需就医。"
    error, _ = check(runtime, draft)
    assert error and "不能劝阻就医" in error


async def test_unrelated_hospital_mention_does_not_count_as_advice(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "肾属水，办公室在医院附近。"
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.safety.flag and reading.safety.note.endswith(HEALTH_NOTE)


async def test_advice_hidden_in_unrendered_fields_does_not_count(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "注意肾与泌尿系统的养护。"
    draft["followups"] = ["如有不适请及时就医吗？"]
    draft["evidence"][0]["reading"] += "身体不适请及时就医。"  # folded appendix
    error, reading = check(runtime, draft)
    assert error is None and HEALTH_NOTE in reading.safety.note


async def test_visible_advice_is_not_repeated(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "注意肾的养护，如有不适请及时就医。"
    error, reading = check(runtime, draft)
    assert error is None
    assert not reading.safety.flag and HEALTH_NOTE not in reading.safety.note
    # Advice written only in an unflagged safety note is made visible, not duplicated.
    draft["sections"][0]["body"] = "注意肾的养护。"
    draft["safety"] = {"flag": False, "note": "如有不适请及时就医。"}
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.safety.flag and reading.safety.note == "如有不适请及时就医。"


def test_specialist_report_cannot_discourage_care():
    from agents.specialists import validate_report

    class Session:
        role = "bazi"
        state = {"signals": [{"system": "bazi", "ref_id": "r1", "reviewed": False}]}
        output_validators = {}

    report = ReportInput.model_validate(
        dict(
            answer="倾向先休整。",
            analysis="水弱时容易疲劳，身体不适也不必就医，多喝水即可。",
            points=[{"ref_id": "r1", "text": "日主壬水。"}],
            confidence={"level": "low", "reason": "草稿"},
        )
    )
    assert "不能劝阻就医" in validate_report(report, Session())


# --- 3. certainty: only a negation that governs the word cancels it ----------------------


@pytest.mark.parametrize(
    "text,claim",
    [
        ("不久后你一定会升职。", "一定会"),
        ("无论如何都一定会顺利。", "一定会"),
        ("没过多久你必然会成功。", "必然"),
        ("不一定会", None),
        ("结果并不一定会如愿。", None),
        ("并非注定如此。", None),
        ("这不代表事件必然发生。", None),
        ("并不意味着你一定会失败。", None),
        ("这不是必然的结果。", None),
        ("一定要保证睡眠。", None),
    ],
)
def test_certainty_negation_scope(text, claim):
    assert certainty_claim([text]) == claim


async def test_unrelated_negation_does_not_hide_certainty(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "不久后你一定会升职。"
    error, _ = check(runtime, draft)
    assert error and "一定会" in error


# --- 4. a layered reply shows the evidence count, the record keeps the items -------------


def layered(**fields):
    return (
        dict(
            summary="这个月有条件适合推进。",
            sections=[{"title": "核心碰撞：辰戌相冲", "body": "挑战与机遇并存。", "ref_ids": []}],
            evidence=[
                {"ref_id": "r1", "reading": "流月戊戌。"},
                {"ref_id": "r2", "reading": "日柱壬辰。"},
            ],
            advice=["精力聚焦：只推进一个目标。"],
            timeline=[],
            resonances=[],
            tensions=[],
            closing="扛过去会更稳。",
            confidence={"level": "low", "reason": "草稿"},
            safety={"flag": False, "note": ""},
        )
        | fields
    )


def test_layered_reply_shows_only_the_evidence_count():
    text = render_reading(layered())
    assert "解读依据：共 2 条计算事实" in text
    assert "流月戊戌" not in text and "日柱壬辰" not in text


def test_reading_without_sections_still_lists_evidence():
    old = layered(sections=[])
    del old["closing"]
    text = render_reading(old)
    assert "流月戊戌" in text and "共 2 条" not in text


async def test_first_reply_followup_and_history_paths(runtime):
    first = await runtime.turn("用塔罗看看近期状态")
    assert first.status == "submit_reading"
    evidence = first.data["reading"]["evidence"]
    assert f"共 {len(evidence)} 条" in first.text
    assert evidence[0]["reading"] not in first.text
    stored = runtime.store.get_reading(runtime.session.user_id, first.data["reading_id"])
    assert stored["output_json"]["evidence"] == evidence  # full items stay in the record
    assert render_reading(stored["output_json"]) == first.text  # history renders the same
    followup = await runtime.turn("第二张牌具体什么意思？")
    assert followup.status == "submit_reading"
    shown = followup.data["reading"]
    if shown.get("sections"):
        assert f"共 {len(shown['evidence'])} 条" in followup.text
    else:  # the demo's follow-up has no sections, so it keeps the original layout
        assert shown["evidence"][0]["reading"] in followup.text


async def test_name_disclosure_only_in_folded_evidence_is_not_shown(runtime):
    from tests.test_week6_followup_fixes import EXPLAIN, name_draft

    value = await name_draft(runtime)
    value["sections"] = [{"title": "数理", "body": "人格26，体现成长。", "ref_ids": []}]
    value["evidence"][0]["reading"] = "人格26。" + EXPLAIN
    from tests.test_week23_integration import invoke

    rejected = await invoke(runtime, "submit_reading", value)
    assert not rejected.ok and "多种写法" in rejected.error
    value["advice"] = [EXPLAIN]
    accepted = await invoke(runtime, "submit_reading", value)
    assert accepted.ok and EXPLAIN in accepted.data["text"]


async def test_medical_rules_apply_to_the_multi_agent_answer(project):
    from app import create_runtime

    runtime = create_runtime(root=project, user_id="multi-care", seed=42, mode="multi")
    try:
        outcome = await runtime.turn("用塔罗看看近期状态")
        assert outcome.status == "submit_reading", outcome.text
        draft = copy.deepcopy(outcome.data["reading"])
        draft["sections"] = [{"title": "调整", "body": "注意肾的养护，少熬夜。", "ref_ids": []}]
        error, reading = check(runtime, draft)
        assert error is None and HEALTH_NOTE in reading.safety.note
        draft["sections"][0]["body"] = "肾脏不适也不用去医院。"
        error, _ = check(runtime, draft)
        assert error and "不能劝阻就医" in error
    finally:
        runtime.close()
