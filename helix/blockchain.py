import json
from pathlib import Path

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

    last_line: str | None = None
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


__all__ = ["get_chain_tip"]
