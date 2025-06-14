import math
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


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
