import pytest

pytest.importorskip("nacl")

from helix import cli, event_manager as em


def test_cli_reassemble(tmp_path, capsys):
    event = em.create_event("CLI reassemble test", microblock_size=4)
    path = em.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    cli.main(["--data-dir", str(tmp_path), "reassemble", "--event-id", evt_id])
    out = capsys.readouterr().out.strip()
    assert out.endswith("CLI reassemble test")

    cli.main(["reassemble", "--path", path])
    out = capsys.readouterr().out.strip()
    assert out.endswith("CLI reassemble test")
