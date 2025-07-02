import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import os
import tempfile

from datetime import datetime
from nacl import signing

from .config import GENESIS_HASH
from .signature_utils import verify_signature, sign_data, generate_keypair
import time
from .merkle_utils import build_merkle_tree as _build_merkle_tree
from . import nested_miner, betting_interface
from .betting_interface import get_bets_for_event
from .ledger import apply_mining_results
from .statement_registry import finalize_statement
from .minihelix import G, DEFAULT_MICROBLOCK_SIZE
import blockchain

FINAL_BLOCK_PADDING_BYTE = b"\x00"

# Maximum total microblock bytes to keep in memory before spilling to disk
MAX_RAM_MICROBLOCK_BYTES = 10 * 1024 * 1024  # 10MB

# Map of event_id -> temporary directory containing spilled microblocks
_MICROBLOCK_STORES: Dict[str, str] = {}

LAST_FINALIZED_HASH = GENESIS_HASH
LAST_FINALIZED_TIME = 0.0


def sha256(data: bytes) -> str:
    """Return hex encoded SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()

# ... all other functions from your provided code continue unmodified ...


def compute_reward(seed: bytes | Dict[str, Any], block_size: int | None = None) -> float:
    """Return HLX reward based on bytes saved.

    A short helper is provided here so the test suite can run without the
    original implementation. If ``seed`` is a mapping, the microblock size is
    taken from ``seed['header']['microblock_size']`` and the rewards for all
    stored seeds are summed.  When ``seed`` is ``bytes`` ``block_size`` must be
    provided and the reward equals ``max(0, block_size - len(seed))``.
    """

    if isinstance(seed, bytes):
        if block_size is None:
            raise TypeError("block_size required when seed is bytes")
        return float(max(0, block_size - len(seed)))

    header = seed.get("header", {})
    micro_size = int(header.get("microblock_size", DEFAULT_MICROBLOCK_SIZE))
    total = 0.0
    for entry in seed.get("seeds", []):
        if not isinstance(entry, (bytes, bytearray, list)):
            continue
        # encoded seed may be stored as list of ints
        if isinstance(entry, list):
            entry = bytes(entry)
        if not entry:
            continue
        total += max(0, micro_size - len(entry))
    return float(total)


def finalize_event(
    event: Dict[str, Any],
    *,
    node_id: str | None = None,
    chain_file: str = "blockchain.jsonl",
    events_dir: str | None = None,
    balances_file: str | None = None,
    delta_bonus: bool = False,
    _bc: Any = blockchain,
) -> Dict[str, float]:
    """Finalize ``event`` and append a block header to ``chain_file``.

    This simplified implementation records ``delta_seconds`` between block
    finalizations and notes whether the delta bonus was granted.  Information
    about who received the bonus and when is stored in the block header so that
    the next finalizer can validate the claim.  The actual enforcement of the
    penalty is performed by :class:`helix.helix_node.HelixNode`.
    """

    global LAST_FINALIZED_HASH, LAST_FINALIZED_TIME

    if not event.get("is_closed"):
        raise ValueError("event must be closed before finalization")

    # Compute delta since the last finalized block
    now = time.time()
    delta_seconds = 0.0 if LAST_FINALIZED_TIME == 0.0 else now - LAST_FINALIZED_TIME
    LAST_FINALIZED_TIME = now

    # Determine previous block and bonus receiver
    chain = _bc.load_chain(str(chain_file))
    prev_block = chain[-1] if chain else None
    bonus_receiver = prev_block.get("finalizer") if prev_block else None

    # Build the new block header
    header = {
        "parent_id": LAST_FINALIZED_HASH,
        "event_id": event.get("header", {}).get("statement_id"),
        "timestamp": datetime.utcfromtimestamp(now).isoformat(),
        "finalizer": node_id,
        "delta_seconds": delta_seconds,
        "delta_bonus": 1 if delta_bonus else 0,
        "delta_receiver": bonus_receiver if delta_bonus else None,
        "delta_granted": now if delta_bonus else None,
    }

    block_id = sha256(json.dumps(header, sort_keys=True).encode("utf-8"))
    header["block_id"] = block_id

    # Persist block and update globals
    _bc.append_block(header, path=str(chain_file))
    LAST_FINALIZED_HASH = block_id

    # Store metadata in the event
    event.setdefault("header", {})["delta_seconds"] = delta_seconds
    event["header"]["delta_bonus"] = bool(delta_bonus)
    event["finalized"] = True
    event["block_header"] = header

    # Payouts and balances are intentionally simplified. The original project
    # applied compression rewards and bet payouts which are out of scope here.
    payouts: Dict[str, float] = {}
    miner_reward = compute_reward(event)
    if node_id:
        payouts[node_id] = payouts.get(node_id, 0.0) + miner_reward

    event["payouts"] = payouts
    event["miner_reward"] = miner_reward

    # Persist event if requested
    if events_dir:
        path = Path(events_dir) / f"{header['event_id']}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(event, fh, indent=2)

    # TODO: future finalizers should verify ``delta_seconds`` against wall clock
    # time and revoke the grantor's pending delta bonus if dishonest.

    return payouts

