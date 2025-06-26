import pytest
import blockchain as bc

pytest.importorskip("nacl")

import pytest

from helix import helix_cli, event_manager


pytest.skip("finalize command removed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_finalize_cli(tmp_path, capsys, monkeypatch):
    event = event_manager.create_event("finalize cli", microblock_size=4)
    enc = bytes([1, 1]) + b"a"
    event_manager.accept_mined_seed(event, 0, enc)
    event_manager.save_event(event, str(tmp_path / "events"))
    capsys.readouterr()
    evt_id = event["header"]["statement_id"]

    monkeypatch.chdir(tmp_path)
    helix_cli.main(["finalize", evt_id])
    out = capsys.readouterr().out.strip()
    assert "statement verified" in out.lower()

    chain = bc.load_chain(str(tmp_path / "blockchain.jsonl"))
    assert chain and chain[-1]["event_ids"][0] == evt_id
