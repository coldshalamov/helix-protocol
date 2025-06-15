import json
from pathlib import Path
from typing import Any, Dict, List


def load_chain(path: str) -> List[Dict[str, Any]]:
    """Load blockchain data from ``path``.

    If the file does not exist, an empty list is returned.
    The file is expected to contain JSON representing a list of blocks or a
    dictionary with a ``"chain"`` key.
    """
    file = Path(path)
    if not file.exists():
        return []
    with open(file, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("chain", [])
    if not isinstance(data, list):
        return []
    return data


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


__all__ = ["load_chain", "validate_chain"]
