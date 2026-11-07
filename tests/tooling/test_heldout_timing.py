"""P3.0: direct_timing_answer accepts both word orders, and nothing more."""

import json

import pytest

from evals.heldout import timing_answer, timing_answer_legacy
from scripts.heldout_rescore import markdown, rescore

# The stance after 跳槽: failed before P3.0, a direct answer all the same.
AFTER = [
    "下个月跳槽不太适合，先把手头项目收尾更稳",
    "下个月跳槽整体偏适合，前提是简历准备好",
    "下个月跳槽适合",
    "下个月跳槽不宜",
    "下个月跳槽可以，但要先谈好待遇",
    "下个月跳槽不建议，牌面更支持先积累",
    "下个月的跳槽时机适合，节奏偏快",
    # Degree words inside the stance.
    "下个月跳槽完全不适合，牌面提示条件未成熟",
    "下个月跳槽根本不适合，现在走时机太早",
    # A double negation still takes a side.
    "下个月跳槽不是不可以，只是要先确认去处",
    "下个月跳槽并非不适合，关键在准备",
    # A stance first, then a turn: the first clause has answered.
    "下个月跳槽不适合，但可以先投简历看看机会",
    "下个月跳槽适合的，不过要留意合同期限",
]

# Still not a direct answer about next month's job change.
STILL_REFUSED = [
    # The stance governs another thing in the same sentence.
    "下个月跳槽前更适合先把作品集准备好",
    "下个月跳槽不如换部门适合",
    "下个月跳槽比留下更适合",
    "下个月跳槽之后适合多观察团队",
    "下个月跳槽，换城市发展更适合",
    "下个月跳槽还是先调岗适合",
    # The stance is about the time around the change.
    "下个月跳槽以后可以慢慢适应",
    # An outer hedge or negation over the whole claim.
    "很难说下个月跳槽适合",
    "不能说下个月跳槽适合，要看准备",
    "不可能说下个月跳槽一定可以",
    "不是说下个月跳槽适合，而是要看机会",
    # Undecided.
    "下个月跳槽不一定适合",
    "下个月跳槽未必可以",
    "下个月跳槽要看情况适合与否",
    # A question back, or no stance at all.
    "下个月跳槽适合吗",
    "下个月跳槽的牌面是宝剑三",
    "下个月跳槽这件事需要你自己判断",
    # The stance is about another time or another verb.
    "这个月跳槽适合，下个月再看",
    "下个月跳槽流程很难执行",
    # The answer comes only after the first sentence.
    "下个月的牌面比较复杂。整体来看下个月跳槽适合",
]


@pytest.mark.parametrize("sentence", AFTER)
def test_stance_after_job_change_is_a_direct_answer(sentence):
    assert timing_answer(sentence)
    assert not timing_answer_legacy(sentence)


@pytest.mark.parametrize("sentence", STILL_REFUSED)
def test_still_not_a_direct_answer(sentence):
    assert not timing_answer(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "下个月适合跳槽，但要先准备好简历",
        "不建议下个月跳槽，先积累半年",
        "下个月整体可以考虑跳槽",
        # The old reading's own acceptances are kept, hedges included: only the order changed.
        "很难说下个月适合跳槽",
    ],
)
def test_legacy_acceptances_are_kept(sentence):
    assert timing_answer_legacy(sentence)
    assert timing_answer(sentence)


def report(tmp_path, summary, **checks):
    row = {
        "name": "跳槽时机正面回答",
        "status": "submit_reading",
        "structured_output": {"summary": summary},
        "checks": {
            "zero_tool_errors": False,
            "valid": True,
            "direct_timing_answer": timing_answer_legacy(summary),
            **checks,
        },
        "pass": False,
    }
    other = {"name": "其他", "checks": {"ok": True}, "pass": True}
    path = tmp_path / "live.json"
    path.write_text(json.dumps({"results": [row, other]}, ensure_ascii=False), encoding="utf-8")
    return path


def test_rescore_reports_both_readings(tmp_path):
    result = rescore(report(tmp_path, "下个月跳槽不太适合，先稳住。其余略。"))
    assert (result["legacy_passed"], result["new_passed"], result["cases"]) == (1, 2, 2)
    timing = result["timing"][0]
    assert (timing["legacy"], timing["new"], timing["recorded"]) == (False, True, False)
    assert timing["sentence"] == "下个月跳槽不太适合，先稳住"
    text = markdown([result])
    assert "| 1/2 | 2/2 | 失败 / 通过 |" in text


def test_rescore_changes_only_the_timing_check(tmp_path):
    # Another failing check keeps the row failed under both readings.
    result = rescore(report(tmp_path, "下个月跳槽不太适合。", valid=False))
    assert (result["legacy_passed"], result["new_passed"]) == (1, 1)
