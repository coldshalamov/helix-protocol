import json
from pathlib import Path
from typing import List, Dict, Any


def load_chain(path: str) -> List[Dict[str, Any]]:
    """Load blockchain data from ``path``.

    The file is expected to contain a JSON list of block
    dictionaries. If the file does not exist, an empty list is
    returned.
    """
    file = Path(path)
    if not file.exists():
        return []
    with open(file, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "blocks" in data:
        blocks = data.get("blocks")
        if isinstance(blocks, list):
            return blocks
    return []


__all__ = ["load_chain"]
