from harness.budget import Budget


def test_dispatch_limit_is_shared_by_siblings_and_denial_does_not_consume_child_slot():
    root = Budget(10000, max_model_calls=2)
    first = root.child(5000)
    second = root.child(5000)
    assert first.start_model_call()
    assert second.start_model_call()
    assert not first.start_model_call()
    assert (root.model_calls, first.model_calls, second.model_calls) == (2, 1, 1)


def test_child_limit_does_not_consume_parent_slot_when_denied():
    root = Budget(10000)
    child = root.child(5000)
    child.max_model_calls = 0
    assert not child.start_model_call()
    assert root.model_calls == child.model_calls == 0
