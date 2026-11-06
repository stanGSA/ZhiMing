"""Name analysis through the pipeline with scripted models (P2.2 of the plan)."""

import json
import re

import pytest

from app import create_runtime
from pipeline.name import CONFIRM, NO_NAME, TOO_MANY, Name
from tests.pipeline.drafts import Composer

ONE = "帮我看看赵杰这个名字"
TWO = "张伟和李娜哪个名字好？"
LINE = re.compile(r"^(R\d+)｜(\S+?)｜(\S+?)｜", re.M)


def facts_in(messages) -> list[tuple[str, str, str]]:
    """(alias, full name, label) read from the fact sheet the writer was given."""
    return LINE.findall(messages[1]["content"])


def alias_of(messages, label: str, name: str | None = None) -> str:
    return next(
        a for a, n, lab in facts_in(messages) if lab.startswith(label) and name in (None, n)
    )


def written(messages, verdict="描述", extra="") -> str:
    names = list(dict.fromkeys(n for _, n, _ in facts_in(messages)))
    layers = "".join(
        f"【分层】{name}的核心\n{{{{{alias_of(messages, '人格', name)}}}}}在约定里对应自我认知，"
        f"{{{{{alias_of(messages, '三才', name)}}}}}只作自我观察的线索。{extra}\n"
        f"【引用】{alias_of(messages, '人格', name)}\n"
        for name in names
    )
    return (
        f"【表态】{verdict}\n【摘要】这个名字在五格约定里整体偏顺。数理只是取名习俗。\n{layers}"
        "【建议】\n- 当作参考：结合自己的实际感受看待。\n【收尾】名字只是一个起点。"
    )


def wrong_number(messages) -> str:
    return written(messages, extra="另外人格24也很好。")


def fatal(messages) -> str:
    return written(messages, extra="这个名字注定成功。")


def extraction(*names):
    return lambda messages: json.dumps({"names": list(names)}, ensure_ascii=False)


@pytest.fixture
def make(project):
    runtimes = []

    def build(*replies, user_id="name-user"):
        composer = Composer(*replies)
        runtime = create_runtime(
            root=project, user_id=user_id, seed=7, model=composer, mode="pipeline"
        )
        events = []
        runtime.tracer.listeners.append(events.append)
        runtimes.append(runtime)
        return runtime, composer, events

    yield build
    for runtime in runtimes:
        runtime.close()


def planned(events) -> list[str]:
    return [name for e in events if e["event"] == "tool_plan" for name in e["tool_names"]]


def purposes(events) -> list[str]:
    return [e["purpose"] for e in events if e["event"] == "model_response"]


async def test_a_name_code_reads_takes_one_writing_call(make):
    runtime, composer, events = make(written)
    outcome = await runtime.turn(ONE)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["model_calls"], info["repairs"], info["degraded"]) == (1, 0, None)
    assert purposes(events) == ["compose"]
    assert planned(events) == ["start_reading", "analyze_name", "submit_reading"]
    ((messages, tools),) = composer.seen
    assert tools == [] and "name:" not in str(messages)
    assert "赵杰的康熙笔画：赵按趙14画、杰按傑12画" in messages[1]["content"]
    # The numbers reach the reader rendered from the calculation.
    assert "人格26" in outcome.text and "三才配置「土土火」" in outcome.text
    # Code asks the user to confirm the written form of 杰.
    advice = outcome.data["reading"]["advice"]
    assert advice[0].startswith(f"{CONFIRM}：赵杰的“杰”默认按傑12画")


async def test_two_names_are_calculated_once_each_and_named_in_every_fact(make):
    runtime, composer, events = make(lambda m: written(m, verdict="倾向A"))
    outcome = await runtime.turn(TWO)
    assert outcome.status == "submit_reading"
    assert planned(events) == ["start_reading", "analyze_name", "analyze_name", "submit_reading"]
    messages = composer.seen[0][0]
    assert "名字A：张伟；名字B：李娜" in messages[1]["content"]
    # With two names each placeholder renders with its name, so every claim is bound.
    assert "张伟的人格22" in outcome.text and "李娜的人格17" in outcome.text
    assert outcome.data["reading"]["verdict"] == "prefer_a"


async def test_a_compound_surname_is_split_as_one(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn("名字：欧阳子涵")
    assert outcome.status == "submit_reading"
    assert "人格20" in outcome.text


async def test_the_model_is_asked_only_when_code_finds_no_name(make):
    runtime, composer, events = make(extraction("李雷"), written)
    outcome = await runtime.turn("李雷的五格怎么样")
    assert outcome.status == "submit_reading"
    assert purposes(events) == ["intent", "compose"]
    stage = next(e for e in events if e.get("stage") == "extract")
    assert (stage["source"], stage["names"]) == ("model", 1)


async def test_a_name_not_in_the_users_words_is_never_analysed(make):
    runtime, _, events = make(extraction("李四"))
    outcome = await runtime.turn("这个人的五格怎么样")
    runtime.session.state["selected_systems"] = ["name"]
    assert outcome.status == "ask_user" and NO_NAME in outcome.text
    assert "analyze_name" not in planned(events)


async def test_the_profile_name_answers_my_name(make):
    runtime, *_ = make(written)
    runtime.session.profile = {**runtime.session.profile, "name": "张伟"}
    runtime.session.state["selected_systems"] = ["name"]
    outcome = await runtime.turn("看看我的名字五格怎么样")
    assert outcome.status == "submit_reading" and "人格22" in outcome.text


async def test_more_than_two_names_are_asked_to_narrow(make):
    runtime, _, events = make()
    outcome = await runtime.turn("比较“张伟”“李娜”“王小明”这三个名字")
    assert outcome.status == "ask_user" and TOO_MANY in outcome.text
    assert "analyze_name" not in planned(events)


async def test_a_wrong_number_is_caught_before_submission_and_repaired(make):
    runtime, composer, events = make(wrong_number, written)
    outcome = await runtime.turn(ONE)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert (info["repairs"], info["degraded"]) == (1, None)
    assert info["problems"][0] == ["赵杰的人格24与本次计算不符"]
    assert planned(events).count("submit_reading") == 1
    refused = next(event for event in events if event.get("stage") == "problems")
    assert "{{" in refused["text"]
    assert "{{" not in refused["rendered_text"]
    assert "人格26" in refused["rendered_text"]


async def test_fate_twice_degrades_to_the_conventions(make):
    runtime, *_ = make(fatal, fatal)
    outcome = await runtime.turn(TWO)
    assert outcome.status == "submit_reading"
    info = outcome.data["pipeline"]
    assert info["degraded"] == "keywords"
    assert "命运断言" in info["problems"][0][0]
    sections = outcome.data["reading"]["sections"]
    assert [s["title"] for s in sections] == ["张伟的五格与三才", "李娜的五格与三才"]
    assert "张伟的人格22" in sections[0]["body"] and "李娜的人格17" in sections[1]["body"]


async def test_a_character_without_strokes_is_asked_about(make, monkeypatch):
    import plugins.name.tools as tools

    monkeypatch.setattr(
        tools, "analyze", lambda surname, given, forms: {"status": "unknown", "unknown": ["杰"]}
    )
    runtime, _, events = make()
    outcome = await runtime.turn(ONE)
    assert outcome.status == "ask_user" and "“杰”" in outcome.text
    assert purposes(events) == []


@pytest.mark.parametrize(
    "message",
    [
        "用八字和“张伟”这个名字一起看看",
        "梦见有人叫张伟这个名字",
        "帮我给孩子起名，姓张",
        "张伟想改名叫张维，哪个好",
        "赵杰证件上写的是原字，五格怎么算",
        "今天天气不错",
    ],
)
async def test_messages_the_name_pipeline_leaves_to_the_agent_loop(make, message):
    runtime, *_ = make()
    assert Name(runtime).detect(runtime, message) is None


@pytest.mark.parametrize("message", ["刚才那个名字的人格是什么意思？", "外格为什么偏低？"])
async def test_a_follow_up_on_a_saved_name_stays_with_the_agent_loop(make, message):
    runtime, *_ = make(written)
    runtime.session.state["selected_systems"] = ["name"]
    assert (await runtime.turn(ONE)).status == "submit_reading"
    assert Name(runtime).detect(runtime, message) is None
    # A new name is a new reading.
    assert Name(runtime).detect(runtime, "再看看张伟这个名字").kind == "new"


async def test_the_name_page_routes_here(make):
    runtime, *_ = make()
    runtime.session.state["selected_systems"] = ["name"]
    assert Name(runtime).detect(runtime, "张伟").kind == "new"
    runtime.session.state["selected_systems"] = ["dream"]
    assert Name(runtime).detect(runtime, "看看张伟这个名字") is None


@pytest.mark.parametrize(
    ("message", "names"),
    [
        ("帮我看看张杰这个名字", ["张杰"]),
        ("张伟和李娜哪个名字好？", ["张伟", "李娜"]),
        ("比较张伟与李娜这两个名字", ["张伟", "李娜"]),
        ("我叫王小明", ["王小明"]),
        ("我朋友叫李雷，这个名字好吗", ["李雷"]),
        ("名字：欧阳子涵", ["欧阳子涵"]),
        ("欧阳子涵这个名字怎么样", ["欧阳子涵"]),
        ("分析一下王小明的名字", ["王小明"]),
        ("请问王小明的名字五格好吗", ["王小明"]),
        # A conjunction inside a name is kept when the name stands before 这个名字.
        ("你看看李一和这个名字", ["李一和"]),
        ("帮我看看“张伟”", ["张伟"]),
        # Misreadings code refuses; the model call or the profile answers these.
        ("看看我的名字五格怎么样", []),
        ("这个人的五格怎么样", []),
    ],
)
def test_code_reads_names_conservatively(message, names):
    assert Name.code_names(message, {}) == names


@pytest.mark.parametrize(
    ("message", "names"),
    [
        ("我叫王小明，想知道这个名字的三才配置说明什么。", ["王小明"]),
        ("我叫小明，这个名字怎么样", []),
        ("刘洋和刘阳这两个名字，五格上有什么区别？", ["刘洋", "刘阳"]),
        ("诸葛明月这个名字按五格分析如何？", ["诸葛明月"]),
    ],
)
def test_an_unquoted_name_starts_with_a_surname(message, names):
    assert Name.code_names(message, {}) == names


@pytest.mark.parametrize(
    "question",
    [
        "比较“张伟”和李娜这两个名字",
        "比较张伟和“李娜”这两个名字",
        "张伟和李娜这个名字哪个好？",
        "张伟这个名字和李娜哪个好？",
    ],
)
async def test_comparison_keeps_both_names_across_extraction_patterns(make, question):
    runtime, composer, events = make(lambda m: written(m, verdict="倾向A"))
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading"
    assert [r["full_name"] for r in Name.results(runtime.session.state)] == ["张伟", "李娜"]
    assert "名字A：张伟；名字B：李娜" in composer.seen[0][0][1]["content"]
    assert planned(events).count("analyze_name") == 2


@pytest.mark.parametrize(
    "question",
    [
        "比较张伟和李娜和王小明三个名字",
        "张伟这个名字、李娜这个名字和王小明哪个好？",
    ],
)
async def test_unquoted_comparison_over_limit_does_not_discard_a_person(make, question):
    runtime, _, events = make()
    outcome = await runtime.turn(question)
    assert outcome.status == "ask_user" and TOO_MANY in outcome.text
    assert "analyze_name" not in planned(events)


async def test_model_extraction_does_not_silently_cap_the_number_of_names(make):
    runtime, composer, events = make(extraction("陈思远", "李雷", "赵杰"))
    outcome = await runtime.turn("陈思远的五格、李雷的五格和赵杰的五格分别如何？")
    assert outcome.status == "ask_user" and TOO_MANY in outcome.text
    assert "不要截掉第三个" in composer.seen[0][0][0]["content"]
    assert "analyze_name" not in planned(events)


async def test_partial_comparison_asks_for_the_missing_name(make):
    runtime, _, events = make()
    outcome = await runtime.turn("比较张伟和另一个名字")
    assert outcome.status == "ask_user" and NO_NAME in outcome.text
    assert "analyze_name" not in planned(events)


@pytest.mark.parametrize(
    "question",
    [
        "“张伟”这个名字的“地格”怎么样？",
        "张伟这个名字怎么样？请称呼我“小明”",
        "张伟这个名字怎么样？请叫我“王哥”",
    ],
)
async def test_quoted_terms_and_nicknames_are_not_analysed_as_names(make, question):
    runtime, _, events = make(written)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading"
    assert [r["full_name"] for r in Name.results(runtime.session.state)] == ["张伟"]
    assert planned(events).count("analyze_name") == 1


async def test_another_persons_single_surname_does_not_change_a_later_reading(make):
    runtime, *_ = make(written, written)
    assert (await runtime.turn("我姓张，是单姓，看看张伟这个名字")).status == "submit_reading"
    outcome = await runtime.turn("再看看欧阳子涵这个名字")
    assert outcome.status == "submit_reading"
    (result,) = Name.results(runtime.session.state)
    assert (result["surname"], result["given"]) == ("欧阳", "子涵")
    assert result["grids"]["天格"] == 32 and result["grids"]["地格"] == 15


async def test_surname_instructions_are_local_to_each_name_in_a_comparison(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn("比较“欧阳明”（姓欧，单姓）和“欧阳子涵”（复姓欧阳）这两个名字")
    assert outcome.status == "submit_reading"
    first, second = Name.results(runtime.session.state)
    assert (first["surname"], first["given"]) == ("欧", "阳明")
    assert (second["surname"], second["given"]) == ("欧阳", "子涵")


async def test_an_explicit_compound_surname_is_not_a_single_surname_negation(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn("欧阳子涵这个名字不是单姓，是复姓欧阳，五格怎么样")
    assert outcome.status == "submit_reading"
    (result,) = Name.results(runtime.session.state)
    assert (result["surname"], result["given"]) == ("欧阳", "子涵")


async def test_explicit_single_surname_introduction_is_kept_across_commas(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn("我姓欧，是单姓，我叫欧阳明，这个名字的五格怎么样")
    assert outcome.status == "submit_reading"
    (result,) = Name.results(runtime.session.state)
    assert (result["surname"], result["given"]) == ("欧", "阳明")


@pytest.mark.parametrize(
    "question", ["比较“张伟明”和“张伟”这两个名字", "比较“张伟”和“张伟明”这两个名字"]
)
@pytest.mark.parametrize("degrade", [False, True])
async def test_names_that_share_a_prefix_can_submit_and_degrade(make, question, degrade):
    runtime, *_ = make(fatal, fatal) if degrade else make(written)
    outcome = await runtime.turn(question)
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["degraded"] == ("keywords" if degrade else None)
    assert "张伟明的三才配置「木木水」" in outcome.text
    assert "张伟的三才配置「木木木」" in outcome.text


@pytest.mark.parametrize(
    "question",
    [
        "赵杰这个名字就写杰，按8画计算五格",
        "赵杰这个名字不用繁体，算一下五格",
        "赵杰这个名字用杰8画，比较李娜这个名字",
    ],
)
async def test_explicit_written_forms_stay_with_the_agent_loop(make, question):
    runtime, *_ = make()
    assert Name(runtime).detect(runtime, question) is None


@pytest.mark.parametrize(
    "claim", ["人格二十三提示行动力。", "数理99代表坚毅。", "张伟的康熙总笔画99画。", "伟十二画。"]
)
async def test_wrong_chinese_grid_shuli_and_stroke_claims_are_repaired(make, claim):
    runtime, _, events = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn("张伟这个名字的五格怎么样？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 1
    assert outcome.data["pipeline"]["degraded"] is None
    assert claim not in outcome.text
    assert planned(events).count("submit_reading") == 1


async def test_correct_chinese_numbers_are_accepted(make):
    runtime, *_ = make(
        lambda m: written(m, extra="张伟的人格二十二，数理二十二，伟十一画，总笔画二十二画。")
    )
    outcome = await runtime.turn("张伟这个名字的五格怎么样？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 0


async def test_a_dream_character_inside_a_name_does_not_change_the_system(make):
    runtime, *_ = make(written)
    outcome = await runtime.turn("李梦瑶这个名字的五格怎么样？")
    assert outcome.status == "submit_reading"
    assert outcome.data["reading"]["systems_used"] == ["name"]


# ---- P2 r4: numbers that count something else are no grid values ----------------------------

R4_COUNTS = [
    "整体五格数理四吉一凶。",
    "人格是五格里最被看重的“自我与做事方式”那一格。",
    "人格、地格、总格三项都在传统所谓“吉”数里。",
    "三才是看天格、人格、地格三个位置尾数对应的五行关系。",
    "只有外格一项提示波折。",
    "名字的数理是一份自我观察的线索。",
]


async def test_the_r4_counted_numbers_are_not_read_as_grid_values(make):
    """r4 name_three_character#3 degraded twice on 外格一项 and 数理是一份 (and single ran
    out of retries on the other sentences): each was read as a wrong grid value."""
    text = "".join(R4_COUNTS)
    runtime, _, events = make(lambda m: written(m, extra=text))
    outcome = await runtime.turn("我叫王小明，想知道这个名字的三才配置说明什么。")
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize(
    "claim",
    [
        "另外人格24也很好。",
        "人格是二十四。",
        "人格24吉。",
        "总格五，",
        "人格二十四吉。",
        "人格二十四凶。",
        "数理二十四凶。",
        "人格二十四五行属火。",
        "人格二十四格。",
    ],
)
async def test_a_wrong_grid_value_is_still_caught_beside_counts(make, claim):
    text = "".join(R4_COUNTS) + claim
    runtime, *_ = make(lambda m: written(m, extra=text), written)
    outcome = await runtime.turn("我叫王小明，想知道这个名字的三才配置说明什么。")
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "与本次计算不符" in outcome.data["pipeline"]["problems"][0][0]


async def test_correct_chinese_values_and_genuine_counts_can_share_a_draft(make):
    text = (
        "人格二十二吉，数理二十二吉，人格二十二五行属木。总格二十三项仅指列表长度。数理四吉一凶。"
    )
    runtime, *_ = make(lambda m: written(m, extra=text))
    outcome = await runtime.turn("张伟这个名字的五格怎么样？")
    assert outcome.status == "submit_reading"
    assert outcome.data["pipeline"]["repairs"] == 0
    assert text in outcome.text


# ---- P2 r5: a lone numeral inside a word is no value (数理一般, 外格二者) --------------------

R5_WORDS = (
    "这个名字的数理一般被看作一种取名习俗，数理一致的地方可以多留意。"
    "数理一说只作参考，数理一共涉及五格。外格二者相近，外格两相比较，外格二人相同。"
    "人格十分重要。名字的数理是一面用于自我反思的镜子。"
)


async def test_a_lone_numeral_inside_a_word_is_not_a_grid_value(make):
    runtime, _, events = make(lambda m: written(m, extra=R5_WORDS))
    outcome = await runtime.turn("我叫王小明，想知道这个名字的三才配置说明什么。")
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None)
    assert R5_WORDS in outcome.text


@pytest.mark.parametrize("claim", ["总格五，", "人格五吉。", "人格五的含义。"])
async def test_a_lone_numeral_value_is_still_checked(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=R5_WORDS + claim), written)
    outcome = await runtime.turn("我叫王小明，想知道这个名字的三才配置说明什么。")
    assert outcome.data["pipeline"]["repairs"] == 1
    assert "与本次计算不符" in outcome.data["pipeline"]["problems"][0][0]


@pytest.mark.parametrize(
    "claim",
    ["人格为五属土。", "人格是十代表圆满。", "数理为一代表独立。", "外格为三属于吉数。"],
)
async def test_a_single_digit_before_a_predicate_is_still_a_value(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn("张伟这个名字的五格怎么样？")
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert "与本次计算不符" in info["problems"][0][0]
    assert claim not in outcome.text


# ---- P2 r6: a subject covering both names binds a shared value to each --------------------

COMPARE = "张伟和李娜，这两个名字从五格看哪个更好？"


def advising(advice):
    """Both names' layers, plus advice items that name neither of them."""
    items = "".join(f"- {item}\n" for item in advice)
    return lambda m: written(m).replace("【建议】\n", f"【建议】\n{items}")


async def test_the_r6_shared_outer_grid_passes_the_final_submission(make):
    """r6 name_compare_two#2: 张伟 and 李娜 both have 外格2."""
    advice = "补短板：两个名字都可留意外格2的提示，做计划时先把基础打扎实。"
    runtime, _, events = make(advising([advice]))
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert "两个名字都可留意外格2" in outcome.text
    assert planned(events).count("submit_reading") == 1


@pytest.mark.parametrize(
    "advice, problem",
    [
        # A shared subject binds every name, so the value must hold for each of them.
        ("留意：两个名字都可留意外格4。", "外格4与本次计算不符"),
        # 张伟's 人格 is 22, 李娜's is 17: another value in the same sentence is checked too.
        ("留意：两个名字都可留意外格2和人格22。", "李娜的人格22与本次计算不符"),
        ("留意：两人都是外格2，人格17。", "张伟的人格17与本次计算不符"),
        # A negated collective, a wrong count, or one in an earlier sentence binds nothing.
        ("留意：并非两个名字都要留意外格2。", "须写明是哪个名字"),
        ("留意：不是两个名字都要留意外格2。", "须写明是哪个名字"),
        ("留意：三个名字都可留意外格2。", "须写明是哪个名字"),
        ("留意：两个名字都不错。人格22值得留意。", "须写明是哪个名字"),
        # A claim before the collective is not covered by it.
        ("留意：外格2，两个名字都要留意。", "须写明是哪个名字"),
        # A full name written after the collective takes the claims back to that name.
        ("留意：两个名字都不错，李娜的人格22值得留意。", "李娜的人格22与本次计算不符"),
    ],
)
async def test_what_the_r6_collective_fix_must_still_refuse(make, advice, problem):
    runtime, *_ = make(advising([advice]), written)
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert problem in info["problems"][0][0], info["problems"]
    assert advice not in outcome.text


async def test_a_collective_alone_does_not_bind_a_single_name_reading(make):
    """With one name there is nothing to share: 两个名字 never widens what is checked."""
    runtime, *_ = make(advising(["留意：两个名字都可留意人格24。"]), written)
    outcome = await runtime.turn("张伟这个名字的五格怎么样？")
    info = outcome.data["pipeline"]
    assert info["repairs"] == 1
    assert "与本次计算不符" in info["problems"][0][0]


@pytest.mark.parametrize("negation", ["并非", "不是", "未必", "不"])
@pytest.mark.parametrize("subject", ["这两个名字", "那两个名字", "两人"])
async def test_pr49_a_demonstrative_cannot_hide_collective_negation(make, negation, subject):
    advice = f"留意：{negation}{subject}都外格2。"
    runtime, *_ = make(advising([advice]), written)
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert "须写明是哪个名字" in info["problems"][0][0]
    assert advice not in outcome.text


async def test_pr49_a_negated_collective_cancels_an_earlier_subject(make):
    advice = "两个名字都值得参考，但并非这两个名字都外格2。"
    runtime, *_ = make(advising([advice]), written)
    outcome = await runtime.turn(COMPARE)
    assert outcome.data["pipeline"]["repairs"] == 1


@pytest.mark.parametrize("subject", ["这两个名字", "那两人"])
async def test_pr49_an_affirmative_collective_keeps_its_shared_value(make, subject):
    advice = f"{subject}都可留意外格2。"
    runtime, *_ = make(advising([advice]))
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert advice in outcome.text


# ---- P2 r9: a label's colon between the shared subject and 都 -----------------------------


async def test_the_r9_colon_collective_passes_the_final_submission(make):
    """r9 name_compare_two#3: both drafts were refused, then degraded to keywords."""
    advice = "两个名字：都留意外格2数提示的基础与分工问题。"
    runtime, _, events = make(advising([advice]))
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert advice in outcome.text


@pytest.mark.parametrize(
    "advice, problem",
    [
        ("两个名字：都留意外格4。", "外格4与本次计算不符"),
        ("两个名字，都留意人格22。", "李娜的人格22与本次计算不符"),
        # Without 都 the label binds nothing; a negated one neither.
        ("两个名字：外格2。", "须写明是哪个名字"),
        ("并非两个名字：都要留意外格2。", "须写明是哪个名字"),
        # A full name written after the label takes the claim back to that name.
        ("两个名字：都不错，张伟的人格17值得留意。", "张伟的人格17与本次计算不符"),
    ],
)
async def test_what_the_r9_colon_fix_must_still_refuse(make, advice, problem):
    runtime, *_ = make(advising([advice]), written)
    outcome = await runtime.turn(COMPARE)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert problem in info["problems"][0][0], info["problems"]
    assert advice not in outcome.text


# ---- P2 r9 (single): 三者 counts grids; an arithmetic expression states its result --------

CHEN = "陈思远这个名字的五格怎么样？"


@pytest.mark.parametrize(
    "claim",
    [
        # r9 name_compound_surname#1 / name_career_grid#2.
        "三才指天格、人格、地格三者尾数对应的五行。",
        # r9 name_without_lead_in#3: 天格17 + 地格26 − 人格25 = 外格18.
        "外格由天格加地格减人格得18。",
        "天格加地格减人格得18。",
    ],
)
async def test_the_r9_single_false_rejections_pass(make, claim):
    runtime, _, events = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert claim in outcome.text


@pytest.mark.parametrize(
    "claim",
    [
        # A wrong result, or a subject grid that is not the result, is still refused.
        "外格由天格加地格减人格得19。",
        "人格由天格加地格减人格得18。",
        "天格加地格得42。",
        # The expression does not cover a separate claim after it, nor a lone numeral.
        "外格由天格加地格减人格得18，人格18。",
        "地格三。",
    ],
)
async def test_what_the_r9_single_fixes_must_still_refuse(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 1, None)
    assert "与本次计算不符" in info["problems"][0][0], info["problems"]
    assert claim not in outcome.text


# ---- P2 r10: 一套 counts, and the repair quotes the sentence -------------------------------


async def test_the_r10_counted_set_passes_the_final_submission(make):
    """r10 name_without_lead_in#2: 数理是一套… was read as 数理1, twice, then degraded."""
    claim = "五格数理是一套民间取名习俗，可当自我反思的镜子，路怎么走仍在自己脚下。"
    runtime, *_ = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"], info["degraded"]) == ("submit_reading", 0, None), info[
        "problems"
    ]
    assert claim in outcome.text


@pytest.mark.parametrize("claim", ["数理是一。", "陈思远的数理1。", "人格一。"])
async def test_what_the_r10_counter_fix_must_still_refuse(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 1)
    assert "与本次计算不符" in info["problems"][0][0]


async def test_a_name_repair_quotes_the_sentence_with_the_wrong_value(make):
    claim = "另外人格24也很好。"
    runtime, composer, _ = make(lambda m: written(m, extra=claim), written)
    await runtime.turn(CHEN)
    request = composer.seen[1][0][-1]["content"]
    assert "出问题的句子：" in request and "人格24也很好。" in request


# ---- PR #53 review F3: 点 counts only in 一点, and grids have no decimals --------------------


@pytest.mark.parametrize(
    "claim, problem",
    [
        # The review's cases: a decimal is refused before its whole part is compared.
        ("陈思远的人格二十四点五。", "小数"),
        ("陈思远的数理二十四点五。", "小数"),
        ("人格一点五。", "小数"),
        # The right whole part does not save a decimal.
        ("陈思远的人格二十五点五。", "小数"),
        ("人格25.5。", "小数"),
    ],
)
async def test_what_the_pr53_counter_review_must_refuse(make, claim, problem):
    runtime, *_ = make(lambda m: written(m, extra=claim), written)
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 1)
    assert problem in info["problems"][0][0], info["problems"]
    assert claim not in outcome.text


@pytest.mark.parametrize(
    "claim", ["人格一点也不差。", "数理是一些人的参考。", "人格25，点评如下。"]
)
async def test_whole_counting_words_still_pass(make, claim):
    runtime, *_ = make(lambda m: written(m, extra=claim))
    outcome = await runtime.turn(CHEN)
    info = outcome.data["pipeline"]
    assert (outcome.status, info["repairs"]) == ("submit_reading", 0), info["problems"]
