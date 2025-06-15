import json
import hashlib
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


def validate_blockchain(path: str = "blockchain.jsonl") -> bool:
    """Validate the blockchain stored at ``path``.

    Blocks are loaded using :func:`load_chain`. For each block we verify
    that ``parent_id`` references the previous block's ``block_id`` and
    that the stored ``block_id`` equals the SHA-256 hash of the block
    contents (excluding the ``block_id`` field).
    """
    chain = load_chain(path)
    prev_id = None
    for block in chain:
        parent_id = block.get("parent_id")
        block_copy = dict(block)
        block_id = block_copy.pop("block_id", None)
        if block_id is None:
            return False
        digest = hashlib.sha256(
            json.dumps(block_copy, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        if digest != block_id:
            return False
        if prev_id is not None and parent_id != prev_id:
            return False
        prev_id = block_id
    return True
