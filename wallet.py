import json
from pathlib import Path
from nacl import signing


WALLET_FILE = Path("wallet.json")


def generate_wallet() -> dict:
    """Generate a new wallet and save it to ``wallet.json``.

    Returns the wallet dictionary.
    """
    signing_key = signing.SigningKey.generate()
    verify_key = signing_key.verify_key
    wallet = {
        "private": signing_key.encode().hex(),
        "public": verify_key.encode().hex(),
    }
    with open(WALLET_FILE, "w", encoding="utf-8") as fh:
        json.dump(wallet, fh, indent=2)
    print(f"Wallet generated and saved to {WALLET_FILE}")
    print(f"Public address: {wallet['public']}")
    return wallet


def load_wallet() -> dict:
    """Load the wallet from ``wallet.json`` and return it."""
    with open(WALLET_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    if WALLET_FILE.exists():
        print("wallet.json already exists. Aborting.")
    else:
        generate_wallet()
