import math
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_split_and_reassemble():
    statement = "Hello Helix"
    blocks, count, length = em.split_into_microblocks(statement, microblock_size=4)
    assert count == math.ceil(len(statement.encode("utf-8")) / 4)
    assert length == len(statement.encode("utf-8"))
    assert all(len(b) == 4 for b in blocks)
    assert em.reassemble_microblocks(blocks) == statement
    merkle_root, tree = em.build_merkle_tree(blocks)
    assert merkle_root == tree[-1][0]


def test_event_closure():
    statement = "Closure test"
    event = em.create_event(statement, microblock_size=4)
    assert "merkle_root" in event["header"]
    assert event["is_closed"] is False
    for i in range(event["header"]["block_count"]):
        em.mark_mined(event, i)
    assert event["is_closed"] is True


def test_accept_block_size_seed():
    event = em.create_event("ab", microblock_size=2)
    seed = b"xy"
    encoded = bytes([1, len(seed)]) + seed
    refund = em.accept_mined_seed(event, 0, encoded)
    assert refund == 0
    hdr = event["seeds"][0][0]
    l = event["seeds"][0][1]
    assert event["seeds"][0][2 : 2 + l] == seed


def test_reject_oversize_seed():
    event = em.create_event("ab", microblock_size=2)
    with pytest.raises(ValueError):
        em.accept_mined_seed(event, 0, bytes([1, 7]) + b"toolong")


def test_mint_uncompressed_seeds():
    event = em.create_event("abcd", microblock_size=2)
    em.mint_uncompressed_seeds(event)
    assert all(event["mined"])
    assert all(event["mined_status"])
    for idx, block in enumerate(event["microblocks"]):
        assert event["seeds"][idx] == [block]
    assert event["is_closed"]
