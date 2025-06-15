import json
import pytest

pytest.importorskip("nacl")

from helix import helix_cli, event_manager


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_view_chain(tmp_path, capsys):
    event = event_manager.create_event("data", microblock_size=4)
    enc = bytes([1, 1]) + b"a"
    event_manager.accept_mined_seed(event, 0, enc)
    event_manager.save_event(event, str(tmp_path / "events"))
    capsys.readouterr()  # clear output from mark_mined

    evt_id = event["header"]["statement_id"]
    chain_data = [{"block_id": "b1", "parent_id": "genesis", "event_ids": [evt_id]}]
    (tmp_path / "chain.json").write_text(json.dumps(chain_data))

    helix_cli.main(["view-chain", "--data-dir", str(tmp_path), "--summary"])
    out = capsys.readouterr().out.strip()
    assert f"0 {evt_id} b1 1" in out
