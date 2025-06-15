import json
import os
from pathlib import Path
from typing import List, Dict


def append_block(block_header: Dict, path: str = "blockchain.jsonl") -> None:
    """Append ``block_header`` to the chain at ``path`` as newline-delimited JSON."""
    line = json.dumps(block_header, separators=(",", ":"))
    file = Path(path)
    with open(file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_chain(path: str = "blockchain.jsonl") -> List[Dict]:
    """Return list of block headers stored in ``path``."""
    file = Path(path)
    if not file.exists():
        return []

    chain: List[Dict] = []
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chain.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return chain
