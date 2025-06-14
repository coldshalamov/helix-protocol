import pytest

pytest.importorskip("nacl")

from helix import event_manager


def test_accept_mined_seed_replacement():
    event = event_manager.create_event("abc", microblock_size=3)
    refund = event_manager.accept_mined_seed(event, 0, b"a", 3)
    assert refund == 0
    assert event["seed_depths"][0] == 3
    assert event["penalties"][0] == 2
    original_reward = event["rewards"][0]

    refund = event_manager.accept_mined_seed(event, 0, b"a", 2)
    assert refund > 0
    assert event["seed_depths"][0] == 2
    assert event["penalties"][0] == 1
    assert event["refunds"][0] == refund
    assert event["rewards"][0] < original_reward


def test_accept_mined_seed_conditions():
    event = event_manager.create_event("abc", microblock_size=3)
    event_manager.accept_mined_seed(event, 0, b"a", 2)
    # different length should not replace
    refund = event_manager.accept_mined_seed(event, 0, b"bb", 1)
    assert refund == 0
    assert event["seeds"][0] == b"a"
    # higher depth should not replace
    refund = event_manager.accept_mined_seed(event, 0, b"c", 3)
    assert refund == 0
    assert event["seed_depths"][0] == 2
