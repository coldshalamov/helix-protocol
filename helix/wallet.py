import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .signature_utils import generate_keypair, sign_data


@dataclass
class Wallet:
    pubkey: str
    privkey: str
    balance: int = 1000

    def to_dict(self) -> Dict[str, str | int]:
        return {
            "pubkey": self.pubkey,
            "privkey": self.privkey,
            "balance": self.balance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str | int]) -> "Wallet":
        return cls(
            pubkey=data["pubkey"],
            privkey=data["privkey"],
            balance=int(data.get("balance", 0)),
        )


def wallet_id(pubkey: str) -> str:
    """Return SHA256 hex digest of ``pubkey``."""
    return hashlib.sha256(pubkey.encode("utf-8")).hexdigest()


def save_wallet(wallet: Wallet, path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wallet.to_dict(), f, indent=2)


def load_wallet(path: str | Path) -> Wallet:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Wallet.from_dict(data)


def create_wallet(path: str | Path, *, balance: int = 1000) -> Wallet:
    pub, priv = generate_keypair()
    wallet = Wallet(pubkey=pub, privkey=priv, balance=balance)
    save_wallet(wallet, path)
    return wallet


def send_hlx(from_path: str | Path, to_path: str | Path, amount: int) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")
    sender = load_wallet(from_path)
    receiver = load_wallet(to_path)
    if sender.balance < amount:
        raise ValueError("insufficient balance")
    sender.balance -= amount
    receiver.balance += amount
    save_wallet(sender, from_path)
    save_wallet(receiver, to_path)


def sign_with_wallet(path: str | Path, message: str) -> str:
    wallet = load_wallet(path)
    return sign_data(message.encode("utf-8"), wallet.privkey)


__all__ = [
    "Wallet",
    "wallet_id",
    "create_wallet",
    "load_wallet",
    "save_wallet",
    "send_hlx",
    "sign_with_wallet",
]

