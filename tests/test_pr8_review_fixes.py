"""Regressions reported in the screenshot review of PR #8."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from common.output_policy import HEALTH_NOTE, care_advice, care_error, certainty_claim
from plugins.astro.validation import validate_output
from scripts.compare_layers import rejection_category, repository_metadata
from tests.test_pr7_review_fixes import STATE, astro_reading, check, section, tarot_draft


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
