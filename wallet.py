from helix.signature_utils import load_or_create_keys, load_keys
from typing import Tuple

DEFAULT_WALLET_FILE = "wallet.json"

def generate_wallet(path: str = DEFAULT_WALLET_FILE) -> Tuple[str, str]:
    """Return public/private keypair, creating a new wallet if needed."""
    return load_or_create_keys(path)

def load_wallet(path: str = DEFAULT_WALLET_FILE) -> Tuple[str, str]:
    """Load an existing wallet keypair from ``path``."""
    return load_keys(path)

__all__ = ["generate_wallet", "load_wallet"]
