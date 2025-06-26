import pytest

pytest.importorskip("nacl")

import pytest

from helix import helix_cli as cli, event_manager


pytest.skip("view-event command removed", allow_module_level=True)


def test_cli_view_event(tmp_path, capsys):
    event = event_manager.create_event("demo event", microblock_size=8)
    event_manager.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    cli.main(["--data-dir", str(tmp_path), "view-event", evt_id])
    out = capsys.readouterr().out
    assert "Statement: demo event" in out
    assert "Status: open" in out
    assert "Microblocks: 0/2" in out
    assert "Microblock Details:" in out
    assert "Merkle Proof:" in out
    assert "Votes: YES=0 NO=0" in out

    for i in range(event["header"]["block_count"]):
        event_manager.mark_mined(event, i)
    event["bets"]["YES"].append({"amount": 10})
    event["bets"]["NO"].append({"amount": 5})
    event["payouts"] = {"A": 1.0}
    event_manager.save_event(event, str(tmp_path / "events"))

    cli.main(["--data-dir", str(tmp_path), "view-event", evt_id])
    out = capsys.readouterr().out
    assert "Status: resolved" in out
    assert "Resolution: YES" in out
    assert "Rewards:" in out
    assert '"A": 1.0' in out
