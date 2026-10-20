import hashlib

import httpx
import pytest

from app import ROOT
from scripts.doctor import diagnose
from scripts.fetch_data import fetch_asset


def test_doctor_week1_required_checks(project):
    report = diagnose(project, data_root=ROOT / "data")
    assert report["ok"]
    assert all(c["required"] is False for c in report["checks"] if c["name"].endswith("API_KEY"))


def test_download_hash_and_cache(tmp_path):
    content = b"synthetic-data"
    asset = {
        "url": "https://example.test/data",
        "path": "ephe/test.bin",
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content))
    ) as client:
        assert fetch_asset(asset, tmp_path, client)["status"] == "downloaded"
        assert fetch_asset(asset, tmp_path, client)["status"] == "cached"


@pytest.mark.parametrize(
    "path,checksum",
    [("../escape.bin", "a" * 64), ("file.bin", "not-a-hash"), ("file.bin", "a" * 64)],
)
def test_bad_download_is_rejected(tmp_path, path, checksum):
    asset = {"url": "https://example.test/data", "path": path, "sha256": checksum}
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"wrong"))
    ) as client:
        with pytest.raises(ValueError):
            fetch_asset(asset, tmp_path, client)
    assert not (tmp_path / "file.bin").exists()
    assert not list(tmp_path.rglob("*.download"))


def test_compare_layers_metrics_and_report(tmp_path):
    import json

    from scripts.compare_layers import SCENARIOS, report, summarize, visible_chars

    layered = dict(
        summary="定调。",
        sections=[{"title": "核心碰撞", "body": "挑战与机遇。", "ref_ids": []}] * 2,
        advice=["精力聚焦：只推进一个目标。"],
        closing="收尾。",
        timeline=[],
        tensions=[],
        evidence=[{"ref_id": "r", "reading": "流月戊戌。"}],
    )
    old = dict(layered, sections=[], closing="")
    assert visible_chars(layered)["evidence_share"] < visible_chars(old)["evidence_share"]
    assert visible_chars(layered)["sections"] == 2
    # Every fixed question appears once; the 补水 follow-up chain is part of the set.
    assert sum(len(s["turns"]) for s in SCENARIOS) == 10
    assert any("补充一点“水”" in t for s in SCENARIOS for t in s["turns"])

    def row(output, turn=1, recomputed=()):
        return dict(
            scenario="bazi-month",
            kind="八字",
            turn=turn,
            status="submit_reading",
            reply_chars=100,
            submit_attempts=1,
            submit_rejections=[],
            report_rejections=[],
            reviews=[],
            warnings=[],
            recomputed=list(recomputed),
            **visible_chars(output),
        )

    for label, output in (("old", old), ("new", layered)):
        rows = [row(output), row(output, 2, ["draw_tarot"])]
        directory = tmp_path / label
        directory.mkdir()
        payload = dict(label=label, mode="single", provider="demo", model=None, rows=rows)
        (directory / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    assert summarize(rows)["followup_recompute"] == 1
    text = report([tmp_path / "old", tmp_path / "new"])
    assert "| layered_turns | 0 | 2 |" in text and "bazi-month-2 | new-single" in text


@pytest.mark.parametrize(
    "code,message,category",
    [
        ("review_revise", "审校要求补充现实条件", "review"),
        ("invalid_arguments", "参数不符合 schema：sections", "schema"),
        ("validation_failed", "行运日期与所述相位不符", "fact"),
        ("validation_failed", "不能使用一定会这类确定性说法", "expression"),
        ("validation_failed", "不能劝阻就医", "safety"),
        ("validation_failed", "尚未分类的校验提示", "other"),
        ("missing_dependency", "需要本次有效的chart_id", "other"),
    ],
)
def test_rejection_categories_do_not_count_every_retry_as_a_fact_error(code, message, category):
    from scripts.compare_layers import rejection_category

    assert rejection_category({"code": code, "error": message}) == category


def test_compare_counts_preserve_review_and_fact_errors_separately():
    from types import SimpleNamespace

    from scripts.compare_layers import summarize, turn_row

    events = [
        dict(
            event="tool_result",
            session_id="orchestrator",
            call={"name": "submit_reading"},
            result=dict(ok=False, code=code, error=message),
        )
        for code, message in (
            ("review_revise", "审校要求补充现实条件"),
            ("validation_failed", "行运日期与所述相位不符"),
        )
    ]
    row = turn_row(
        {"id": "fixture", "kind": "占星"},
        1,
        "测试",
        SimpleNamespace(data={}, text="", status="limit_reached"),
        events,
        SimpleNamespace(session=SimpleNamespace(id="orchestrator")),
        0,
    )
    summary = summarize([row])
    assert summary["rejections"] == 2
    assert summary["fact_rejections"] == 1
    assert summary["review_rejections"] == 1
    assert row["rejection_details"][0]["code"] == "review_revise"


def test_compare_counts_hedged_verdicts_caveats_and_basis_layers():
    from scripts.compare_layers import summarize

    def row(summary, text, titles):
        return dict(
            status="submit_reading",
            reply_chars=len(text),
            analysis_chars=0,
            evidence_share=None,
            sections=len(titles),
            section_titles=titles,
            submit_rejections=[],
            report_rejections=[],
            submit_attempts=1,
            reviews=[],
            recomputed=[],
            turn=1,
            output=dict(summary=summary),
            text=text,
        )

    rows = [
        row(
            "这个月有条件适合攻坚，前提是缩小范围。",
            "这个时刻不能当作现实事件时间；这张牌不能用来判定结果。",
            ["排盘基准：壬水日主", "核心碰撞：辰戌相冲"],
        ),
        row("这个月整体偏压力。前提是缩小范围。", "主要落在项目节奏上。", ["核心碰撞"]),
    ]
    summary = summarize(rows)
    assert summary["hedged_first"] == 1  # a premise after the first sentence is fine
    assert summary["avg_caveats"] == 1.0
    assert summary["basis_sections"] == 1
    assert summary["avg_lead_jargon"] == 1.0  # 日主 and 辰戌相冲 in the first reply's titles


def test_compare_counts_jargon_the_user_did_not_ask_about():
    from scripts.compare_layers import summarize

    def row(question, summary, titles, text):
        return dict(
            status="submit_reading",
            reply_chars=len(text),
            analysis_chars=0,
            evidence_share=None,
            sections=len(titles),
            section_titles=titles,
            submit_rejections=[],
            report_rejections=[],
            submit_attempts=1,
            reviews=[],
            recomputed=[],
            turn=1,
            question=question,
            output=dict(summary=summary, advice=["偏财运：多留意外部机会。"], closing=""),
            text=text,
        )

    rows = [
        row(
            "这个月怎么样？",
            "这个月整体偏压力，主要落在工作上。",
            ["当前大运：丁酉", "能量压制：财生七杀"],
            "丁酉大运，戊土为七杀；自己未来的方向更清楚。",
        ),
        row("我的偏财运怎么样？", "偏财运平稳。", ["压力偏大，但能逼出成果"], "偏财平稳。"),
    ]
    summary = summarize(rows)
    assert summary["avg_lead_jargon"] == 1.5  # 丁酉、七杀、偏财, then nothing the user did not ask
    assert summary["avg_jargon"] == 1.5  # 丁酉、七杀 in the first reply, 偏财 in the second
