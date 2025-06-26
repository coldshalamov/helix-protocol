import pytest

pytest.importorskip("nacl")

pytest.skip("reassemble command removed", allow_module_level=True)

from helix import helix_cli as cli, event_manager as em


def test_cli_reassemble(tmp_path, capsys):
    event = em.create_event("CLI reassemble test", microblock_size=4)
    path = em.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    cli.main(["reassemble-statement", "--event-id", evt_id])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "CLI reassemble test"

    cli.main(["reassemble-statement", "--path", path])
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "CLI reassemble test"
