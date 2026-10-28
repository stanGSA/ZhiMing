import json

import pytest

from harness.json_arguments import parse_arguments


def test_unescaped_prose_quotes_are_preserved_inside_the_value():
    raw = '{"body": "起运，白话就是"人生阶段的分段线"从这里开始。", "ref_ids": ["R1"]}'
    value, repaired = parse_arguments(raw)
    assert repaired
    assert value == {"body": '起运，白话就是"人生阶段的分段线"从这里开始。', "ref_ids": ["R1"]}


@pytest.mark.parametrize(
    "raw",
    [
        '{"body":"已正确转义\\"引用\\"，中文“引号”正常。"}',
        '{"n":2,"items":["甲","乙"],"empty":null}',
    ],
)
def test_valid_json_is_unchanged(raw):
    assert parse_arguments(raw) == (json.loads(raw), False)


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        '{"body":"输出截断',
        '{"body":"a" "other":1}',
        '{"body":"a", "ref_ids":["R1"]',
        "[1,2]",
        '{"body":"a"broken"}',
    ],
)
def test_structural_or_ambiguous_damage_is_not_completed(raw):
    with pytest.raises((ValueError, TypeError)):
        parse_arguments(raw)
