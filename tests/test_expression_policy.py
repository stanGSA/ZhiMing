"""Layered answers: facts stay strict, wording is repaired instead of rejected."""

import copy

import pytest

from agents.consult import project as project_report
from agents.reviewer import packet_from_reading
from agents.schemas import ReportInput
from app import create_runtime
from common.output_policy import HEALTH_NOTE, certainty_claim, normalize_report
from common.schemas import Reading
from common.tools import render_reading
from common.validation import validate_reading


async def tarot_draft(runtime):
    outcome = await runtime.turn("看看近期状态")
    assert outcome.status == "submit_reading"
    draft = copy.deepcopy(outcome.data["reading"])
    ref = draft["evidence"][0]["ref_id"]
    draft["sections"] = [
        {"title": "牌阵基调：从困惑到重整", "body": "过去的模糊正在澄清。", "ref_ids": [ref]}
    ]
    draft["closing"] = "先看清现实条件，再决定用力的方向。"
    return draft


def check(runtime, draft):
    reading = Reading.model_validate(draft)
    return validate_reading(reading, runtime.session), reading


def output(**fields):
    base = dict(
        summary="这个月有条件适合推进，前提是先核实条件。",
        sections=[],
        evidence=[{"ref_id": "r1", "reading": "【月亮】逆位。"}],
        advice=["精力聚焦：只推进一个目标。"],
        timeline=[],
        resonances=[],
        tensions=[],
        closing="",
        confidence={"level": "low", "reason": "草稿"},
        safety={"flag": False, "note": ""},
    )
    return base | fields


def test_render_puts_layers_first_and_evidence_last():
    text = render_reading(
        output(
            sections=[
                {"title": "核心碰撞：辰戌相冲", "body": "挑战与机遇并存。", "ref_ids": []},
                {"title": "能量压制：财生七杀", "body": "压力转为动力。", "ref_ids": []},
            ],
            closing="扛过去之后，抗压能力会上一个台阶。",
        )
    )
    order = [
        "这个月",
        "一、核心碰撞：辰戌相冲",
        "二、能量压制：财生七杀",
        "行动建议：",
        "扛过去之后",
        "解读依据：共 1 条",
        "仅供参考与自我反思。",
    ]
    positions = [text.index(part) for part in order]
    assert positions == sorted(positions)
    assert "【月亮】逆位" not in text  # the appendix is counted, not listed


def test_render_keeps_layout_of_readings_saved_before_sections():
    saved = output()
    del saved["sections"], saved["closing"]
    text = render_reading(saved)
    assert text.index("依据：") < text.index("可以考虑：")
    assert "解读依据：" not in text


async def test_sections_are_saved_and_rendered(runtime):
    draft = await tarot_draft(runtime)
    error, _ = check(runtime, draft)
    assert error is None
    assert len(Reading.model_validate(draft).sections) == 1


async def test_disclaimer_and_internal_sentences_are_removed_not_rejected(runtime):
    draft = await tarot_draft(runtime)
    draft["summary"] = "近期宜先梳理现状。以上内容仅供参考。"
    draft["sections"][0]["body"] = "过去的模糊正在澄清。知识库释义提示先分辨事实。保存失败请重试。"
    draft["advice"] = ["先核实条件。", "仅供娱乐。"]
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.summary == "近期宜先梳理现状。"
    assert reading.sections[0].body == "过去的模糊正在澄清。传统释义提示先分辨事实。"
    assert reading.advice == ["先核实条件。"]


async def test_html_line_breaks_become_line_breaks(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = (
        "过去的模糊正在澄清。<br>潜在挑战：节奏被打乱。<BR/>潜在机遇：看清重点。"
    )
    error, reading = check(runtime, draft)
    assert error is None
    assert (
        reading.sections[0].body
        == "过去的模糊正在澄清。\n潜在挑战：节奏被打乱。\n潜在机遇：看清重点。"
    )
    assert "<br" not in render_reading(reading.model_dump(mode="json")).lower()


async def test_jargon_in_verdict_titles_and_advice_is_a_warning(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["title"] = "能量压制：财生七杀"
    draft["advice"] = ["偏财运：多留意外部机会。"]
    error, _ = check(runtime, draft)
    assert error is None  # recorded, never a rejection round
    assert any("七杀、偏财" in w for w in runtime.session.state["output_warnings"])
    # Plain titles and advice pass; a term explained in the body is fine.
    draft["sections"][0]["title"] = "压力偏大，但能逼出成果"
    draft["sections"][0]["body"] = "偏财（额外的机会和外部资源）在这段时间更活跃。"
    draft["advice"] = ["多留意外部机会，但先确认自己接得住。"]
    assert check(runtime, draft)[0] is None
    assert not any("白话" in w for w in runtime.session.state["output_warnings"])


async def test_jargon_the_user_asked_about_may_be_named(runtime):
    outcome = await runtime.turn("用塔罗看看我近期的偏财运")
    assert outcome.status == "submit_reading"
    draft = copy.deepcopy(outcome.data["reading"])
    draft["advice"] = ["偏财运：多留意外部机会。"]
    assert check(runtime, draft)[0] is None
    assert not any("白话" in w for w in runtime.session.state["output_warnings"])


async def test_field_made_only_of_a_disclaimer_is_still_rejected(runtime):
    draft = await tarot_draft(runtime)
    draft["summary"] = "此结果仅供参考"
    error, _ = check(runtime, draft)
    assert error and "免责声明" in error


@pytest.mark.parametrize(
    "text,claim",
    [
        ("这个月一定会升职。", "一定会"),
        ("无论如何都一定会顺利。", "一定会"),
        ("你注定要经历这一关。", "注定"),
        ("这不代表事件必然发生。", None),
        ("结果不一定会如愿，但容易遇到转机。", None),
        ("并非注定如此，倾向于先难后易。", None),
        ("一定要保证睡眠。", None),
    ],
)
def test_certainty_words(text, claim):
    assert certainty_claim([text]) == claim


async def test_certainty_claim_in_section_is_rejected(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "这个月你一定会遇到贵人。"
    error, _ = check(runtime, draft)
    assert error and "倾向/容易" in error
    draft["sections"][0]["body"] = "这个月你容易遇到愿意帮忙的人。"
    assert check(runtime, draft)[0] is None


async def test_health_remark_gets_a_see_a_doctor_note(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "水被克时容易疲劳，注意肾与泌尿系统的养护，少熬夜。"
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.safety.flag and HEALTH_NOTE in reading.safety.note
    assert HEALTH_NOTE in render_reading(reading.model_dump(mode="json"))
    # Already advising a doctor: nothing is appended.
    draft["sections"][0]["body"] += "如有不适请及时就医。"
    error, reading = check(runtime, draft)
    assert error is None and HEALTH_NOTE not in reading.safety.note


async def test_five_element_advice_is_allowed(runtime):
    draft = await tarot_draft(runtime)
    draft["advice"] = ["喜用神倾向于水，可以多用黑色和深蓝色，桌上放一杯清水。"]
    assert check(runtime, draft)[0] is None


@pytest.mark.parametrize(
    "body",
    ["日柱甲子，这个月压力大。", "太阳在白羊座，行动力强。", "抽到了【愚人】正位。"],
)
async def test_fact_checks_cover_sections(runtime, body):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = body
    assert check(runtime, draft)[0]


async def test_section_refs_must_come_from_this_reading(runtime):
    draft = await tarot_draft(runtime)
    draft["sections"][0]["ref_ids"] = ["tarot:another-reading:pos1:the_star:upright"]
    error, _ = check(runtime, draft)
    assert error and "sections" in error


def test_specialist_report_is_repaired_and_carries_analysis():
    report = ReportInput.model_validate(
        dict(
            answer="倾向先稳住节奏。仅供参考。",
            analysis="辰戌相冲带来变动，印星可以化解压力。",
            points=[{"ref_id": "r1", "text": "流月戊戌。"}],
            confidence={"level": "high", "reason": ""},
        )
    )
    normalize_report(report, [{"reviewed": False}])
    assert report.answer == "倾向先稳住节奏。"
    assert report.confidence.level == "low" and "审核" in report.confidence.reason
    data = {"report": report.model_dump(mode="json") | {"system": "bazi", "label": "八字"}}
    data["report"]["status"] = "ok"
    assert project_report(data)["report"]["analysis"].startswith("辰戌相冲")


def test_reviewer_sees_the_sections():
    packet = packet_from_reading(
        output(sections=[{"title": "核心碰撞", "body": "辰戌相冲。", "ref_ids": []}]),
        "这个月怎么样",
        None,
    )
    assert "核心碰撞：辰戌相冲。" in packet["draft"]["body"]


async def test_demo_multi_agent_builds_sections_from_specialist_analysis(project):
    runtime = create_runtime(root=project, user_id="layers", seed=42, mode="multi")
    try:
        outcome = await runtime.turn("用塔罗看看近期状态")
        assert outcome.status == "submit_reading", outcome.text
        sections = outcome.data["reading"]["sections"]
        assert sections and sections[0]["title"] == "牌阵推演"
        assert "一、牌阵推演" in outcome.text
    finally:
        runtime.close()
