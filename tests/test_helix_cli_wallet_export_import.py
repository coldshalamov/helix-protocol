import json
import base64

import pytest

pytest.importorskip("nacl")

from helix import helix_cli, signature_utils, ledger


def test_export_import_wallet(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pub, priv = signature_utils.generate_keypair()
    wallet_file = tmp_path / "wallet.txt"
    signature_utils.save_keys(str(wallet_file), pub, priv)
    balances_file = tmp_path / "balances.json"
    ledger.save_balances({pub: 123.0}, str(balances_file))

    helix_cli.main([
        "export-wallet",
        "--wallet",
        str(wallet_file),
        "--balances",
        str(balances_file),
    ])
    encoded = capsys.readouterr().out.strip()
    data = json.loads(base64.b64decode(encoded).decode())
    assert data["public_key"] == pub
    assert data["private_key"] == priv
    assert data["balance"] == 123.0

    wallet_file.unlink()
    balances_file.write_text("{}")

    helix_cli.main([
        "import-wallet",
        encoded,
        "--wallet",
        str(wallet_file),
        "--balances",
        str(balances_file),
    ])
    capsys.readouterr()
    saved_pub, saved_priv = signature_utils.load_keys(str(wallet_file))
    assert (saved_pub, saved_priv) == (pub, priv)
    balances = ledger.load_balances(str(balances_file))
    assert balances[pub] == 123.0
