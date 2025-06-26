import pytest

pytest.importorskip("nacl")

import pytest

from helix import helix_cli, event_manager, helix_node


pytest.skip("mine command removed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_cli_mine_event(tmp_path, monkeypatch, capsys):
    event = event_manager.create_event("ab", microblock_size=2)
    event_manager.save_event(event, str(tmp_path / "events"))
    evt_id = event["header"]["statement_id"]

    def fake_mine(ev, max_depth=4):
        enc = bytes([1, 1]) + b"a"
        event_manager.accept_mined_seed(ev, 0, enc)
        return 1, 0.0

    monkeypatch.setattr(helix_node, "mine_microblocks", fake_mine)

    helix_cli.main(["mine", evt_id, "--data-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "Blocks mined: 1" in out

    reloaded = event_manager.load_event(str(tmp_path / "events" / f"{evt_id}.json"))
    assert reloaded["is_closed"]
