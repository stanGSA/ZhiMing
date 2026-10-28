"""The model boundary offers only references the reading can cite, and says how to fix others."""

import json

from common.schemas import LOOKUP_KINDS, Reading
from common.validation import citation_error
from harness.guard import json_error_detail
from harness.refs import constrain, transform
from harness.session import Session


def reading_session(*citable):
    session = Session("boundary")
    session.state.update(allowed_refs=set(citable), kb_refs={"kb:tarot:card:x@v1"})
    return session


def test_uncitable_references_are_hidden_not_numbered():
    session = reading_session("tarot:r:pos1:x")
    value = {
        "cards": [
            {"ref_id": "tarot:r:pos1:x", "meaning": {"text": "t", "ref_id": "kb:tarot:card:x@v1"}}
        ],
        "tensions": [{"ref_ids": ["kb:tarot:card:x@v1", "tarot:r:pos1:x"]}],
    }
    shown = transform(value, session)
    assert shown == {
        "cards": [{"ref_id": "R1", "meaning": {"text": "t"}}],
        "tensions": [{"ref_ids": ["R1"]}],
    }
    assert session.state["ref_alias"] == {"R1": "tarot:r:pos1:x"}
    # Restoring the model's arguments is unchanged, and full results are never edited.
    assert transform({"ref_id": "R1"}, session, restore=True) == {"ref_id": "tarot:r:pos1:x"}
    assert value["cards"][0]["meaning"]["ref_id"] == "kb:tarot:card:x@v1"


def test_sessions_without_a_reading_number_every_reference():
    session = Session("no-reading")
    assert transform({"ref_id": "kb:x"}, session) == {"ref_id": "R1"}


def test_submission_schema_lists_seen_citable_references():
    session = reading_session("tarot:r:pos1:x", "tarot:r:pos2:y", "tarot:r:pos3:z")
    session.state["ref_alias"] = {
        "R1": "tarot:old:pos1:a",
        "R2": "tarot:r:pos2:y",
        "R3": "tarot:r:pos1:x",
    }
    original = Reading.model_json_schema()
    schema = constrain(original, session)
    definitions = schema["$defs"]
    # Seen and citable, in alias order; the unseen pos3 and the old reading's R1 are not offered.
    assert definitions["Evidence"]["properties"]["ref_id"]["enum"] == ["R2", "R3"]
    assert definitions["Section"]["properties"]["ref_ids"]["items"]["enum"] == ["R2", "R3"]
    assert "enum" not in original["$defs"]["Evidence"]["properties"]["ref_id"]
    assert constrain(original, Session("empty")) is original


def test_citation_error_lists_every_problem_and_the_citable_facts():
    session = reading_session("tarot:r:pos1:x", "tarot:r:pos2:y")
    session.state["ref_alias"] = {
        "R1": "tarot:r:pos1:x",
        "R2": "kb:tarot:card:x@v1",
        "R3": "tarot:old:pos1:a",
    }
    cited = [
        ("evidence.0.ref_id", "tarot:r:pos1:x", True),
        ("evidence.1.ref_id", "kb:tarot:card:x@v1", True),
        ("sections.0.ref_ids.0", "tarot:old:pos1:a", False),
        ("sections.0.ref_ids.1", "R9", False),
    ]
    error = citation_error(
        session, cited, session.state["allowed_refs"], {"tarot:r:pos1:x": "过去：【A】正位。"}
    )
    assert "evidence.1.ref_id=R2是知识库释义条目，不是本次计算事实" in error
    assert "sections.0.ref_ids.0=R3不属于本次记录的计算事实" in error
    assert "sections.0.ref_ids.1=R9不是工具返回过的编号" in error
    assert "evidence.0" not in error
    # The unseen citable fact gets the next number, so the model can use it.
    assert error.endswith("本次可引用：R1（过去：【A】正位。）、R4。")
    assert session.state["ref_alias"]["R4"] == "tarot:r:pos2:y"
    assert (
        citation_error(session, cited[:1], session.state["allowed_refs"], {"tarot:r:pos1:x": "x"})
        is None
    )


def test_evidence_without_rendered_text_is_named():
    session = reading_session("tarot:r:pos1:x")
    error = citation_error(
        session, [("evidence.0.ref_id", "tarot:r:pos1:x", True)], {"tarot:r:pos1:x"}
    )
    assert "evidence.0.ref_id=R1没有可渲染的事实文本" in error


def test_json_error_points_at_the_break_and_the_unescaped_quote():
    raw = '{"summary": "你感到的"停滞"其实是信号", "evidence": []}'
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        detail = json_error_detail(exc)
    assert '你感到的"停滞' in detail
    assert '英文双引号须写成\\"' in detail
    try:
        json.loads('{"a": 1,}')
    except json.JSONDecodeError as exc:
        assert "双引号须写成" not in json_error_detail(exc)


def test_lookup_kinds_match_the_knowledge_base(runtime):
    built = runtime.kb.db.execute("SELECT DISTINCT system, kind FROM entries").fetchall()
    assert {(system, kind) for system, kinds in LOOKUP_KINDS.items() for kind in kinds} == set(
        built
    )


def test_unknown_kind_for_a_system_gets_the_valid_ones(runtime):
    lookup = runtime.registry.tools["lookup_meaning"]
    args = lookup.input_model(system="tarot", kind="sign", key="Aries")
    result = lookup.handler(args, runtime.session)
    assert result.code == "missing_entry"
    assert "tarot的kind只能是card、position" in result.error
