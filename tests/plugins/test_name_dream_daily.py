"""Week 6: name five grids, dream symbols and daily fortune with its same-day cache."""

import json
import sqlite3
from datetime import date, timedelta

import pytest
import yaml

from agents.consult import ConsultService
from app import ROOT, create_runtime
from common.schemas import Reading
from knowledge.build import build
from knowledge.kb import KnowledgeBase
from plugins.astro.calculator import BODY_ZH
from plugins.daily.tools import daily_seed
from plugins.dream.match import BARE_FRAGMENTS, DISTINCT_HEADS, DreamMatcher
from plugins.name.strokes import UnihanMissing, char_strokes, unihan
from plugins.name.wuge import analyze, element, grids, relation, shuli
from signals.merge import merge_signals
from tests.plugins.test_astro_bazi_integration import invoke

NAMES = yaml.safe_load((ROOT / "evals/cases/name_strokes.yaml").read_text(encoding="utf-8"))
DREAMS = yaml.safe_load((ROOT / "evals/cases/dream_annotations.yaml").read_text(encoding="utf-8"))
ASPECT_ZH = dict(conjunction="合", opposition="对分", trine="三分", square="四分", sextile="六分")
LOW = dict(level="low", reason="释义为未人工审核草稿")
BIRTH = {
    "birth_local_dt": "1996-05-10 08:30",
    "tz": "Asia/Shanghai",
    "lat": 30.66,
    "lon": 104.07,
    "time_known": True,
}


def reading(system, ref, summary, question_type=None, text="依据本次计算。"):
    return Reading.model_validate(
        dict(
            question_type=question_type or system,
            systems_used=[system],
            summary=summary,
            evidence=[dict(ref_id=ref, reading=text)],
            confidence=LOW,
            safety=dict(flag=False, note=""),
        )
    )


def check(runtime, value):
    return runtime.registry.tools["submit_reading"].validator(value, runtime.session)


async def ask(runtime, message, question=None):
    runtime.session.append_user(message)
    assert (await invoke(runtime, "start_reading", dict(question=question or message))).ok


def with_birth(runtime, **extra):
    for field, value in {**BIRTH, **extra}.items():
        runtime.session.profile = runtime.store.update_profile(
            runtime.session.user_id, field, value, "合成测试资料"
        )


# ---- strokes and five grids -------------------------------------------------------------


def test_all_200_dataset_strokes_and_default_forms():
    wrong = []
    for item in NAMES["items"]:
        result = char_strokes(item["char"], item["role"])
        if (result["form"], result["strokes"]) != (
            item["traditional"],
            item["expected_kangxi_strokes"],
        ):
            wrong.append(item["char"])
        if "known_value" in item:
            assert result["strokes"] == item["known_value"]
    assert wrong == []


def test_nineteen_review_characters_are_finalised():
    review = {i["char"]: i for i in NAMES["items"] if i["status"] == "needs_review"}
    assert len(review) == 19
    confirm = {k for k, v in review.items() if char_strokes(k, v["role"])["needs_confirmation"]}
    # Real alternative spellings ask for confirmation; pure surname conventions do not.
    assert confirm == {"肖", "万", "钟", "丽", "强", "艳", "杰", "郁", "胜"}
    jie = char_strokes("杰", "given")
    assert (jie["form"], jie["strokes"]) == ("傑", 12)
    assert [(a["form"], a["strokes"]) for a in jie["alternatives"]] == [("杰", 8)]
    chosen = char_strokes("杰", "given", "杰")
    assert (chosen["strokes"], chosen["needs_confirmation"], chosen["confirmed"]) == (
        8,
        False,
        True,
    )
    with pytest.raises(ValueError):
        char_strokes("杰", "given", "桀")


def test_radical_restoration_and_numerals():
    assert char_strokes("江", "surname")["strokes"] == 7  # 氵 as 水
    assert char_strokes("陈", "surname")["strokes"] == 16  # left 阝 as 阜
    assert char_strokes("郑", "surname")["strokes"] == 19  # right 阝 as 邑
    assert char_strokes("五", "given")["strokes"] == 5
    assert char_strokes("十", "given")["strokes"] == 10


def test_unknown_character_is_never_guessed():
    result = analyze("王", "😀")
    assert result["status"] == "unknown_chars" and result["unknown"] == ["😀"]


def test_missing_unihan_is_explicit(tmp_path):
    with pytest.raises(UnihanMissing):
        unihan(tmp_path)


@pytest.mark.parametrize(
    "surname,given,expected",
    [
        ("张", "三", {"天格": 12, "人格": 14, "地格": 4, "外格": 2, "总格": 14}),
        ("王", "思远", {"天格": 5, "人格": 13, "地格": 26, "外格": 18, "总格": 30}),
        ("欧阳", "子涵", {"天格": 32, "人格": 20, "地格": 15, "外格": 27, "总格": 47}),
        ("欧阳", "修", {"天格": 32, "人格": 27, "地格": 11, "外格": 16, "总格": 42}),
    ],
)
def test_five_grids_single_and_compound_surnames(surname, given, expected):
    result = analyze(surname, given)
    assert result["grids"] == expected
    assert result["sancai"]["key"] == "".join(
        element(expected[g]) for g in ("天格", "人格", "地格")
    )


def test_grid_formula_numbers_and_relations():
    assert grids([7], [1]) == {"天格": 8, "人格": 8, "地格": 2, "外格": 2, "总格": 8}
    assert [element(n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)] == list("木木火火土土金金水水")
    assert (shuli(81), shuli(82), shuli(163)) == (81, 2, 3)
    assert (relation("木", "火"), relation("火", "木"), relation("木", "土")) == (
        "生",
        "被生",
        "克",
    )


async def test_analyze_name_provenance_and_compound_split(runtime):
    await ask(runtime, "帮我看看“欧阳子涵”这个名字")
    split = await invoke(runtime, "analyze_name", dict(surname="欧", given="阳子涵"))
    assert "复姓" in split.error
    invented = await invoke(runtime, "analyze_name", dict(surname="李", given="四"))
    assert "原话" in invented.error
    ok = await invoke(runtime, "analyze_name", dict(surname="欧阳", given="子涵"))
    assert ok.ok and ok.data["grids"]["天格"] == 32
    assert ok.data["name_id"] == analyze("欧阳", "子涵")["name_id"]
    unconfirmed = await invoke(
        runtime, "analyze_name", dict(surname="欧阳", given="子涵", forms={"涵": "涵"})
    )
    assert "确认" in unconfirmed.error


async def test_profile_name_two_names_and_validator(runtime):
    runtime.session.profile = {"name": "赵杰", "version": 1}
    await ask(runtime, "我名字里的“杰”按几画算？和“李逸”比呢")
    first = await invoke(runtime, "analyze_name", dict(surname="赵", given="杰"))
    second = await invoke(runtime, "analyze_name", dict(surname="李", given="逸"))
    assert first.ok and second.ok and first.data["ambiguities"][0]["char"] == "杰"
    ref = first.data["interpretations"][1]["ref_id"]
    explain = "“杰”默认傑12画，写原字8画，请按证件确认。"
    assert "多种写法" in check(runtime, reading("name", ref, "“杰”按12画计。"))
    assert check(runtime, reading("name", ref, explain + "赵杰人格26。")) is None
    # Each claim is checked against the name it belongs to (see test_week6_review).
    assert check(runtime, reading("name", ref, explain + "李逸人格22。")) is None
    assert "不符" in check(runtime, reading("name", ref, explain + "赵杰人格23。"))
    assert "不符" in check(runtime, reading("name", ref, explain + "赵杰三才配置为木木木。"))
    # Five-element advice is allowed as a traditional inference; fatalism is not.
    assert check(runtime, reading("name", ref, explain + "名字五行缺水，可倾向补水。")) is None
    assert "命运" in check(runtime, reading("name", ref, explain + "这个名字注定成功。"))
    signals = [s for s in runtime.session.state["signals"] if s["system"] == "name"]
    assert {s["horizon"] for s in signals} == {"trait"}
    assert max(s["strength"] for s in signals) <= 0.35  # below bazi/natal strengths


async def test_confirmed_written_form_changes_strokes(runtime):
    await ask(runtime, "我叫赵杰，证件上写的是原字，不用繁体")
    result = await invoke(
        runtime, "analyze_name", dict(surname="赵", given="杰", forms={"杰": "杰"})
    )
    assert result.ok and result.data["grids"]["人格"] == 14 + 8 and not result.data["ambiguities"]


async def test_name_bazi_comparison_uses_reading_bazi_only(runtime):
    runtime.session.append_user(
        "我是男，出生于1993-08-17 23:20，北京；我叫王思远，结合八字看看名字"
    )
    assert (await invoke(runtime, "start_reading", dict(question="结合八字看名字"))).ok
    location = await invoke(runtime, "resolve_location", dict(query="北京"))
    wrong = await invoke(
        runtime, "analyze_name", dict(surname="王", given="思远", bazi_id="not-this-reading")
    )
    assert "本记录" in wrong.error
    bazi = await invoke(
        runtime,
        "compute_bazi",
        dict(
            birth_local="1993-08-17 23:20",
            location_id=location.data["location"]["location_id"],
            gender="male",
        ),
    )
    result = await invoke(
        runtime, "analyze_name", dict(surname="王", given="思远", bazi_id=bazi.data["bazi_id"])
    )
    comparison = result.data["bazi_comparison"]
    assert comparison["bazi_wuxing_count"] == bazi.data["wuxing_count"]
    assert sum(comparison["sancai_element_count"].values()) == 3


async def test_unknown_char_asks_user(runtime):
    # 麺 has only a simplified-radical entry and no traditional variant in Unihan.
    await ask(runtime, "帮我看看“王麺”这个名字")
    result = await invoke(runtime, "analyze_name", dict(surname="王", given="麺"))
    assert result.data["status"] == "needs_input" and result.data["code"] == "unknown_name_char"


# ---- dream ------------------------------------------------------------------------------


def test_dream_kb_covers_seed_vocabulary_and_excludes_probes(project):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        matcher = DreamMatcher(kb.db, kb.version)
        assert len(matcher.entries) >= 300
        assert set(DREAMS["vocabulary_used"]["keys"]) <= set(matcher.entries)
        oov = {o for item in DREAMS["items"] for o in item["out_of_vocabulary"]}
        assert not oov & set(matcher.aliases)
        for key, synonyms in DREAMS["vocabulary_used"]["synonym_examples"].items():
            for synonym in synonyms:
                # Live review found that a venue alone does not imply taking an exam.
                # Keep the older draft dataset intact; assert the corrected boundary.
                expected = None if (key, synonym) == ("考试", "考场") else key
                assert matcher.match(synonym)["key"] == expected
        assert kb.db.execute("SELECT count(*) FROM dream_fts").fetchone()[0] > 300
    finally:
        kb.close()


def test_distinct_heads_are_never_read_as_another_symbol(project):
    """Review removed 熊猫→熊 etc.; containment must not then interpret 猫, 火车 or 花."""
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        matcher = DreamMatcher(kb.db, kb.version)
        for query in (*DISTINCT_HEADS, "大熊猫", "一只熊猫", *BARE_FRAGMENTS):
            assert matcher.match(query)["key"] is None, query
        assert matcher.scan("梦见一只大熊猫踩着雪花，骑着电动车，旁边有一只黑猫") == ["猫"]
        assert matcher.match("黑猫")["key"] == "猫"
        assert matcher.match("钥匙丢了")["key"] == "钥匙"
        assert matcher.match("动车")["key"] == "火车"
        # An alias for the head itself, once the knowledge base has one, wins.
        matcher.aliases["熊猫"] = "熊"
        assert matcher.match("熊猫")["key"] == matcher.match("大熊猫")["key"] == "熊"
        assert matcher.scan("梦见熊猫") == ["熊"]
    finally:
        kb.close()


def test_dream_matching_methods(project):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        matcher = DreamMatcher(kb.db, kb.version)
        assert matcher.match("掉牙")["method"] == "key"
        assert matcher.match("高铁")["key"] == "火车"
        assert matcher.match("一条大鱼")["key"] == "鱼"
        assert matcher.match("牙掉")["key"] == "掉牙"
        # The head noun comes last: a gate of the metro is not the metro.
        assert matcher.match("地铁闸机")["key"] is None
        bm25 = matcher.match("婚礼仪式")
        assert bm25["key"] is None or bm25["score"] >= matcher.threshold
        assert matcher.match("无人机") == dict(
            query="无人机", key=None, method="unmatched", score=0.0
        )
    finally:
        kb.close()


async def test_dream_tool_hits_misses_and_psyche_only(runtime):
    await ask(runtime, "梦见无人机掉在我家阳台，还被一条大狗追，是不是要出事了？")
    invented = await invoke(
        runtime, "lookup_dream_symbols", dict(symbols=[dict(phrase="考试", symbol="考试")])
    )
    assert "逐字来自" in invented.error
    result = await invoke(
        runtime,
        "lookup_dream_symbols",
        dict(
            symbols=[
                dict(phrase="无人机", symbol="无人机"),
                dict(phrase="一条大狗", symbol="大狗"),
                dict(phrase="被一条大狗追", symbol="被追"),
            ]
        ),
    )
    assert [h["key"] for h in result.data["hits"]] == ["狗", "被追"]
    assert result.data["misses"] == ["无人机"]
    dream = [s for s in runtime.session.state["signals"] if s["system"] == "dream"]
    assert dream and {s["horizon"] for s in dream} == {"psyche"}
    ref = result.data["interpretations"][0]["ref_id"]
    ok = "不是要出事，这个梦更像压力感受，不预示现实事件。"
    assert check(runtime, reading("dream", ref, ok)) is None
    assert "预兆" in check(runtime, reading("dream", ref, "这个梦预示近期会有麻烦。"))
    assert "未在词典" in check(runtime, reading("dream", ref, "无人机象征科技焦虑。"))
    assert check(runtime, reading("dream", ref, "无人机未收录，暂不解读；被追反映压力。")) is None
    assert "不是本次命中" in check(runtime, reading("dream", ref, "梦里的「蛇」代表转变。"))


def test_dream_signals_never_cancel_timing():
    from tests.agents.test_merge_and_reviewer import sig

    merged = merge_signals(
        [
            sig("dream", "career", -0.3, 0.9, horizon="psyche"),
            sig("astro", "career", 0.3, 0.9, horizon="timing", timeframe="2026-11-03"),
            sig("bazi", "career", 0.3, 0.9, horizon="timing", timeframe="2026-11-03"),
        ]
    )
    assert merged["tensions"] == []


# ---- daily fortune ----------------------------------------------------------------------


async def daily(runtime, message="今天运势怎么样？"):
    await ask(runtime, message)
    return await invoke(runtime, "daily_fortune", dict(date=runtime.session.calendar_anchor))


async def test_daily_needs_birth_data(runtime):
    result = await daily(runtime)
    assert result.data["status"] == "needs_input"
    assert result.data["code"] == "missing_birth_information"


async def test_daily_same_day_unchanged_across_sessions_and_cache(project):
    outputs = []
    for attempt in range(10):
        runtime = create_runtime(root=project, user_id="daily-user", seed=attempt)
        try:
            if attempt == 0:
                with_birth(runtime)
            result = await daily(runtime)
            assert result.ok and result.data.get("status") != "needs_input"
            assert result.data["cache_reused"] is (attempt > 0)
            outputs.append(
                json.dumps(
                    {k: v for k, v in result.data.items() if k != "cache_reused"},
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        finally:
            runtime.close()
    assert len(set(outputs)) == 1
    row = sqlite3.connect(project / "data/app.db").execute("SELECT count(*) FROM daily").fetchone()
    assert row == (1,)


async def test_daily_pure_recompute_is_identical(project):
    runtime = create_runtime(root=project, user_id="daily-pure", seed=1)
    try:
        with_birth(runtime)
        first = await daily(runtime)
        plugin = runtime.registry.tools["daily_fortune"].handler.__self__
        chart = runtime.store.get_calculation(
            "astro", "daily-pure", first.data["natal"]["chart_id"]
        )
        bazi = runtime.store.get_calculation("bazi", "daily-pure", first.data["bazi"]["bazi_id"])
        again = plugin.compute("daily-pure", first.data["date"], "Asia/Shanghai", chart, bazi)
        keep = ("seed", "card", "day", "events", "daily_id", "signals")
        stored = runtime.store.get_daily("daily-pure", first.data["date"])["result"]
        assert {k: again[k] for k in keep} == {k: stored[k] for k in keep}
    finally:
        runtime.close()


def test_daily_seed_is_stable_and_date_specific():
    assert daily_seed("u", "2026-10-14") == daily_seed("u", "2026-10-14")
    assert len({daily_seed("u", f"2026-10-{d:02d}") for d in range(1, 31)}) == 30
    assert daily_seed("u", "2026-10-14") != daily_seed("v", "2026-10-14")
    assert daily_seed("u", "2026-10-14") == 11742066326863056085


async def test_daily_date_must_match_the_question(runtime):
    with_birth(runtime)
    await ask(runtime, "明天运势怎么样？")
    today = runtime.session.calendar_anchor
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    wrong = await invoke(runtime, "daily_fortune", dict(date=today))
    assert tomorrow in wrong.error
    assert (await invoke(runtime, "daily_fortune", dict(date=tomorrow))).ok


async def test_daily_profile_change_recomputes(project):
    runtime = create_runtime(root=project, user_id="daily-change", seed=1)
    try:
        with_birth(runtime)
        first = await daily(runtime)
        with_birth(runtime, birth_local_dt="1996-05-11 08:30")
        second = await daily(runtime, "今天运势怎么样？更正了出生日期")
        assert second.data["recomputed_after_profile_change"] is True
        assert second.data["bazi"]["pillars"] != first.data["bazi"]["pillars"]
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "anchor,expected_pillars",
    [
        ("2026-10-15", {"壬戌", "癸亥"}),
        ("2026-10-16", {"癸亥", "甲子"}),
        ("2026-10-17", {"甲子", "乙丑"}),
    ],
)
async def test_daily_reading_validates_card_pillar_and_aspects(runtime, anchor, expected_pillars):
    runtime.session.calendar_anchor = anchor
    with_birth(runtime)
    result = await daily(runtime, "今天适合签合同吗？")
    state = runtime.session.state
    assert {s["horizon"] for s in state["signals"]} == {"moment"}
    assert {s["system"] for s in state["signals"]} == {"daily"}
    card, day = result.data["card"], result.data["day"]
    orientation = "逆位" if card["reversed"] else "正位"
    good = f"今天可以签，前提是核对条款；流日{day['pillar']}，每日一牌【{card['name']}】{orientation}。"
    assert check(runtime, reading("daily", card["ref_id"], good[:80])) is None
    other = "愚人" if card["name"] != "愚人" else "魔术师"
    assert "未抽出" in check(
        runtime, reading("daily", card["ref_id"], f"今天抽到【{other}】正位。")
    )
    # The 23:00 day boundary permits two pillars in one civil day. A different
    # noon pillar alone does not make a fabricated fact (e.g. 甲子 on Oct 16).
    segment_pillars = {segment["pillar"] for segment in day["segments"]}
    assert segment_pillars == expected_pillars
    for pillar in segment_pillars:
        assert check(runtime, reading("daily", card["ref_id"], f"当天分段流日{pillar}。")) is None
    known_pillars = segment_pillars | set(result.data["bazi"]["pillars"].values())
    fake = next(
        pillar
        for pillar in ("甲子", "乙丑", "丙寅", "丁卯", "戊辰", "己巳", "庚午")
        if pillar not in known_pillars
    )
    assert "干支" in check(runtime, reading("daily", card["ref_id"], f"今天流日{fake}。"))
    computed = {(e["transit_body"], e["natal_body"], e["aspect"]) for e in result.data["events"]}
    for e in result.data["events"]:
        text = f"今天行运{BODY_ZH[e['transit_body']]}{ASPECT_ZH[e['aspect']]}本命{BODY_ZH[e['natal_body']]}。"
        assert check(runtime, reading("daily", card["ref_id"], text)) is None
    wrong = next(
        b for b in ("Pluto", "Saturn", "Uranus") if ("Mars", b, "conjunction") not in computed
    )
    text = f"今天行运火星合本命{BODY_ZH[wrong]}。"
    assert "相位" in check(runtime, reading("daily", card["ref_id"], text))


async def test_daily_saved_reading_followup_keeps_card_and_forget_clears(project):
    runtime = create_runtime(root=project, user_id="daily-follow", seed=1)
    try:
        with_birth(runtime)
        result = await daily(runtime)
        card = result.data["card"]
        orientation = "逆位" if card["reversed"] else "正位"
        summary = f"今天适合稳步推进，每日一牌【{card['name']}】{orientation}。"
        submitted = await invoke(
            runtime,
            "submit_reading",
            reading("daily", card["ref_id"], summary).model_dump(mode="json"),
        )
        assert submitted.ok
        runtime.session.append_user("今天那张牌什么意思？")
        restored = await invoke(runtime, "read_reading", {})
        assert restored.ok and card["name"] in runtime.session.state["facts"]
        assert check(runtime, reading("daily", card["ref_id"], summary)) is None
        runtime.forget()
        assert runtime.store.get_daily("daily-follow", result.data["date"]) is None
    finally:
        runtime.close()


# ---- wiring -----------------------------------------------------------------------------


def test_kb_partitions_and_rules(project):
    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        coverage = json.loads(
            kb.db.execute("SELECT value FROM meta WHERE key='coverage'").fetchone()[0]
        )
        for system, count in (("name", 220), ("daily", 9)):
            assert coverage["partitions"][system]["entries"] == count
            assert coverage["partitions"][system]["coverage"] == 1.0
        assert coverage["partitions"]["dream"]["entries"] >= 303
        assert kb.rules("name")["max_strength"] < kb.rules("bazi")["strength"]["god_pillar"]
        assert kb.rules("dream")["horizon"] == "psyche"
        assert kb.rules("daily")["horizon"] == "moment"
        assert all(kb.lookup("name", "shuli", str(n)) for n in range(1, 82))
    finally:
        kb.close()


def test_missing_name_entry_fails_build(project):
    path = project / "sources/name/entries.yaml"
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    content["entries"] = [e for e in content["entries"] if e["key"] != "81"]
    path.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="覆盖不完整"):
        build(project / "sources", project / "data/other.sqlite", project / "rules")


def test_name_specialist_inherits_reading_bazi(project):
    runtime = create_runtime(root=project, user_id="multi-name", mode="multi", seed=1)
    try:
        service = runtime.registry.tools["consult_specialist"].handler.__self__
        assert isinstance(service, ConsultService)
        from agents.schemas import ConsultInput

        parent = dict(
            active_reading_id="r", question="q", bazi_id="b1", signals=[], allowed_refs=set()
        )
        args = ConsultInput(system="name", sub_question="看名字")
        assert service.child_state(service.specs["name"], args, parent)["bazi_id"] == "b1"
        args = ConsultInput(system="dream", sub_question="解梦")
        assert "bazi_id" not in service.child_state(service.specs["dream"], args, parent)
        assert runtime.registry.tools["daily_fortune"].roles == frozenset({"orchestrator"})
    finally:
        runtime.close()
