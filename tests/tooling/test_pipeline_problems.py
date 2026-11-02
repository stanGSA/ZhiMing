"""scripts.pipeline_problems: each draft's problems, read back from the traces."""

import json

from scripts.pipeline_problems import drafts, kind, render, tally


def batch(tmp_path, rows):
    run = tmp_path / "Dream-pipeline" / "20261102T000000-test"
    run.mkdir(parents=True)
    path = run / "live.json"
    path.write_text(json.dumps({"results": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def trace(tmp_path, name, *problem_lists):
    path = tmp_path / f"{name}.jsonl"
    events = [{"event": "pipeline_stage", "stage": "compose"}] + [
        {"event": "pipeline_stage", "stage": "problems", "draft": i, "problems": problems}
        for i, problems in enumerate(problem_lists, 1)
    ]
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    return str(path)


def test_problems_are_read_per_draft_and_tallied_without_the_drafts_words(tmp_path):
    repaired = trace(tmp_path, "a", ["“地铁闸机”不在事实表里，只能解读事实表里的意象"])
    degraded = trace(
        tmp_path,
        "b",
        ["“考场”不在事实表里，只能解读事实表里的意象", "解梦只提供心理层面的线索"],
        ["“考场”不在事实表里，只能解读事实表里的意象"],
    )
    rows = [
        {"id": "a", "repeat": 0, "trace": repaired, "pipeline": {"problems": [1]}},
        {
            "id": "b",
            "repeat": 1,
            "trace": degraded,
            "pipeline": {"problems": [2, 1], "degraded": "keywords"},
        },
        {"id": "clean", "repeat": 0, "trace": trace(tmp_path, "c"), "pipeline": {"problems": []}},
        {"id": "agent", "repeat": 0, "trace": "", "pipeline": None},
    ]
    path = batch(tmp_path, rows)
    report = json.loads(path.read_text(encoding="utf-8"))
    assert drafts(rows[1]) == [
        ["“考场”不在事实表里，只能解读事实表里的意象", "解梦只提供心理层面的线索"],
        ["“考场”不在事实表里，只能解读事实表里的意象"],
    ]
    assert drafts(rows[2]) == []
    text = render(path, report)
    assert "b#2（降级：keywords）" in text and "第2稿：“考场”" in text
    assert "clean" not in text and "agent" not in text
    table = tally(path, report)
    assert "| 首稿 | “…”不在事实表里，只能解读事实表里的意象 | 2 |" in table
    assert "| 修复稿 | “…”不在事实表里，只能解读事实表里的意象 | 1 |" in table
    assert "地铁闸机" not in table and "考场" not in table


def test_a_trace_without_problem_texts_is_reported_not_counted(tmp_path):
    rows = [
        {"id": "old", "repeat": 0, "trace": trace(tmp_path, "old"), "pipeline": {"problems": [1]}}
    ]
    path = batch(tmp_path, rows)
    report = json.loads(path.read_text(encoding="utf-8"))
    assert drafts(rows[0]) is None
    assert "trace 中没有问题文字" in render(path, report)
    assert "1 条回答的 trace 中没有问题文字" in tally(path, report)


def test_kind_drops_quoted_words_and_numbers():
    assert (
        kind("当天流日的十神是正财，正文写成了「偏财」第3处")
        == "当天流日的十神是正财，正文写成了“…”第N处"
    )
