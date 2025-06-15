import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import GENESIS_HASH


def get_chain_tip(path: str = "blockchain.jsonl") -> str:
    """Return the latest ``block_id`` from ``path``.

    Parameters
    ----------
    path:
        Path to the blockchain JSON lines file.

    Returns
    -------
    str
        ``block_id`` of the last entry, or :data:`GENESIS_HASH` if the file is
        missing or empty.
    """
    file = Path(path)
    if not file.exists():
        return GENESIS_HASH

    last_line: Optional[str] = None
    with open(file, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                last_line = line

    if not last_line:
        return GENESIS_HASH

    try:
        entry = json.loads(last_line)
    except json.JSONDecodeError:
        return GENESIS_HASH

    return entry.get("block_id", GENESIS_HASH)


def load_chain(path: str) -> List[Dict[str, Any]]:
    """Load blockchain data from ``path``.

    Supports both JSON lines and structured block files.
    - If file contains a list of blocks → returns directly.
    - If file contains a dict with "blocks" or "chain" → extracts list.
    - If file doesn't exist → returns [].
    """
    file = Path(path)
    if not file.exists():
        return []
    with open(file, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "blocks" in data and isinstance(data["blocks"], list):
            return data["blocks"]
        if "chain" in data and isinstance(data["chain"], list):
            return data["chain"]
    return []


def validate_chain(chain: List[Dict[str, Any]]) -> bool:
    """Basic validation of a blockchain structure.

    Each block must be a dictionary containing at least an ``event_id`` field.
    If a ``height`` field is present, it must match the block's index.
    """
    if not isinstance(chain, list):
        return False
    for idx, block in enumerate(chain):
        if not isinstance(block, dict):
            return False
        if "event_id" not in block:
            return False
        if "height" in block and block["height"] != idx:
            return False
    return True


__all__ = ["get_chain_tip", "load_chain", "validate_chain"]
