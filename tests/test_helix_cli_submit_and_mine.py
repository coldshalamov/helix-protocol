import pytest
import blockchain as bc

pytest.importorskip("nacl")

from helix import helix_cli, event_manager, helix_node


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_submit_and_mine(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def fake_mine(ev, max_depth=4):
        enc = bytes([1, 1]) + b"a"
        event_manager.accept_mined_seed(ev, 0, enc)
        return 1, 0.0

    monkeypatch.setattr(helix_node, "mine_microblocks", fake_mine)

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
