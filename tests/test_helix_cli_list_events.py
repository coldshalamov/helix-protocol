import pytest

pytest.importorskip("nacl")

from helix import helix_cli, event_manager


def test_list_events(tmp_path, capsys):
    e1 = event_manager.create_event("first", microblock_size=4)
    event_manager.save_event(e1, str(tmp_path / "events"))

    e2 = event_manager.create_event("second", microblock_size=4)
    event_manager.mark_mined(e2, 0)
    event_manager.save_event(e2, str(tmp_path / "events"))
    capsys.readouterr()  # clear output from mark_mined

    helix_cli.main(["list-events", "--data-dir", str(tmp_path)])
    out_lines = capsys.readouterr().out.strip().splitlines()
    sid1 = e1["header"]["statement_id"]
    sid2 = e2["header"]["statement_id"]
    assert f"{sid1} closed=False 0/1" in out_lines
    assert f"{sid2} closed=True 1/1" in out_lines

    helix_cli.main(["list-events", "--data-dir", str(tmp_path), "--show-statement"])
    out = capsys.readouterr().out
    assert "first" in out and "second" in out


def test_list_events_no_dir(tmp_path):
    with pytest.raises(SystemExit):
        helix_cli.main(["list-events", "--data-dir", str(tmp_path / "nodir")])
