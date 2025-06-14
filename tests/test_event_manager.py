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
    refund = em.accept_mined_seed(event, 0, [seed])
    assert refund == 0
    assert event["seeds"][0] == seed


def test_reject_oversize_seed():
    event = em.create_event("ab", microblock_size=2)
    with pytest.raises(ValueError):
        em.accept_mined_seed(event, 0, [b"toolong"])
