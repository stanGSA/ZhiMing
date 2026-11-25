"""Regression tests for range evidence parsing, localized validators, and step efficiency.

Covers:
1. Cross-month, cross-year, and same-month year-omitted date range parsing in question_range.
2. Dream and astrology ValidationMessage original-sentence localization, retry_key stability,
   and taxonomy/category quote-stripping compatibility.
3. Profile validator boolean-first checks, resolved birthplace alias grounding, same-turn
   location preservation across start_reading, and root-cause hints in birth_provenance.
4. Deterministic ask_user gate requiring compute_bazi/compute_natal_chart before asking about
   DST gap/fold or solar-term boundaries when complete Gregorian birth details are present.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from common.input_evidence import question_range
from common.schemas import Evidence, Reading, Section, Timeline
from harness.loop import run_turn
from harness.models import ModelResponse, ToolCall, ValidationMessage
from plugins.astro.validation import validate_output as validate_astro_facts
from plugins.context import BirthInput, birth_provenance, range_provenance
from plugins.dream.match import DreamMatcher
from plugins.dream.validation import validate_output as validate_dream_facts
from scripts.compare_layers import rejection_category
from scripts.failure_taxonomy import category as taxonomy_category
from tests.plugins.test_astro_bazi_integration import invoke


class Replay:
    def __init__(self, steps):
        self.steps = iter(steps)

    async def chat(self, messages, tools):
        return next(self.steps)


def call_step(index: int, name: str, **arguments) -> ModelResponse:
    return ModelResponse(
        input_tokens=100,
        output_tokens=20,
        tool_calls=[ToolCall(id=f"call-{index}", name=name, arguments=arguments)],
    )


# ---------------------------------------------------------------------------
# 1. Cross-month / cross-year / same-month year-omitted date range parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,anchor,expected",
    [
        (
            "合成资料：我是男性，2001年11月25日上午10点出生于中国北京市。"
            "根据我的八字，看看这个月（2026年10月8日到11月6日）有什么值得关注的？",
            "2026-10-15",
            ("2026-10-08", "2026-11-06"),
        ),
        ("2026-10-08~11-06 运势如何？", "2026-10-15", ("2026-10-08", "2026-11-06")),
        ("2026/10/8—11/6", None, ("2026-10-08", "2026-11-06")),
        ("2026年12月20日到1月10日适合出行吗？", "2026-12-01", ("2026-12-20", "2027-01-10")),
        ("2023年12月20日到2月29日", None, ("2023-12-20", "2024-02-29")),
        ("2026年10月8日到15日安排面试怎么样？", "2026-10-01", ("2026-10-08", "2026-10-15")),
        ("2026年10月8号到15号", None, ("2026-10-08", "2026-10-15")),
        # Invalid dates safely return None without falling back to "这个月".
        ("看看这个月（2026年2月20日到2月30日）运势", "2026-02-10", None),
        ("2026年2月20日到30日", "2026-02-10", None),
        ("2025年12月20日到2月29日", None, None),
        ("2026年2月30日到3月5日", None, None),
        ("2026年10月15日到8日", None, None),
        # Non-date suffixes and unrelated birth dates must not form ranges.
        ("2026年10月8日到15点在开会", None, None),
        ("我1993年8月17日出生，看看10月8日到11月6日运势", None, None),
    ],
)
def test_question_range_supports_year_omitted_and_preserves_boundaries(text, anchor, expected):
    assert question_range(text, anchor) == expected


def test_range_provenance_accepts_bazi_month_year_omitted_range():
    session = NS(
        user_messages=[
            "合成资料：我是男性，2001年11月25日上午10点出生于中国北京市。"
            "根据我的八字，看看这个月（2026年10月8日到11月6日）有什么值得关注的？"
        ],
        profile={},
        state={"question_message_index": 0},
        calendar_anchor="2026-10-15",
    )
    assert range_provenance(NS(start="2026-10-08", end="2026-11-06"), session) is None
    assert range_provenance(NS(start="2026-10-01", end="2026-10-31"), session) is not None


# ---------------------------------------------------------------------------
# 2. Dream & Astro ValidationMessage localization, retry_key, and taxonomy
# ---------------------------------------------------------------------------


def _dream_reading(body: str, *, timeline: list[Timeline] | None = None) -> Reading:
    return Reading(
        question_type="dream",
        systems_used=["dream"],
        summary="梦境反映近期情绪张力。",
        sections=[Section(title="心理线索", body=body, ref_ids=["r1"])],
        evidence=[Evidence(ref_id="r1", reading="命中意象：狗")],
        timeline=timeline or [],
    )


def test_dream_validation_returns_localized_validation_messages_and_retry_keys(project):
    from knowledge.kb import KnowledgeBase

    kb = KnowledgeBase(project / "data/kb.sqlite")
    try:
        matcher = DreamMatcher(kb.db, kb.version)
        state = {
            "calculations": {
                "dream_result:1": {
                    "hits": [{"key": "狗"}],
                    "misses": ["无人机"],
                }
            }
        }

        unmatched = validate_dream_facts(
            _dream_reading("无人机象征你对失控的焦虑。"), state, matcher
        )
        assert isinstance(unmatched, ValidationMessage)
        assert "未在词典中命中" in unmatched
        assert "冲突片段：“无人机象征你对失控的焦虑”" in unmatched
        assert "位于 sections[0].body" in unmatched
        assert unmatched.retry_key == "dream_unmatched:无人机"

        unhit = validate_dream_facts(
            _dream_reading("梦里的「蛇」代表关系里的警惕。"), state, matcher
        )
        assert isinstance(unhit, ValidationMessage)
        assert "不是本次命中的意象" in unhit
        assert "冲突片段：“梦里的「蛇」代表关系里的警惕”" in unhit
        assert unhit.retry_key == "dream_unhit:蛇"

        prophecy = validate_dream_facts(
            _dream_reading("狗的状态预示你下周相位和原话都会遇到麻烦。"),
            state,
            matcher,
        )
        assert isinstance(prophecy, ValidationMessage)
        assert "现实事件的预兆" in prophecy
        assert "冲突原句：“狗的状态预示你下周相位和原话都会遇到麻烦”" in prophecy
        assert prophecy.retry_key == "dream_prophecy"
        # Quoted sentence words ("相位", "原话") must be stripped before taxonomy/rejection bucketing.
        assert rejection_category({"code": "validation_failed", "error": prophecy}) == "other"
        assert taxonomy_category("submit_reading", "validation_failed", prophecy).startswith("Z ")

        timeline_err = validate_dream_facts(
            _dream_reading(
                "狗反映安全感需求。", timeline=[Timeline(period="本周", note="注意情绪")]
            ),
            state,
            matcher,
        )
        assert isinstance(timeline_err, ValidationMessage)
        assert timeline_err.retry_key == "dream_timeline"
    finally:
        kb.close()


def _astro_reading(body: str) -> Reading:
    return Reading(
        question_type="trait",
        systems_used=["astro"],
        summary="工作风格务实稳健。",
        sections=[Section(title="核心配置", body=body, ref_ids=["r1"])],
        evidence=[Evidence(ref_id="r1", reading="本命太阳摩羯座第4宫")],
    )


def test_astro_position_validation_quotes_original_sentence_and_actual_values():
    unknown_state = {
        "natal_result": {
            "time_known": False,
            "planets": [{"body_zh": "太阳", "sign_zh": "摩羯", "house": None}],
            "axes": None,
            "aspects": [],
        }
    }
    err_unknown = validate_astro_facts(
        _astro_reading("你的上升落在白羊座，做事直接。"), unknown_state
    )
    assert isinstance(err_unknown, ValidationMessage)
    assert "出生时间未知，不能使用宫位或四轴解读" in err_unknown
    assert "冲突原句：“你的上升落在白羊座，做事直接”" in err_unknown
    assert err_unknown.retry_key == "astro_unknown_time_house_axis"
    assert rejection_category({"code": "validation_failed", "error": err_unknown}) == "fact"
    assert (
        taxonomy_category("submit_reading", "validation_failed", err_unknown) == "E 事实与计算不符"
    )

    known_state = {
        "natal_result": {
            "time_known": True,
            "planets": [{"body_zh": "太阳", "sign_zh": "摩羯", "house": 4}],
            "axes": {"asc": 155.0, "mc": 65.0, "dsc": 335.0, "ic": 245.0},
            "aspects": [],
        }
    }
    err_transit = validate_astro_facts(_astro_reading("行运土星落在双鱼座带来考验。"), known_state)
    assert isinstance(err_transit, ValidationMessage)
    assert "行运星落座宫位未作为本次事实提供" in err_transit
    assert "冲突原句：“行运土星落在双鱼座带来考验”" in err_transit
    assert err_transit.retry_key == "astro_transit_position:土星"
    assert rejection_category({"code": "validation_failed", "error": err_transit}) == "fact"

    # Pre-normalize_positions word order ("狮子座太阳") must appear verbatim in 冲突原句.
    err_sign = validate_astro_facts(
        _astro_reading("本命狮子座太阳让你在原话和画像中显得格外外放。"), known_state
    )
    assert isinstance(err_sign, ValidationMessage)
    assert "行星落座或四轴与本次计算不符" in err_sign
    assert "冲突原句：“本命狮子座太阳让你在原话和画像中显得格外外放”" in err_sign
    assert "本次计算太阳实际落座为摩羯座" in err_sign
    assert err_sign.retry_key == "astro_sign:太阳"
    assert rejection_category({"code": "validation_failed", "error": err_sign}) == "fact"
    assert taxonomy_category("submit_reading", "validation_failed", err_sign) == "E 事实与计算不符"

    err_axis = validate_astro_facts(_astro_reading("上升白羊让你行事果断。"), known_state)
    assert isinstance(err_axis, ValidationMessage)
    assert "本次计算上升实际落座为处女座" in err_axis
    assert err_axis.retry_key == "astro_sign:上升"

    # Pre-normalize_positions house wording ("摩羯座第9宫太阳") must appear verbatim in 冲突原句.
    err_house = validate_astro_facts(_astro_reading("本命摩羯座第9宫太阳强调探索。"), known_state)
    assert isinstance(err_house, ValidationMessage)
    assert "宫位不可用或与本次计算不符" in err_house
    assert "冲突原句：“本命摩羯座第9宫太阳强调探索”" in err_house
    assert "位于 sections[0].body" in err_house
    assert "本次计算太阳实际位于第4宫" in err_house
    assert err_house.retry_key == "astro_house:太阳"
    assert rejection_category({"code": "validation_failed", "error": err_house}) == "fact"
    assert taxonomy_category("submit_reading", "validation_failed", err_house) == "E 事实与计算不符"


# ---------------------------------------------------------------------------
# 3. Profile validator, location preservation, and birth_provenance hints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_validator_checks_bool_first_and_grounds_birth_place_aliases(runtime):
    runtime.session.append_user("我1993年8月17日晚上11点20分在北京出生，现在住在纽约。")

    # String "true" on boolean field must report boolean type error first, never substring error.
    bad_bool = await invoke(
        runtime,
        "update_profile",
        dict(field="time_known", value="true", evidence="晚上11点20分"),
    )
    assert not bad_bool.ok
    assert "该字段必须是布尔值" in bad_bool.error
    assert "自动保存" in bad_bool.error
    assert "字段值必须在 evidence 原话中" not in bad_bool.error

    # Before resolving location, ungrounded alias "北京市" is still rejected with auto-save hint.
    before_resolve = await invoke(
        runtime,
        "update_profile",
        dict(field="birth_place", value="北京市", evidence="在北京出生"),
    )
    assert not before_resolve.ok
    assert "自动保存" in before_resolve.error

    # After resolving "北京", canonical alias "北京市" grounded in birthplace utterance is accepted.
    assert (await invoke(runtime, "resolve_location", dict(query="北京", country="CN"))).ok
    after_resolve = await invoke(
        runtime,
        "update_profile",
        dict(field="birth_place", value="北京市", evidence="在北京出生"),
    )
    assert after_resolve.ok

    # Unrelated cities and non-birth residence places remain strictly blocked.
    fabricated = await invoke(
        runtime,
        "update_profile",
        dict(field="birth_place", value="上海市", evidence="在北京出生"),
    )
    assert not fabricated.ok

    assert (await invoke(runtime, "resolve_location", dict(query="纽约", country="US"))).ok
    residence_as_birth = await invoke(
        runtime,
        "update_profile",
        dict(field="birth_place", value="New York City", evidence="现在住在纽约"),
    )
    assert not residence_as_birth.ok


@pytest.mark.asyncio
async def test_same_turn_resolved_location_survives_start_reading(runtime):
    runtime.session.append_user(
        "合成资料：公历1995-12-31 23:45，纽约（美国）出生。只用西方占星看性格。"
    )
    loc = await invoke(runtime, "resolve_location", dict(query="New York", country="US"))
    assert loc.ok and loc.data["location"]["location_id"] == "5128581"

    started = await invoke(
        runtime, "start_reading", dict(question="占星性格分析", systems=["astro"])
    )
    assert started.ok

    chart = await invoke(
        runtime,
        "compute_natal_chart",
        dict(birth_local="1995-12-31 23:45", location_id="5128581", tz="America/New_York"),
    )
    assert chart.ok and chart.data.get("chart_id")


@pytest.mark.asyncio
async def test_birth_provenance_gives_root_cause_hint_for_pending_candidates_and_unresolved_loc(
    runtime,
):
    runtime.session.append_user(
        "合成资料：公历1998-04-12 09:30，出生地Springfield。只用占星看工作。"
    )
    assert (await invoke(runtime, "start_reading", dict(question="工作方向", systems=["astro"]))).ok

    # Before resolve_location: hand-filling tz must say resolve_location first, not Xinjiang error.
    pre_err = birth_provenance(
        BirthInput(birth_local="1998-04-12 09:30", tz="America/Chicago"),
        runtime.session,
    )
    assert pre_err is not None
    assert "resolve_location" in pre_err
    assert "新疆" not in pre_err

    # After resolve_location returns multiple candidates: hand-filling tz must point to ask_user.
    res = await invoke(runtime, "resolve_location", dict(query="Springfield"))
    assert res.ok and res.data["status"] == "needs_input" and len(res.data["candidates"]) > 1

    cand_err = birth_provenance(
        BirthInput(birth_local="1998-04-12 09:30", tz="America/Chicago"),
        runtime.session,
    )
    assert cand_err is not None
    assert "ask_user" in cand_err
    assert "候选" in cand_err
    assert "新疆" not in cand_err
    assert (
        taxonomy_category("compute_natal_chart", "validation_failed", cand_err)
        == "C 资料来源/地点未确认就计算"
    )

    # Also when passing an unconfirmed candidate_id with manual tz.
    unconfirmed_id = res.data["candidates"][0]["location_id"]
    cand_id_err = birth_provenance(
        BirthInput(
            birth_local="1998-04-12 09:30",
            location_id=unconfirmed_id,
            tz="America/Chicago",
        ),
        runtime.session,
    )
    assert cand_id_err is not None and "ask_user" in cand_id_err and "新疆" not in cand_id_err


# ---------------------------------------------------------------------------
# 4. DST / calendar boundary premature ask_user deterministic gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dst_gap_blocks_premature_ask_user_until_compute_bazi_returns_needs_input(runtime):
    question = "合成资料：男性，公历1986-05-04 02:30，北京出生。只用八字看工作方向。"
    model = Replay(
        [
            call_step(0, "resolve_location", query="北京", country="CN"),
            call_step(
                1,
                "ask_user",
                question="1986-05-04 02:30 处于中国夏令时跳变区间，该时间不存在，请确认原始时间？",
            ),
            call_step(2, "start_reading", question="八字看工作方向", systems=["bazi"]),
            call_step(
                3,
                "compute_bazi",
                birth_local="1986-05-04 02:30",
                location_id="1816670",
                gender="male",
            ),
            call_step(
                4,
                "ask_user",
                question="排盘核验确认 1986-05-04 02:30 因夏令时跳时不存在，请确认实际出生时间。",
            ),
        ]
    )
    outcome = await run_turn(runtime.session, question, model, runtime.registry, runtime.tracer)
    assert outcome.status == "ask_user"

    tool_msgs = [json.loads(m["content"]) for m in runtime.session.messages if m["role"] == "tool"]
    assert not tool_msgs[1]["ok"]
    assert "compute_bazi" in tool_msgs[1]["error"]
    assert "start_reading" in tool_msgs[1]["error"]
    assert tool_msgs[3]["ok"] and tool_msgs[3]["data"]["code"] == "nonexistent_local_time"
    assert tool_msgs[4]["ok"]


@pytest.mark.asyncio
async def test_dst_fold_blocks_premature_ask_user_until_compute_natal_chart_returns_needs_input(
    runtime,
):
    question = "合成资料：公历1986-09-14 01:30，北京出生。只用占星看工作方向，我还没确认是回拨前还是回拨后。"
    model = Replay(
        [
            call_step(0, "resolve_location", query="北京", country="CN"),
            call_step(
                1,
                "ask_user",
                question="1986-09-14 01:30 正好在夏令时回拨当天，请确认是回拨前还是回拨后？",
            ),
            call_step(2, "start_reading", question="占星看工作方向", systems=["astro"]),
            call_step(
                3,
                "compute_natal_chart",
                birth_local="1986-09-14 01:30",
                location_id="1816670",
            ),
            call_step(
                4,
                "ask_user",
                question="排盘核验该时刻出现两次，请确认回拨前（fold=0）还是回拨后（fold=1）。",
            ),
        ]
    )
    outcome = await run_turn(runtime.session, question, model, runtime.registry, runtime.tracer)
    assert outcome.status == "ask_user"

    tool_msgs = [json.loads(m["content"]) for m in runtime.session.messages if m["role"] == "tool"]
    assert not tool_msgs[1]["ok"]
    assert "compute_natal_chart" in tool_msgs[1]["error"]
    assert tool_msgs[3]["ok"] and tool_msgs[3]["data"]["code"] == "ambiguous_local_time"
    assert tool_msgs[4]["ok"]


@pytest.mark.asyncio
async def test_premature_ask_gate_blocks_solar_term_and_allows_lunar_and_xinjiang(runtime):
    # Lunar input must NOT be blocked from asking directly.
    runtime.session.append_user(
        "合成资料：男性，农历2023年二月十五 10:00，北京出生；我还没确认是否闰月。只用八字分析工作方向。"
    )
    assert (await invoke(runtime, "resolve_location", dict(query="北京", country="CN"))).ok
    lunar_ask = await invoke(
        runtime,
        "ask_user",
        dict(question="请确认农历2023年二月十五是普通二月还是闰二月？"),
    )
    assert lunar_ask.ok

    # Complete Gregorian birth + solar-term boundary question BEFORE compute_bazi IS blocked.
    runtime.session.append_user("合成资料：男性，公历1993-08-07 10:00，北京出生。只用八字看工作。")
    runtime.session.state["asked_this_turn"] = False
    assert (
        await invoke(runtime, "start_reading", dict(question="八字看工作", systems=["bazi"]))
    ).ok
    assert (await invoke(runtime, "resolve_location", dict(query="北京", country="CN"))).ok
    solar_term_ask = await invoke(
        runtime,
        "ask_user",
        dict(question="当天靠近立秋交节时刻，请确认是否按真太阳时交节换月？"),
    )
    assert not solar_term_ask.ok
    assert "compute_bazi" in solar_term_ask.error

    # Xinjiang clock-system confirmation is NOT blocked.
    runtime.session.append_user("合成资料：公历2000-01-01 10:00，乌鲁木齐出生。只用八字看工作。")
    runtime.session.state["asked_this_turn"] = False
    assert (await invoke(runtime, "resolve_location", dict(query="乌鲁木齐", country="CN"))).ok
    xj_ask = await invoke(
        runtime,
        "ask_user",
        dict(question="乌鲁木齐出生请确认钟表时间使用的是北京时间还是新疆时间？"),
    )
    assert xj_ask.ok
