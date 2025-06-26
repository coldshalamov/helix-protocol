import pytest

pytest.importorskip("nacl")

from helix import event_manager
from helix.ledger import compression_stats


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_compression_stats(tmp_path):
    events_dir = tmp_path / "events"
    event = event_manager.create_event("abcd", microblock_size=2)
    for idx, block in enumerate(event["microblocks"]):
        enc = bytes([1, 1]) + b"a"
        event_manager.accept_mined_seed(event, idx, enc)
    event_manager.save_event(event, str(events_dir))

    saved, hlx = compression_stats(str(events_dir))
    assert saved == 0
    assert hlx == pytest.approx(sum(event["rewards"]))
