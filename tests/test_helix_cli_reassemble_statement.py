import pytest

pytest.importorskip("nacl")

from helix import helix_cli, event_manager


def test_reassemble_statement(tmp_path, capsys, monkeypatch):
    event = event_manager.create_event("Reassemble CLI test", microblock_size=4)
    path = event_manager.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    monkeypatch.chdir(tmp_path)
    helix_cli.main(["reassemble-statement", "--event-id", evt_id])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "Reassemble CLI test"

    helix_cli.main(["reassemble-statement", "--path", path])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "Reassemble CLI test"
