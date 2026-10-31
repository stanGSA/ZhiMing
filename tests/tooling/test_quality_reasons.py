"""The judge's reasons for failed answers are readable from a local live.json, offline."""

import json
import sys

from scripts.quality_reasons import (
    TABLE_HEAD,
    counts,
    counts_row,
    fabrication_kind,
    failed,
    main,
    render,
    reports,
)

PASSED = dict(
    direct_answer=True, time_consistent=True, supported_conclusion=True, no_fabricated_facts=True
)


def report_rows():
    return [
        dict(id="kept", repeat=0, quality_review=PASSED, answer="好的回答"),
        dict(
            id="tarot_followup_second_card",
            repeat=2,
            quality_review={
                **PASSED,
                "no_fabricated_facts": False,
                "reasons": ["把“同事支持你”写成了用户已知的经历"],
            },
            structured={"summary": "第二张牌说的是你现在的状态。"},
            answer="第一行\n第二行",
            pipeline={"kind": "followup", "repairs": 0, "degraded": None},
        ),
        dict(id="unscored", repeat=0, quality_review={"scored": False, "error_type": "ValueError"}),
    ]


def test_only_failed_dimensions_are_listed():
    rows = report_rows()
    assert [failed(row) for row in rows] == [[], ["no_fabricated_facts"], ["未评分"]]


def test_the_latest_report_of_a_batch_directory_is_read(tmp_path):
    for run in ("20261030T1", "20261030T2"):
        (tmp_path / "Tarot-pipeline" / run).mkdir(parents=True)
        (tmp_path / "Tarot-pipeline" / run / "live.json").write_text("{}", encoding="utf-8")
    assert reports([tmp_path / "Tarot-pipeline"]) == [
        tmp_path / "Tarot-pipeline" / "20261030T2" / "live.json"
    ]


def test_reasons_and_answers_are_rendered(tmp_path, monkeypatch, capsys):
    path = tmp_path / "Tarot-pipeline" / "run" / "live.json"
    path.parent.mkdir(parents=True)
    report = dict(mode="pipeline", judge_model="judge", results=report_rows())
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    text = render(path, report, answers=False)
    assert "质量未通过 2/3" in text
    assert "### tarot_followup_second_card · 第3次" in text
    assert "把“同事支持你”写成了用户已知的经历" in text and "流水线：followup" in text
    assert "第一行" not in text and "kept" not in text
    monkeypatch.setattr(sys, "argv", ["quality_reasons", str(path.parent.parent), "--answers"])
    main()
    assert "> 第一行\n> 第二行" in capsys.readouterr().out


def fabricated(reason, status="submit_reading"):
    return dict(
        id="t",
        repeat=0,
        status=status,
        quality_review={**PASSED, "no_fabricated_facts": False, "reasons": [reason]},
    )


def test_fabrication_failures_are_sorted_by_the_judges_reason():
    # 根因整改实施计划 §5: verifiable facts (0 expected) apart from narrative (prompt only).
    cases = {
        "no_fabricated_facts：正文说现在位是【力量】正位，本次实际是逆位": "事实类",
        "no_fabricated_facts：解释了未计算的宫位": "事实类",
        "no_fabricated_facts：把“同事支持你”写成了用户已知的经历": "叙述类",
        "no_fabricated_facts：描述了事实表没有的牌面画面和人物形象": "叙述类",
        "no_fabricated_facts：把逆位的含义写成了用户的经历": "未分类",
        "no_fabricated_facts：内容不准确": "未分类",
    }
    for reason, kind in cases.items():
        assert fabrication_kind(fabricated(reason)) == kind, reason
    # Reasons for other dimensions do not decide the kind.
    row = fabricated("no_fabricated_facts：预言了必然发生的具体事件")
    row["quality_review"]["reasons"].insert(0, "direct_answer：首句没有回答正逆位的问题")
    assert fabrication_kind(row) == "叙述类"
    assert fabrication_kind(dict(quality_review=PASSED)) is None


def test_the_counts_are_over_submitted_answers():
    report = dict(
        results=[
            fabricated("no_fabricated_facts：写成了用户的经历"),
            fabricated("no_fabricated_facts：牌名与本次不符"),
            fabricated("no_fabricated_facts：写成了用户的经历", status="retry_limit"),
            dict(id="ok", status="submit_reading", quality_review=PASSED),
        ]
    )
    assert counts(report) == {"submitted": 3, "事实类": 1, "叙述类": 1, "未分类": 0}
    assert (
        counts_row("Tarot-pipeline/run", report)
        == "| Tarot-pipeline/run | 3 | 2 | 1 | 1 | 0 | 33.3% |"
    )


def test_the_counts_alone_carry_no_question_reason_or_answer(tmp_path, monkeypatch, capsys):
    path = tmp_path / "Tarot-pipeline" / "run" / "live.json"
    path.parent.mkdir(parents=True)
    row = {**fabricated("no_fabricated_facts：写成了用户的经历"), "answer": "回答原文"}
    path.write_text(json.dumps(dict(results=[row]), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["quality_reasons", str(path), "--counts-only"])
    main()
    out = capsys.readouterr().out
    assert out.splitlines() == [*TABLE_HEAD, "| Tarot-pipeline/run | 1 | 1 | 0 | 1 | 0 | 100.0% |"]
    assert "经历" not in out and "回答原文" not in out
