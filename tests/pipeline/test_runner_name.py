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
