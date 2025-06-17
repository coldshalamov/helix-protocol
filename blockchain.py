import json
import hashlib
import os
from pathlib import Path
from typing import List, Dict
from helix.config import GENESIS_HASH


def get_chain_tip(path: str = "blockchain.jsonl") -> str:
    """Return the ``block_id`` of the last block in ``path``."""
    file = Path(path)
    if not file.exists():
        return GENESIS_HASH

    last_line = None
    with open(file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last_line = line

    if not last_line:
        return GENESIS_HASH

    try:
        entry = json.loads(last_line)
    except json.JSONDecodeError:
        return GENESIS_HASH

    return entry.get("block_id", GENESIS_HASH)


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


def validate_chain(chain: List[Dict]) -> bool:
    """Validate a blockchain provided as a list of block headers."""
    prev_id = None
    for block in chain:
        parent_id = block.get("parent_id")
        block_copy = dict(block)
        block_id = block_copy.pop("block_id", None)
        if block_id is None:
            return False
        digest = hashlib.sha256(
            json.dumps(block_copy, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if digest != block_id:
            return False
        if prev_id is not None and parent_id != prev_id:
            return False
        prev_id = block_id
    return True


def _chain_weight(chain: List[Dict], events_dir: str) -> float:
    """Return total compression rewards for ``chain`` based on event files."""
    try:
        from helix import event_manager  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return 0.0

    weight = 0.0
    events_path = Path(events_dir)
    for block in chain:
        ids = block.get("event_ids") or []
        if isinstance(ids, str):
            ids = [ids]
        for evt_id in ids:
            evt_file = events_path / f"{evt_id}.json"
            if not evt_file.exists():
                continue
            try:
                event = event_manager.load_event(str(evt_file))
            except Exception:
                continue
            rewards = event.get("rewards", [])
            refunds = event.get("refunds", [])
            weight += sum(rewards) - sum(refunds)
    return weight


def resolve_fork(
    local_chain: List[Dict],
    remote_chain: List[Dict],
    *,
    events_dir: str = "events",
) -> List[Dict]:
    """Return the preferred chain between ``local_chain`` and ``remote_chain``.

    The remote chain is adopted only if it is longer, valid, and has a greater
    total compression reward weight.
    """

    if len(remote_chain) <= len(local_chain):
        return local_chain
    if not validate_chain(remote_chain):
        return local_chain

    local_weight = _chain_weight(local_chain, events_dir)
    remote_weight = _chain_weight(remote_chain, events_dir)

    if remote_weight > local_weight:
        return remote_chain
    return local_chain
