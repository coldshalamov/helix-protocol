"""Utilities for generating and verifying digital signatures using Ed25519."""

from __future__ import annotations

import base64
from typing import Tuple
from pathlib import Path

from nacl import signing


def generate_keypair() -> Tuple[str, str]:
    """Generate a new Ed25519 keypair.

    Returns a tuple of ``(public_key, private_key)`` where both values are
    base64-encoded strings.
    """
    private_key = signing.SigningKey.generate()
    public_key = private_key.verify_key
    priv_b64 = base64.b64encode(private_key.encode()).decode("ascii")
    pub_b64 = base64.b64encode(public_key.encode()).decode("ascii")
    return pub_b64, priv_b64


def sign_data(data: bytes, private_key: str) -> str:
    """Return a base64 signature for ``data`` using ``private_key``."""
    key_bytes = base64.b64decode(private_key)
    signing_key = signing.SigningKey(key_bytes)
    signed = signing_key.sign(data)
    return base64.b64encode(signed.signature).decode("ascii")


def sign_statement(statement: str, private_key: str) -> str:
    """Return a base64 signature for ``statement`` using ``private_key``."""
    return sign_data(statement.encode("utf-8"), private_key)


def verify_signature(data: bytes, signature: str, public_key: str) -> bool:
    """Verify that ``signature`` matches ``data`` for ``public_key``."""
    sig_bytes = base64.b64decode(signature)
    key_bytes = base64.b64decode(public_key)
    verify_key = signing.VerifyKey(key_bytes)
    try:
        verify_key.verify(data, sig_bytes)
        return True
    except Exception:
        return False


def save_keys(filename: str, pub: str, priv: str) -> None:
    """Save base64-encoded ``pub`` and ``priv`` keys to ``filename``."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"{pub}\n{priv}\n")


def load_keys(filename: str) -> Tuple[str, str]:
    """Load ``(public_key, private_key)`` from ``filename``."""
    with open(filename, "r", encoding="utf-8") as f:
        pub = f.readline().strip()
        priv = f.readline().strip()
    return pub, priv


def load_private_key(filename: str) -> str:
    """Return only the private key stored in ``filename``."""
    _, priv = load_keys(filename)
    return priv


def load_or_create_keys(filename: str) -> Tuple[str, str]:
    """Return keys from ``filename`` or generate and save new ones."""
    path = Path(filename)
    if path.exists():
        return load_keys(filename)
    pub, priv = generate_keypair()
    save_keys(filename, pub, priv)
    return pub, priv


def load_private_key(private_key: str) -> signing.SigningKey:
    """Return a :class:`~nacl.signing.SigningKey` for ``private_key``."""
    key_bytes = base64.b64decode(private_key)
    return signing.SigningKey(key_bytes)


__all__ = [
    "generate_keypair",
    "sign_statement",
    "sign_data",
    "verify_signature",
    "save_keys",
    "load_keys",
    "load_or_create_keys",
    "load_private_key",
]


def main() -> None:
    """Demonstrate key generation, signing and verification."""
    pub, priv = generate_keypair()
    statement = b"Helix signature demo"
    signature = sign_data(statement, priv)
    print("Public key:", pub)
    print("Private key:", priv)
    print("Signature:", signature)
    valid = verify_signature(statement, signature, pub)
    print("Signature valid:", valid)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
