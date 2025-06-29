"""Utility functions for Helix wallet management."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Tuple

from nacl import signing


class Wallet:
    """Simple HLX wallet for tests."""

    def __init__(self, balance: int = 0) -> None:
        if balance < 0:
            raise ValueError("balance must be non-negative")
        self._balance = balance

    @property
    def balance(self) -> int:
        return self._balance

    def deposit(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self._balance += amount

    def withdraw(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if amount > self._balance:
            raise ValueError("insufficient funds")
        self._balance -= amount

__all__ = ["Wallet", "generate_wallet", "load_wallet", "DEFAULT_WALLET_FILE"]


DEFAULT_WALLET_FILE = Path("wallet.json")


def generate_wallet(path: Path = DEFAULT_WALLET_FILE) -> Tuple[str, str]:
    """Generate a new keypair and save to ``path``.

    The file will contain the base64 encoded public key on the first line and
    the private key on the second line.  Returns ``(public, private)``.
    """

    signing_key = signing.SigningKey.generate()
    verify_key = signing_key.verify_key

    pub_b64 = base64.b64encode(verify_key.encode()).decode("ascii")
    priv_b64 = base64.b64encode(signing_key.encode()).decode("ascii")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"{pub_b64}\n{priv_b64}\n")

    return pub_b64, priv_b64


def _normalize_keys(pub: bytes, priv: bytes) -> Tuple[str, str]:
    """Return base64 encoded ``(pub, priv)``."""

    pub_b64 = base64.b64encode(pub).decode("ascii")
    priv_b64 = base64.b64encode(priv).decode("ascii")
    return pub_b64, priv_b64


def load_wallet(path: Path = DEFAULT_WALLET_FILE) -> Tuple[str, str]:
    """Load wallet keys from ``path`` in various supported formats."""

    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read().strip()

    # Try JSON structure first
    try:
        data = json.loads(content)
    except Exception:
        data = None

    if isinstance(data, dict) and "public" in data and "private" in data:
        pub_raw = data["public"]
        priv_raw = data["private"]
        try:
            pub = base64.b64decode(pub_raw)
            priv = base64.b64decode(priv_raw)
        except Exception:
            pub = bytes.fromhex(pub_raw)
            priv = bytes.fromhex(priv_raw)
        return _normalize_keys(pub, priv)

    # Fallback to two-line format
    lines = content.splitlines()
    if len(lines) < 2:
        raise ValueError("wallet file malformed")

    try:
        pub = base64.b64decode(lines[0])
        priv = base64.b64decode(lines[1])
    except Exception:
        pub = bytes.fromhex(lines[0])
        priv = bytes.fromhex(lines[1])

    return _normalize_keys(pub, priv)

