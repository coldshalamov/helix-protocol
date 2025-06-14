import os
import sys
import pytest

# ensure project root is on path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

pytest.importorskip("nacl")

from helix import event_manager, minihelix


def test_simulated_mining():
    statement = "abc"
    event = event_manager.create_event(statement, microblock_size=3)
    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block, max_attempts=100000)
        assert seed is not None
        assert minihelix.verify_seed(seed, block)
        event["seeds"][idx] = {"seed": seed, "depth": 1}
        event_manager.mark_mined(event, idx)
    assert event["is_closed"]
    final = event_manager.reassemble_microblocks(event["microblocks"])
    assert final == statement
