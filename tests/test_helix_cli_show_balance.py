import pytest

pytest.importorskip("nacl")

from helix import helix_cli, signature_utils, ledger


def test_show_balance(tmp_path, capsys):
    pub, priv = signature_utils.generate_keypair()
    wallet_file = tmp_path / "wallet.txt"
    signature_utils.save_keys(str(wallet_file), pub, priv)
    balances_file = tmp_path / "balances.json"
    ledger.save_balances({pub: 42.0}, str(balances_file))

    helix_cli.main([
        "show-balance",
        "--wallet",
        str(wallet_file),
        "--balances",
        str(balances_file),
    ])
    out = capsys.readouterr().out.strip()
    assert out == "42.0"
