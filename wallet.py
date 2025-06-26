import json
from pathlib import Path
from nacl import signing
from typing import Tuple

DEFAULT_WALLET_FILE = Path("wallet.json")


def generate_wallet(path: Path = DEFAULT_WALLET_FILE) -> dict:
    """Generate a new wallet and save it to the specified path."""
    signing_key = signing.SigningKey.generate()
    verify_key = signing_key.verify_key
    wallet = {
        "private": signing_key.encode().hex(),
        "public": verify_key.encode().hex(),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(wallet, fh, indent=2)
    print(f"Wallet generated and saved to {path}")
    print(f"Public address: {wallet['public']}")
    return wallet


def load_wallet(path: Path = DEFAULT_WALLET_FILE) -> dict:
    """Load an existing wallet from the specified path."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    if DEFAULT_WALLET_FILE.exists():
        print("wallet.json already exists. Aborting.")
    else:
        generate_wallet()


__all__ = ["generate_wallet", "load_wallet"]
