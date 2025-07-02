import json
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_finalized_log_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    event = em.create_event("log", microblock_size=5)
    for idx in range(event["header"]["block_count"]):
        em.accept_mined_seed(event, idx, bytes([1, 1]) + b"a", miner="MINER")

    assert event.get("finalized")

    log_file = tmp_path / "finalized_log.jsonl"
    assert log_file.exists()

    entry = json.loads(log_file.read_text().splitlines()[-1])
    assert entry["block_id"] == event["block_header"]["block_id"]
    assert entry["statement_id"] == event["header"]["statement_id"]
    assert entry["miner_id"] == "MINER"
    assert entry["delta_seconds"] == event["block_header"]["delta_seconds"]
    assert entry["compression_reward"] == event["miner_reward"]
