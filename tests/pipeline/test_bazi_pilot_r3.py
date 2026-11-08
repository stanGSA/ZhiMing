"""Bazi pilot r2 findings (docs/verification/p3/bazi-pilot-r2/review.md), fixed in r3.

Investment #1: a section of 396 characters as written held 24 numbers and expanded to about
1400; the submission refused it twice with a schema error the writer could not act on, and the
reading code wrote instead attached the knowledge base's first keywords (甲己合) to a 丙辛 and a
丁壬 relation and cut its last section mid-word.
"""

import re

from pipeline.bazi import Bazi, relevant_keywords
from tests.pipeline.test_runner_bazi import make, planned  # noqa: F401
from tests.pipeline.test_runner_bazi import written as bazi_written

INVESTMENT = "从八字看，明年适合把积蓄都投进股市吗？"
STEMS, BRANCHES = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥"
HE = ["天干合", "天干五合", "甲己合", "乙庚合", "丙辛合", "丁壬合", "戊癸合", "相合", "合化"]


def broken(messages) -> str:
    return "这不是标记文本"


def test_pair_keywords_follow_the_fact():
    """The three r2 sentences, with the keywords their knowledge entry lists."""
    for text, pair in (
        ("流年丙午与本命时柱辛亥天干合（1月1日至2月3日）", "丙辛合"),
        ("流月辛丑与本命年柱丙寅天干合（1月5日至2月3日）", "丙辛合"),
        ("流月壬寅与本命日柱丁亥天干合（2月4日至3月5日）", "丁壬合"),
    ):
        kept = relevant_keywords(HE, text)
        assert kept[:3] == ["天干合", "天干五合", pair], text
        assert not {"甲己合", "乙庚合", "戊癸合"} & set(kept), text
    # A three-branch group is kept only for that group.
    group = ["三合", "申子辰", "亥卯未", "联结"]
    assert relevant_keywords(group, "流月甲申地支申与原局地支构成申子辰三合") == [
        "三合",
        "申子辰",
        "联结",
    ]
    # Single stems or branches name the fact's own character (日柱丁亥地支亥: “亥”, “藏干”).
    assert relevant_keywords(["亥", "地支", "水"], "日柱丁亥地支亥") == ["亥", "地支", "水"]


def test_a_body_too_long_once_expanded_is_said_before_submission():
    args = {"summary": "整体平稳。", "sections": [{"title": "全年", "body": "流月" * 700}]}
    (problem,) = Bazi.length_problems(args)
    assert "1400字" in problem and "拆成两层" in problem
    args["sections"][0]["body"] = "流月" * 600
    assert Bazi.length_problems(args) == []


async def test_a_too_long_section_is_repaired_not_degraded(make):  # noqa: F811
    def crowded(messages):
        aliases = re.findall(r"^(R\d+)｜", messages[1]["content"], re.M)
        listed = "，".join("{{" + alias + "}}" for alias in aliases)
        draft = bazi_written(messages)
        return draft.replace(
            "提示你把精力放在长期目标上。", f"{listed}都提示你把精力放在长期目标上。"
        )

    runtime, composer, events = make(crowded, bazi_written)
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert any("拆成两层" in p for p in info["problems"][0])
    # Caught before submission: no schema error reached submit_reading.
    assert planned(events).count("submit_reading") == 1


async def test_the_degraded_reading_keeps_whole_sentences_and_its_own_pairs(make):  # noqa: F811
    runtime, composer, events = make(broken, broken)
    outcome = await runtime.turn(INVESTMENT)
    assert outcome.status == "submit_reading", outcome.text
    reading = outcome.data["reading"]
    assert outcome.data["pipeline"]["degraded"] == "keywords"
    assert reading["summary"].startswith("不能依据八字作这类重大现实决定。")
    pairs = 0
    for section in reading["sections"]:
        body = section["body"]
        assert len(body) <= 1200 and body.endswith("。"), body[-30:]
        for sentence in filter(None, body.split("。")):
            fact, _, said = sentence.partition("，常和")
            for keyword in said.removesuffix("联系在一起").split("、"):
                named = [c for c in keyword if c in STEMS + BRANCHES]
                if len(named) >= 2:
                    assert set(named) <= set(fact), sentence
                    pairs += 1
    assert pairs  # this chart has a 天干合 in 2027 (丙辛), so the check is not vacuous


async def test_relation_facts_give_dates_only(make):  # noqa: F811
    runtime, composer, _ = make(bazi_written)
    await runtime.turn(INVESTMENT)
    sheet = composer.seen[0][0][1]["content"]
    relations = [line for line in sheet.splitlines() if "｜流期与原局｜" in line]
    assert relations
    for line in relations:
        text = line.split("｜")[2]
        assert "北京时间" not in text and not re.search(r"\d\d:\d\d", text), text
    # The flow pillar keeps its exact start and end.
    pillars = [line for line in sheet.splitlines() if "｜流月｜" in line]
    assert pillars and all(re.search(r"\d\d:\d\d", line) for line in pillars)
