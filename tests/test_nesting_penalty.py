import pytest

pytest.importorskip("nacl")

from helix import event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_accept_mined_seed_replacement():
    event = event_manager.create_event("abc", microblock_size=3)
    refund = event_manager.accept_mined_seed(event, 0, [b"a"])
    assert refund == 0
    assert event["seed_depths"][0] == 3
    assert event["penalties"][0] == 2
    original_reward = event["rewards"][0]

    refund = event_manager.accept_mined_seed(event, 0, [b"a"])
    expected_reward = event_manager.reward_for_depth(2)
    assert refund == pytest.approx(original_reward - expected_reward)
    assert event["seed_depths"][0] == 2
    assert event["penalties"][0] == 1
    assert event["refunds"][0] == refund
    assert event["rewards"][0] == expected_reward


def test_accept_mined_seed_shorter_replacement():
    event = event_manager.create_event("abc", microblock_size=3)
    event_manager.accept_mined_seed(event, 0, [b"long", b"inter"])
    original_reward = event["rewards"][0]

    refund = event_manager.accept_mined_seed(event, 0, [b"a"])
    expected_reward = event_manager.reward_for_depth(5)
    assert event["seeds"][0] == b"a"
    assert event["seed_depths"][0] == 5
    assert refund == pytest.approx(original_reward - expected_reward)
    assert event["refunds"][0] == refund


def test_accept_mined_seed_conditions():
    event = event_manager.create_event("abc", microblock_size=3)
    event_manager.accept_mined_seed(event, 0, [b"a"])
    # different length should not replace
    refund = event_manager.accept_mined_seed(event, 0, [b"bb"])
    assert refund == 0
    assert event["seeds"][0] == b"a"
    # higher depth should not replace
    refund = event_manager.accept_mined_seed(event, 0, [b"c"])
    assert refund == 0
    assert event["seed_depths"][0] == 2
    # same depth should not replace
    refund = event_manager.accept_mined_seed(event, 0, [b"d"])
    assert refund == 0
    assert event["seeds"][0] == b"a"
