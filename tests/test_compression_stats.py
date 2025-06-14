import pytest

pytest.importorskip("nacl")

from helix import event_manager
from helix.ledger import compression_stats


def test_compression_stats(tmp_path):
    events_dir = tmp_path / "events"
    event = event_manager.create_event("abcd", microblock_size=2)
    for idx, block in enumerate(event["microblocks"]):
        event_manager.accept_mined_seed(event, idx, b"a", 1)
    event_manager.save_event(event, str(events_dir))

    saved, hlx = compression_stats(str(events_dir))
    assert saved == event["header"]["block_count"]
    assert hlx == pytest.approx(sum(event["rewards"]))
