import json
import hashlib
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
    """Validate a chain loaded with :func:`load_chain`.

    The chain is walked block by block verifying that ``parent_id`` matches the
    previous block's ``block_id`` and that each block's ``block_id`` equals the
    SHA-256 hash of the block contents (excluding the ``block_id`` field).
    """

    if not isinstance(chain, list):
        return False

    prev_id: Optional[str] = None
    for block in chain:
        if not isinstance(block, dict):
            return False

        parent_id = block.get("parent_id")

        block_copy = dict(block)
        block_id = block_copy.pop("block_id", None)
        if block_id is None:
            return False

        digest = hashlib.sha256(
            json.dumps(block_copy, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()

        if digest != block_id:
            return False

        if prev_id is not None and parent_id != prev_id:
            return False

        prev_id = block_id

    return True


__all__ = ["get_chain_tip", "load_chain", "validate_chain"]
