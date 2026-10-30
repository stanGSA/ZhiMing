"""Regressions reported in the screenshot review of PR #8."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from common.output_policy import HEALTH_NOTE, care_advice, care_error, certainty_claim
from common.validation import risk_note
from plugins.astro.validation import validate_output
from scripts.compare_layers import rejection_category, repository_metadata
from tests.validation.test_layered_fact_binding import (
    STATE,
    astro_reading,
    check,
    section,
    tarot_draft,
)


@pytest.mark.parametrize(
    "text",
    [
        "这不代表过去的努力白费你下个月一定会升职",
        "我不认为这很难你一定会成功",
        "不说别的你一定会成功",
        "我不觉得这有问题你必然成功",
        "并不意味着努力白费但你一定会成功",
    ],
)
async def test_unrelated_negative_predicate_cannot_cancel_certainty(runtime, text):
    assert certainty_claim([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = text
    error, _ = check(runtime, draft)
    assert error and "确定性说法" in error


@pytest.mark.parametrize(
    "text",
    [
        "我不认为你一定会失败。",
        "我不觉得你下个月必然失败。",
        "这不代表事件必然发生。",
        "并不意味着你一定会失败。",
        "并非你这个月一定会失败。",
        "不要以为你一定能成功。",
    ],
)
def test_direct_negative_complements_remain_allowed(text):
    assert certainty_claim([text]) is None


# Drafts the tarot tuning set refused (PR #37 review: 10 refused drafts replayed from the raw
# traces, all of these forms). The writers follow the card meanings' "不代表事件必然发生" and
# say it of what the question is about.
REFUSED_DRAFTS = [
    "它不代表行情必然上涨。",
    "它不预言你一定会亏钱。",
    "这不是说留下就一定会变差。",
    "这不代表某件事必然发生。",
    "不代表具体事件必然发生。",
    # The one left after 1fe9499 (re-check: 1 of the 10 still refused).
    "它不会告诉你今天一定会发生什么，只提供一个观看自己的角度。",
]


@pytest.mark.parametrize(
    "text",
    [
        *REFUSED_DRAFTS,
        "这不代表行情对你必然有利。",
        "这不代表下个月的面试结果一定会好。",
        "不代表你们这段关系必然结束。",
        "这不代表这只股票一定会涨。",
        "牌面不代表股价必然上涨。",
        "这张牌并不代表投资必然亏损。",
        "不代表全部投入必然亏损。",
        "这不代表你们的关系一定会好转。",
        "不代表关系必然走向破裂。",
        "不代表考试一定会失利。",
        "不意味着跳槽必然成功。",
        "并不是说这只股票一定会涨。",
        "这不是一种必然。",
        "并没有什么是必然的。",
        "没有哪种结果是注定的。",
        "不必把这理解为必然。",
    ],
)
def test_a_negated_claim_about_the_question_s_subject_is_allowed(text):
    assert certainty_claim([text]) is None


@pytest.mark.parametrize(
    "text",
    [
        "这只股票一定会涨。",
        "你们的关系必然好转。",
        "这不代表关系必然好转你们一定会分手。",
        "不代表投资失败你一定会赚钱。",
        "这不是一种选择，你注定要走这条路。",
        "没有什么好担心的你一定会成功。",
        "没有问题，你一定会成功。",
        "这不是坏事你一定会成功。",
        "不代表行情不好你一定会亏。",
        "它不预言失败你必然成功。",
        # Re-check of 1fe9499: a noun, not a pronoun, starts the second clause.
        "这不是坏事这只股票一定会涨。",
        "这不是坏事股价一定会涨。",
        "并非坏事股价一定会涨。",
        "这不是问题结果一定会好。",
        "这不代表失败这只股票一定会涨。",
        "这不代表坏事股价一定会涨。",
        "这不代表亏损行情一定会涨。",
        "它不预言坏事那只股票一定会涨。",
        "它不会告诉你答案你一定会成功。",
        "它不会告诉你今天会怎样，但你一定会成功。",
        "不会告诉你结果这只股票一定会涨。",
    ],
)
async def test_a_subject_or_noun_form_does_not_hide_a_separate_claim(runtime, text):
    assert certainty_claim([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = text
    error, _ = check(runtime, draft)
    assert error and "确定性说法" in error


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
def test_negated_sign_inference_is_separate_from_a_position_claim(field):
    def check_position(text):
        reading = astro_reading()
        if field == "sections":
            reading.sections = astro_reading(sections=[section(text)]).sections
        elif field == "summary":
            reading.summary = text
        else:
            reading.evidence[0].reading = text
        return validate_output(reading, STATE)

    inference = "并不是狮子座的人都外向"
    assert check_position(f"太阳狮子座，{inference}。") is None
    assert check_position("太阳狮子座，并非白羊座就一定内向。") is None
    # Both explicit and denied position claims must still bind to the computed Sun in Leo.
    for text in (
        f"太阳白羊座，{inference}。",
        f"太阳不是狮子座，{inference}。",
        "太阳狮子座，并非狮子座就一定外向，也不在狮子座。",
        "太阳狮子座，并不是第4宫就意味着失败，但不在第4宫。",
    ):
        assert check_position(text)


@pytest.mark.parametrize(
    "text",
    [
        "这不代表你有病不需要就医",
        "这不说明你有病不必就医",
        "这不意味着身体有问题无需就医",
        "不要以为身体很好不需要就医",
        "如果身体不适也不应就医",
        "如果身体不适不要就医",
        "身体不适不能及时就医",
    ],
)
async def test_unrelated_negation_does_not_become_care_advice(runtime, text):
    assert care_advice([text])[0] is False
    assert care_error([text])
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "身体不适。" + text
    error, reading = check(runtime, draft)
    assert error and "不能劝阻就医" in error
    assert HEALTH_NOTE in reading.safety.note


@pytest.mark.parametrize(
    "text",
    [
        "如果不能及时就医，症状可能拖延加重",
        "不能及时就医时，先联系家人",
        "若你不能马上去医院，请联系家人",
        "万一不能及时就诊，先向家人求助",
        "一旦不可及时就医，应联系家人",
        "不能及时就医的话，先联系家人",
    ],
)
async def test_conditional_inability_is_neither_discouragement_nor_advice(runtime, text):
    assert care_advice([text]) == (False, None)
    draft = await tarot_draft(runtime)
    draft["sections"][0]["body"] = "身体不适。" + text
    error, reading = check(runtime, draft)
    assert error is None
    assert reading.safety.flag and HEALTH_NOTE in reading.safety.note


def test_conditional_inability_does_not_hide_a_later_prohibition():
    assert care_error(["如果不能及时就医，也不要寻求医疗帮助。"])
    assert care_advice(["不能及时就医时，先联系家人；如有不适请尽快就医。"])[0]


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
@pytest.mark.parametrize("peak", ["达到高峰", "达到峰值", "达到顶峰", "达峰"])
def test_peak_dates_are_bound_to_the_transit(field, peak):
    for day, valid in ((5, True), (12, False)):
        text = f"行运木星拱本命太阳，在11月{day}日{peak}。"
        reading = astro_reading()
        if field == "sections":
            reading.sections = astro_reading(sections=[section(text)]).sections
        elif field == "evidence":
            reading.evidence[0].reading = text
        else:
            reading.summary = text
        assert (validate_output(reading, STATE) is None) == valid


@pytest.mark.parametrize("field", ["sections", "summary", "evidence"])
def test_influence_onset_is_not_an_exact_date_claim(field):
    text = "10月8日，行运木星拱本命太阳的影响开始显现。"
    reading = astro_reading(sections=[section(text)] if field == "sections" else [])
    if field == "summary":
        reading.summary = text
    if field == "evidence":
        reading.evidence[0].reading = text
    assert validate_output(reading, STATE) is None
    # Relaxing onset dates must never relax the relation or an explicit peak date.
    for wrong in (text.replace("拱", "刑"), text.replace("开始显现", "开始显现并达到高峰")):
        if field == "sections":
            reading.sections[0].body = wrong
        elif field == "summary":
            reading.summary = wrong
        else:
            reading.evidence[0].reading = wrong
        assert validate_output(reading, STATE)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("时间范围问题需要相应行运或流期计算，不能只用原局", "fact"),
        ("systems_used 必须恰好等于本次调用的体系，不能声称使用未调用的体系", "fact"),
        ("必须先调用确定性计算工具", "fact"),
        ("西方占星专家未完成，confidence.reason 须说明缺少体系及原因", "disclosure"),
        ("正文不能包含内部状态、审核或存储错误信息", "expression"),
        ("confidence.reason 有未知问题", "other"),
    ],
)
def test_calculation_and_disclosure_categories(message, expected):
    assert rejection_category(dict(code="validation_failed", error=message)) == expected


@pytest.mark.parametrize(
    "failure", [FileNotFoundError(), subprocess.CalledProcessError(128, "git")]
)
async def test_archive_comparison_still_writes_results(project, monkeypatch, failure):
    from app import create_runtime
    from scripts import compare_layers

    def no_git(*args, **kwargs):
        raise failure

    monkeypatch.setattr(compare_layers.subprocess, "check_output", no_git)
    monkeypatch.setattr(compare_layers, "load_code", lambda root: (create_runtime, None))
    monkeypatch.setattr(compare_layers, "workdir", lambda *args: project)
    monkeypatch.setattr(
        compare_layers, "SCENARIOS", [{"id": "tarot", "kind": "塔罗", "turns": ["看看近期状态"]}]
    )
    out = await compare_layers.run(
        SimpleNamespace(
            root=project,
            out=project / "comparison",
            data_from=None,
            label="archive",
            mode="single",
            provider="demo",
            model=None,
            orchestrator_thinking=None,
        )
    )
    data = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert data["revision"] is None and data["dirty"] is None
    assert data["revision_error"] == type(failure).__name__
    assert data["rows"][0]["status"] == "submit_reading"
    assert "代码版本=未知" in compare_layers.report([out])


def test_git_metadata_preserves_revision_and_dirty_state(tmp_path, monkeypatch):
    results = iter(["abc123\n", b" M changed.py\n"])
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: next(results))
    assert repository_metadata(tmp_path) == dict(revision="abc123", dirty=True, revision_error=None)


def test_saved_diagnostics_are_reclassified_without_rewriting_them():
    from scripts.compare_layers import summarize

    details = [
        dict(
            code="validation_failed", error="时间范围问题需要相应行运或流期计算", category="other"
        ),
        dict(
            code="validation_failed",
            error="西方占星专家未完成，confidence.reason 须说明原因",
            category="expression",
        ),
    ]
    row = dict(
        status="ask_user",
        submit_rejections=[d["error"] for d in details],
        report_rejections=[],
        rejection_details=details,
        submit_attempts=2,
        reviews=[],
        turn=1,
    )
    summary = summarize([row])
    assert summary["fact_rejections"] == 1
    assert summary["disclosure_rejections"] == 1
    assert summary["expression_rejections"] == summary["other_rejections"] == 0
    assert [d["category"] for d in details] == ["other", "expression"]


INVESTMENT = "只用塔罗三张牌帮我反思：是否应该把积蓄全部买入一只股票？"


async def high_risk_draft(runtime, text):
    draft = await tarot_draft(runtime)
    runtime.session.state["question"] = INVESTMENT
    draft["sections"][0]["body"] = text
    draft["safety"] = {"flag": True, "note": risk_note(INVESTMENT)}
    return draft


@pytest.mark.parametrize("text", ["下个月不一定会顺利。", "这不代表这只股票一定会涨。"])
async def test_a_negated_claim_passes_the_high_risk_check(runtime, text):
    # The high-risk check searched the raw JSON for 一定会, so the hedge itself was refused as
    # "不能给出健康、投资或生死的确定性结论", which the pipeline takes for a safety failure.
    error, _ = check(runtime, await high_risk_draft(runtime, text))
    assert error is None


async def test_the_high_risk_check_still_refuses_a_claim_the_policy_judge_would_weigh(runtime):
    draft = await high_risk_draft(runtime, "现在全部买入，这只股票一定会涨。")
    runtime.session.policy_judge = object()  # the two-level mode: wording goes to a model
    error, _ = check(runtime, draft)
    assert error == "不能给出健康、投资或生死的确定性结论"
