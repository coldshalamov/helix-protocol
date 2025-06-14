import pytest
from helix.wallet import Wallet


def test_wallet_deposit_withdraw():
    w = Wallet(100)
    w.deposit(50)
    assert w.balance == 150
    w.withdraw(70)
    assert w.balance == 80


def test_wallet_withdraw_insufficient():
    w = Wallet(30)
    with pytest.raises(ValueError):
        w.withdraw(40)

