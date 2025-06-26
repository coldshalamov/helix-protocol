import pytest

pytest.importorskip("nacl")

from helix import event_manager, minihelix


def test_simulated_mining():
    statement = "abc"
    event = event_manager.create_event(statement, microblock_size=3)
    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block, max_attempts=100000)
        assert seed is not None
        assert minihelix.verify_seed(seed, block)
        enc = bytes([1, len(seed)]) + seed
        event_manager.accept_mined_seed(event, idx, enc)
    assert event["is_closed"]
    final = event_manager.reassemble_microblocks(event["microblocks"])
    assert final == statement
