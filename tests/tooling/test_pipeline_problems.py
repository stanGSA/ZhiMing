"""scripts.pipeline_problems: each draft's problems, read back from the traces."""

import json

from scripts.pipeline_problems import drafts, kind, render, sources, tally


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
    assert "| 首稿 | 事实表外的梦境意象 | 2 |" in table
    assert "| 修复稿 | 事实表外的梦境意象 | 1 |" in table
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


def test_kind_reports_only_a_fixed_category_for_daily_facts():
    assert kind("当天流日的十神是正财，正文写成了「偏财」第3处") == "流日十神错误"


def test_tally_groups_name_errors_without_publishing_names(tmp_path):
    from plugins.name.validation import check_claims

    problems = []
    for name in ("王晓敏", "陈丽"):
        bound = {"full_name": name, "grids": {"人格": 25}, "shuli": {"人格": 25}}
        problems.append(check_claims("人格999", bound, {"name1": bound}))
    rows = [
        {
            "id": "names",
            "trace": trace(tmp_path, "names", problems),
            "pipeline": {"problems": [2]},
        }
    ]
    path = batch(tmp_path, rows)
    table = tally(path, {"results": rows})
    assert "| 首稿 | 姓名五格数值错误 | 2 |" in table
    assert all(name not in table for name in ("王晓敏", "陈丽", "999"))
    # The detailed local report still contains the evidence.
    assert all(name in render(path, {"results": rows}) for name in ("王晓敏", "陈丽"))


def test_unknown_problem_text_is_never_published():
    assert kind('未识别的错误：王晓敏，电话13812345678，"私人内容"') == "其他校验问题"


def test_render_shows_the_sentence_a_refused_word_stands_in(tmp_path):
    path = tmp_path / "t.jsonl"
    events = [
        {
            "stage": "problems",
            "draft": 1,
            "problems": ["“火”不是本次命中的意象，不能解读"],
            "text": "【摘要】这个梦反映你的不安。梦里像着火一样着急，往往反映压力。",
        }
    ]
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    rows = [{"id": "flood", "repeat": 2, "trace": str(path), "pipeline": {"problems": [1]}}]
    live = batch(tmp_path, rows)
    text = render(live, json.loads(live.read_text(encoding="utf-8")))
    assert "    - 候选原句：梦里像着火一样着急，往往反映压力。" in text
    # Published counts never carry the sentence.
    assert "着火" not in tally(live, json.loads(live.read_text(encoding="utf-8")))


def test_sources_without_a_recorded_draft_are_empty():
    assert sources("“火”不是本次命中的意象，不能解读", "") == []


def test_sources_include_later_mentions_after_an_allowed_abstention(tmp_path):
    problem = "“火”不是本次命中的意象，不能解读"
    draft = "火未收录，这次不作解读。火象征你近期的压力。"
    assert sources(problem, draft) == ["火未收录，这次不作解读。", "火象征你近期的压力。"]
    path = tmp_path / "mentions.jsonl"
    path.write_text(
        json.dumps({"stage": "problems", "problems": [problem], "text": draft}, ensure_ascii=False),
        encoding="utf-8",
    )
    rows = [{"id": "mentions", "trace": str(path), "pipeline": {"problems": [1]}}]
    live = batch(tmp_path, rows)
    report = {"results": rows}
    text = render(live, report)
    assert "候选原句：火象征你近期的压力。" in text
    assert "象征你近期" not in tally(live, report)


def test_sources_keep_draft_order_and_deduplicate_shared_sentences():
    problem = "“蛇”和“火”不在事实表里，只能解读事实表里的意象"
    assert sources(problem, "火未收录。蛇和火象征压力。蛇未收录。火未收录。") == [
        "火未收录。",
        "蛇和火象征压力。",
        "蛇未收录。",
    ]
