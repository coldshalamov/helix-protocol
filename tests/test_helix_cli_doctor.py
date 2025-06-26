import json
from pathlib import Path
import pytest

pytest.importorskip("nacl")

import pytest

from helix import helix_cli, event_manager, signature_utils


pytest.skip("doctor command removed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(event_manager.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_helix_cli_doctor_missing_genesis(tmp_path, capsys):
    helix_cli.main(["doctor", "--data-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "genesis.json not found" in out


def test_helix_cli_doctor_invalid_hash(tmp_path, capsys):
    (tmp_path / "genesis.json").write_text("{}")
    helix_cli.main(["doctor", "--data-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "hash mismatch" in out


def test_helix_cli_doctor_summary(tmp_path, capsys):
    genesis_src = Path("genesis.json")
    (tmp_path / "genesis.json").write_bytes(genesis_src.read_bytes())

    pub, priv = signature_utils.generate_keypair()
    wallet = tmp_path / "wallet.txt"
    signature_utils.save_keys(str(wallet), pub, priv)
    with open(tmp_path / "balances.json", "w", encoding="utf-8") as f:
        json.dump({pub: 50}, f)

    event1 = event_manager.create_event("ab", microblock_size=1)
    event_manager.save_event(event1, str(tmp_path / "events"))

    event2 = event_manager.create_event("c", microblock_size=2)
    event_manager.accept_mined_seed(event2, 0, [b"a"])
    event_manager.save_event(event2, str(tmp_path / "events"))

    chain_data = [{"block_id": "b1", "parent_id": "genesis", "timestamp": 123}]
    (tmp_path / "chain.json").write_text(json.dumps(chain_data))

    helix_cli.main(["doctor", "--data-dir", str(tmp_path)])
    out = capsys.readouterr().out

    assert "Mined microblocks: 1" in out
    assert "Unmined microblocks: 2" in out
    assert "Wallet balance: 50" in out
    assert "Latest block: 0 123" in out
