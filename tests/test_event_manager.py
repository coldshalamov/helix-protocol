import math
import pytest

pytest.importorskip("nacl")
pytest.skip("legacy microblock logic removed", allow_module_level=True)

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


def test_event_closure():
    statement = "Closure test"
    event = em.create_event(statement, microblock_size=4)
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
    em.accept_mined_seed(event, 0, bytes([1, 7]) + b"toolong")
    assert event["seeds"][0] is not None


def test_mock_mining_closes_event():
    event = em.create_event("abcd", microblock_size=2)
    for idx, _ in enumerate(event["microblocks"]):
        em.accept_mined_seed(event, idx, [b"a"])
    assert all(event["mined_status"])
    assert event["is_closed"]
