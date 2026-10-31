"""Drafts a live run refused for certainty wording are replayed through today's check, offline."""

import json

from scripts.replay_rejections import render, replay


def draft(body: str) -> dict:
    return dict(
        question_type="tarot",
        systems_used=["tarot"],
        summary="近期整体平稳，可以按计划推进。",
        sections=[{"title": "现在", "body": body, "ref_ids": ["R1"]}],
        evidence=[{"ref_id": "R1"}],
        confidence={"level": "low", "reason": ""},
        safety={"flag": True, "note": "这不构成投资建议。"},
    )


def refusal(arguments: dict, error: str, ok=False) -> str:
    return json.dumps(
        dict(
            event="tool_result",
            call=dict(id="c1", name="submit_reading", arguments=arguments),
            result=dict(ok=ok, error=error),
        ),
        ensure_ascii=False,
    )


def test_a_refused_draft_is_replayed_sentence_by_sentence():
    claim, sentences = replay(draft("它不代表行情必然上涨。可这只股票一定会涨。"))
    assert claim == "一定会"
    assert sentences == [("它不代表行情必然上涨。", False), ("可这只股票一定会涨。", True)]
    assert replay({"summary": 3}) == ("无法解析", [])


def test_a_run_counts_the_drafts_still_refused(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                refusal(draft("它不代表行情必然上涨。"), "不能使用“必然”这类确定性说法"),
                refusal(draft("这只股票一定会涨。"), "不能给出健康、投资或生死的确定性结论"),
                refusal(draft("免责声明"), "免责声明由应用统一添加，正文不要重复"),
                refusal(draft("近期平稳。"), "", ok=True),
            ]
        ),
        encoding="utf-8",
    )
    path = tmp_path / "Tarot-single" / "run" / "live.json"
    report = dict(results=[dict(id="tarot_investment_all_in", repeat=2, trace=str(trace))])
    text = render(path, report)
    assert "因确定性措辞被拒的草稿 2 份，按当前校验仍被拒 1 份" in text
    assert "- 放行：它不代表行情必然上涨。" in text
    assert "第3次：仍拒（一定会）" in text
    # A trace that is not on this machine has nothing to replay.
    missing = dict(results=[dict(id="x", trace=str(tmp_path / "missing.jsonl"))])
    text = render(path, missing)
    assert "被拒的草稿 0 份" in text and "缺少 trace 1 条，结果不完整" in text
