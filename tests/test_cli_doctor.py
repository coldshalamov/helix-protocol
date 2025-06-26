from pathlib import Path
import pytest

pytest.importorskip("nacl")

import pytest

from helix import helix_cli as cli, event_manager


pytest.skip("doctor command removed", allow_module_level=True)


def test_doctor_missing_genesis(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["--data-dir", str(tmp_path), "doctor"])
    out = capsys.readouterr().out
    assert "genesis.json not found" in out


def test_doctor_invalid_hash(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "genesis.json").write_text("{}")
    cli.main(["--data-dir", str(tmp_path), "doctor"])
    out = capsys.readouterr().out
    assert "hash mismatch" in out


def test_doctor_unmined_and_wallet(tmp_path, capsys, monkeypatch):
    genesis_src = Path("genesis.json")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "genesis.json").write_bytes(genesis_src.read_bytes())
    # leave wallet missing to trigger warning
    event = event_manager.create_event("diag", microblock_size=2)
    event_manager.save_event(event, str(tmp_path / "events"))
    cli.main(["--data-dir", str(tmp_path), "doctor"])
    out = capsys.readouterr().out
    assert "no wallet file" in out
    assert "unmined events detected" in out
    assert event["header"]["statement_id"] in out
