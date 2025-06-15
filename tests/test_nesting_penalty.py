import pytest

pytest.importorskip("nacl")

from helix import event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_accept_mined_seed_replacement():
    event = event_manager.create_event("abc", microblock_size=3)
    enc = event_manager.nested_miner.encode_header(3, 1) + b"a"
    refund = event_manager.accept_mined_seed(event, 0, enc)
    assert refund == 0
    assert event["seed_depths"][0] == 3
    assert event["penalties"][0] == 2
    original_reward = event["rewards"][0]

    refund = event_manager.accept_mined_seed(event, 0, enc)
    expected_reward = event_manager.compute_reward(b"a", 3)
    assert refund == pytest.approx(original_reward - expected_reward)
    assert event["seed_depths"][0] == 2
    assert event["penalties"][0] == 1
    assert event["refunds"][0] == refund
    assert event["rewards"][0] == expected_reward


def test_accept_mined_seed_shorter_replacement():
    event = event_manager.create_event("abc", microblock_size=3)
    enc_long = event_manager.nested_miner.encode_header(2, 4) + b"long" + b"inter"
    event_manager.accept_mined_seed(event, 0, enc_long)
    original_reward = event["rewards"][0]

    enc_a = event_manager.nested_miner.encode_header(5, 1) + b"a"
    refund = event_manager.accept_mined_seed(event, 0, enc_a)
    expected_reward = event_manager.compute_reward(b"a", 3)
    hdr = event["seeds"][0][0]
    _, l = event_manager.nested_miner.decode_header(hdr)
    assert event["seeds"][0][1 : 1 + l] == b"a"
    assert event["seed_depths"][0] == 5
    assert refund == pytest.approx(original_reward - expected_reward)
    assert event["refunds"][0] == refund


def test_accept_mined_seed_conditions():
    event = event_manager.create_event("abc", microblock_size=3)
    base = event_manager.nested_miner.encode_header(2, 1) + b"a"
    event_manager.accept_mined_seed(event, 0, base)
    # different length should not replace
    refund = event_manager.accept_mined_seed(event, 0, event_manager.nested_miner.encode_header(2, 2) + b"bb")
    assert refund == 0
    hdr = event["seeds"][0][0]
    _, l = event_manager.nested_miner.decode_header(hdr)
    assert event["seeds"][0][1 : 1 + l] == b"a"
    # higher depth should not replace
    refund = event_manager.accept_mined_seed(event, 0, event_manager.nested_miner.encode_header(3, 1) + b"c")
    assert refund == 0
    assert event["seed_depths"][0] == 2
    # same depth should not replace
    refund = event_manager.accept_mined_seed(event, 0, event_manager.nested_miner.encode_header(2, 1) + b"d")
    assert refund == 0
    hdr = event["seeds"][0][0]
    _, l = event_manager.nested_miner.decode_header(hdr)
    assert event["seeds"][0][1 : 1 + l] == b"a"
