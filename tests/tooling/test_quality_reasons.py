"""The judge's reasons for failed answers are readable from a local live.json, offline."""

import json
import sys

import pytest

from scripts.quality_reasons import (
    TABLE_HEAD,
    counts,
    counts_row,
    fabrication_kind,
    failed,
    load_reviewed,
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


def fabricated(*reasons, status="submit_reading", repeat=0, id="t"):
    return dict(
        id=id,
        repeat=repeat,
        status=status,
        quality_review={**PASSED, "no_fabricated_facts": False, "reasons": list(reasons)},
    )


def test_fabrication_failures_are_sorted_by_the_judges_reason():
    # 根因整改实施计划 §5: verifiable facts (0 expected) apart from narrative (prompt only).
    cases = {
        "no_fabricated_facts：正文说现在位是【力量】正位，本次实际是逆位": "事实类",
        "no_fabricated_facts：解释了未计算的宫位": "事实类",
        "no_fabricated_facts：把“同事支持你”写成了用户已知的经历": "叙述类",
        "no_fabricated_facts：描述了事实表没有的牌面画面和人物形象": "叙述类",
        "no_fabricated_facts：把逆位的含义写成了用户的经历": "待复核",
        "no_fabricated_facts：内容不准确": "待复核",
        "no_fabricated_facts：牌名与事实不一致": "事实类",
        # Second review of PR #38: a list called right as a whole, then the user's state.
        "no_fabricated_facts：牌名和正逆位均正确，但把你最近一直失眠写成已知事实。": "叙述类",
        "no_fabricated_facts：牌名、正逆位与事实一致，但你最近一直失眠没有资料支持。": "叙述类",
    }
    for reason, kind in cases.items():
        assert fabrication_kind(fabricated(reason)) == kind, reason
    assert fabrication_kind(dict(quality_review=PASSED)) is None


def test_only_the_reason_labelled_no_fabricated_facts_decides():
    # PR #38 review: another dimension's "未编造宫位" made a narrative failure count as a fact.
    row = fabricated(
        "no_fabricated_facts：用户已经买了房，没有原始资料支持。",
        "supported_conclusion：未编造宫位，结论仍缺乏支持。",
    )
    assert fabrication_kind(row) == "叙述类"
    row = fabricated(
        "direct_answer：首句没有回答正逆位的问题", "no_fabricated_facts：预言了具体事件"
    )
    assert fabrication_kind(row) == "叙述类"
    # Without a labelled reason nothing is decided by code.
    assert fabrication_kind(fabricated("用户已经买了房，牌名也写错了")) == "待复核"
    assert fabrication_kind(fabricated("把场景写成了用户的经历")) == "待复核"


def test_a_fact_the_reason_rules_out_is_no_evidence():
    # PR #38 review: "没有新增牌名" counted as a card-name error.
    assert (
        fabrication_kind(fabricated("no_fabricated_facts：没有新增牌名，正文断言用户长期失眠。"))
        == "叙述类"
    )
    assert (
        fabrication_kind(fabricated("no_fabricated_facts：牌名无误，但把场景写成了用户经历"))
        == "叙述类"
    )
    assert (
        fabrication_kind(fabricated("no_fabricated_facts：未编造宫位，但其他内容缺乏依据"))
        == "待复核"
    )


def unscored(review, status="submit_reading"):
    return dict(id="u", repeat=0, status=status, quality_review=review)


def test_unscored_answers_are_counted_apart_and_never_read_as_zero():
    # PR #38 review: 24 timed-out reviews were printed as 0 fabrication, 0.0%.
    timed_out = [unscored({"scored": False, "error_type": "TimeoutError"}) for _ in range(24)]
    assert counts(dict(results=timed_out))["unscored"] == 24
    assert counts_row("B", dict(results=timed_out)) == (
        "| B | 24 | 0 | 24 | 0 | 0 | 0 | 0 | 0/0/0 | 待定（未评分） | 不完整：未评分 24 |"
    )
    no_review = [dict(id="h", repeat=0, status="submit_reading") for _ in range(8)]
    assert counts_row("B", dict(results=no_review)).endswith(
        "| 待定（未评分） | 不完整：未评分 8 |"
    )
    partial = dict(id="p", status="submit_reading", quality_review={"no_fabricated_facts": True})
    report = dict(
        results=[fabricated("no_fabricated_facts：写成了用户的经历"), partial, unscored(PASSED)]
    )
    numbers = counts(report)
    assert (numbers["scored"], numbers["unscored"], numbers["undecided"]) == (2, 1, 1)
    # Nothing decided yet out of three submitted; the open two could both be narrative.
    assert counts_row("B", report).endswith("| 0.0%–66.7% | 不完整：待人工判定 1、未评分 1 |")


def test_the_counts_are_over_submitted_answers():
    report = dict(
        results=[
            fabricated("no_fabricated_facts：写成了用户的经历", id="a"),
            fabricated("no_fabricated_facts：牌名与本次不符", id="b"),
            fabricated("no_fabricated_facts：写成了用户的经历", status="retry_limit"),
            dict(id="ok", status="submit_reading", quality_review=PASSED),
        ]
    )
    assert counts(report) == {
        "submitted": 3,
        "scored": 3,
        "unscored": 0,
        "failures": 2,
        "fact": 0,
        "narrative": 0,
        "undecided": 2,
        "suggested": {"事实类": 1, "叙述类": 1, "待复核": 0},
    }
    reviewed = {"a#1": ["叙述类"], "b#1": ["事实类"]}
    assert counts_row("R", report, reviewed) == (
        "| R | 3 | 3 | 0 | 2 | 1 | 1 | 0 | 0/0/0 | 33.3% | 完整 |"
    )


def test_counts_are_complete_only_when_the_owner_decided_every_failure(tmp_path):
    # Second review of PR #38: a suggestion counted as a decision and printed "完整".
    report = dict(
        results=[
            fabricated("no_fabricated_facts：牌名和正逆位都写错了", id="x"),
            fabricated("no_fabricated_facts：内容不准确", id="a", repeat=1),
            fabricated("no_fabricated_facts：把逆位的含义写成了用户的经历", id="b", repeat=2),
            dict(id="ok", status="submit_reading", quality_review=PASSED),
        ]
    )
    assert counts_row("B", report) == (
        "| B | 4 | 4 | 0 | 3 | 0 | 0 | 3 | 1/0/2 | 0.0%–75.0% | 不完整：待人工判定 3 |"
    )
    decisions = tmp_path / "reviewed.yaml"
    decisions.write_text("B:\n  a#2: [叙述类]\n  b#3: [事实类, 叙述类]\n", encoding="utf-8")
    partly = load_reviewed(decisions)["B"]
    assert counts_row("B", report, partly).endswith("| 50.0%–75.0% | 不完整：待人工判定 1 |")
    # An answer may be both kinds and is still one failure.
    decisions.write_text(
        "B:\n  x#1: [事实类]\n  a#2: [叙述类]\n  b#3: [事实类, 叙述类]\n", encoding="utf-8"
    )
    reviewed = load_reviewed(decisions)["B"]
    numbers = counts(report, reviewed)
    assert (numbers["failures"], numbers["fact"], numbers["narrative"]) == (3, 2, 2)
    assert counts_row("B", report, reviewed) == (
        "| B | 4 | 4 | 0 | 3 | 2 | 2 | 0 | 0/0/0 | 50.0% | 完整 |"
    )


@pytest.mark.parametrize("decision", ["[]", "[记错了]", "叙述类", "[叙述类, 两类都不是]"])
def test_a_decision_names_at_least_one_kind(tmp_path, decision):
    # Second review of PR #38: an empty list closed a failure without counting it anywhere.
    decisions = tmp_path / "reviewed.yaml"
    decisions.write_text(f"B:\n  a#1: {decision}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_reviewed(decisions)


def test_the_counts_alone_carry_no_question_reason_or_answer(tmp_path, monkeypatch, capsys):
    path = tmp_path / "Tarot-pipeline" / "run" / "live.json"
    path.parent.mkdir(parents=True)
    row = {**fabricated("no_fabricated_facts：写成了用户的经历"), "answer": "回答原文"}
    path.write_text(json.dumps(dict(results=[row]), ensure_ascii=False), encoding="utf-8")
    decisions = tmp_path / "reviewed.json"
    decisions.write_text(json.dumps({"Tarot-pipeline": {"t#1": ["叙述类"]}}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["quality_reasons", str(path), "--counts-only"])
    main()
    out = capsys.readouterr().out
    assert out.splitlines() == [
        *TABLE_HEAD,
        "| Tarot-pipeline/run | 1 | 1 | 0 | 1 | 0 | 0 | 1 | 0/1/0 | 0.0%–100.0% | "
        "不完整：待人工判定 1 |",
    ]
    assert "经历" not in out and "回答原文" not in out
    argv = ["quality_reasons", str(path), "--counts-only", "--reviewed", str(decisions)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    assert capsys.readouterr().out.splitlines()[-1] == (
        "| Tarot-pipeline/run | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0/0/0 | 100.0% | 完整 |"
    )
