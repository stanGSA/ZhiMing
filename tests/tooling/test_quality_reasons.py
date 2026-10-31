"""The judge's reasons for failed answers are readable from a local live.json, offline."""

import json
import sys

from scripts.quality_reasons import failed, main, render, reports

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
