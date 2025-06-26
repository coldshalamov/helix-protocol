import pytest
import blockchain as bc

pytest.importorskip("nacl")

import pytest

from helix import helix_cli, event_manager


pytest.skip("submit-and-mine command removed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_submit_and_mine(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(helix_cli.miner, "find_seed", lambda b: b"a")
    monkeypatch.setattr(helix_cli.minihelix, "verify_seed", lambda s, b: True)

    statement = "ab"
    helix_cli.main(["submit-and-mine", statement, "--block-size", "2"])
    out = capsys.readouterr().out
    evt_id = event_manager.sha256(statement.encode("utf-8"))
    chain = bc.load_chain(str(tmp_path / "blockchain.jsonl"))
    assert chain and chain[-1]["event_ids"][0] == evt_id
    evt_file = tmp_path / "events" / f"{evt_id}.json"
    assert evt_file.exists()
    event = event_manager.load_event(str(evt_file))
    assert event.get("is_closed")
