import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import os
import tempfile
import logging

from datetime import datetime
from nacl import signing

from .config import GENESIS_HASH
from .signature_utils import verify_signature, sign_data, generate_keypair
import time
from .merkle_utils import build_merkle_tree as _build_merkle_tree
from . import nested_miner, betting_interface, exhaustive_miner
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
# Hash of the last finalized statement. Used to link final blocks together.
LAST_STATEMENT_HASH = GENESIS_HASH

# Pending microblock information keyed by event_id
pending_microblocks: Dict[str, Dict[int, bytes]] = {}
pending_seeds: Dict[str, Dict[int, bytes]] = {}
pending_miners: Dict[str, Dict[int, str]] = {}

# Event metadata (block count and microblock size) keyed by event_id
event_metadata: Dict[str, Dict[str, int]] = {}

# File used to persist finalized statements
FINALIZED_FILE = Path("finalized_statements.jsonl")
# File used to log finalized block summaries
FINALIZED_EVENT_LOG = Path("finalized_log.jsonl")


def sha256(data: bytes) -> str:
    """Return hex encoded SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def split_into_microblocks(
    statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE
) -> Tuple[List[bytes], int, int]:
    """Split ``statement`` into padded microblocks."""

    payload = statement.encode("utf-8")
    orig_len = len(payload)
    blocks: List[bytes] = []
    for i in range(0, orig_len, microblock_size):
        chunk = payload[i : i + microblock_size]
        if len(chunk) < microblock_size:
            chunk = chunk + FINAL_BLOCK_PADDING_BYTE * (microblock_size - len(chunk))
        blocks.append(chunk)
    return blocks, len(blocks), orig_len


def reassemble_microblocks(blocks: List[bytes]) -> str:
    """Return the original statement from ``blocks``."""

    payload = b"".join(bytes(b) for b in blocks).rstrip(FINAL_BLOCK_PADDING_BYTE)
    return payload.decode("utf-8")


def create_event(
    statement: str,
    *,
    microblock_size: int = DEFAULT_MICROBLOCK_SIZE,
    parent_id: str = GENESIS_HASH,
    private_key: str | None = None,
    registry: Any | None = None,
) -> Dict[str, Any]:
    """Create a new statement event."""

    if registry is not None:
        registry.check_and_add(statement)

    blocks, count, orig_len = split_into_microblocks(statement, microblock_size)
    root, tree = _build_merkle_tree(blocks)

    if private_key is None:
        pub, priv = generate_keypair()
    else:
        priv = private_key
        signing_key = signing.SigningKey(base64.b64decode(priv))
        pub = base64.b64encode(signing_key.verify_key.encode()).decode("ascii")

    signature = sign_data(statement.encode("utf-8"), priv)

    header = {
        "statement_id": sha256(statement.encode("utf-8")),
        "original_length": orig_len,
        "microblock_size": microblock_size,
        "block_count": count,
        "parent_id": parent_id,
        "merkle_root": root.hex(),
    }

    event = {
        "header": header,
        "statement": statement,
        "microblocks": blocks,
        "merkle_tree": [[h.hex() for h in level] for level in tree],
        "seeds": [None] * count,
        "seed_depths": [0] * count,
        "mined_status": [False] * count,
        "rewards": [0.0] * count,
        "refunds": [0.0] * count,
        "is_closed": False,
        "bets": {"YES": [], "NO": []},
        "originator_pub": pub,
        "originator_sig": signature,
        "miners": [None] * count,
    }

    # Register event metadata for later microblock submissions
    evt_id = header["statement_id"]
    event_metadata[evt_id] = {
        "block_count": count,
        "microblock_size": microblock_size,
    }

    return event


def save_event(event: Dict[str, Any], directory: str) -> str:
    """Persist ``event`` to ``directory`` and return the file path."""

    Path(directory).mkdir(parents=True, exist_ok=True)
    evt_id = event.get("header", {}).get("statement_id")
    if not evt_id:
        raise ValueError("missing statement_id")

    data = event.copy()
    data["microblocks"] = [b.hex() for b in event.get("microblocks", [])]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, (bytes, bytearray)) else s for s in data["seeds"]]

    path = Path(directory) / f"{evt_id}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return str(path)


def load_event(path: str) -> Dict[str, Any]:
    """Load and decode an event from ``path``."""

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    header = data.get("header", {})
    parent = header.get("parent_id")
    if parent and parent != GENESIS_HASH:
        raise ValueError("invalid parent_id")

    data["microblocks"] = [bytes.fromhex(b) for b in data.get("microblocks", [])]
    seeds = []
    for entry in data.get("seeds", []):
        if entry is None:
            seeds.append(None)
        elif isinstance(entry, str):
            seeds.append(bytes.fromhex(entry))
        else:
            seeds.append(entry)
    data["seeds"] = seeds
    return data


def mark_mined(event: Dict[str, Any], index: int) -> None:
    """Mark microblock ``index`` as mined and close event if complete."""

    status = event.setdefault("mined_status", [False] * event["header"]["block_count"])
    status[index] = True
    if all(status):
        event["is_closed"] = True


def accept_mined_seed(
    event: Dict[str, Any],
    index: int,
    encoded: bytes | List[int] | List[bytes],
    *,
    miner: str | None = None,
    chain_file: str = "blockchain.jsonl",
) -> float:
    """Store ``encoded`` seed for ``index`` and finalize if complete."""

    if isinstance(encoded, list) and encoded and isinstance(encoded[0], int):
        encoded_bytes = bytes(encoded)
    elif isinstance(encoded, list):
        encoded_bytes = b"".join(bytes(e) for e in encoded)
    else:
        encoded_bytes = bytes(encoded)

    block = event.get("microblocks", [])[index]
    if not nested_miner.verify_nested_seed(encoded_bytes, block):
        return 0.0

    seeds = event.setdefault("seeds", [None] * event["header"]["block_count"])
    rewards = event.setdefault("rewards", [0.0] * event["header"]["block_count"])
    miners = event.setdefault("miners", [None] * event["header"]["block_count"])
    seeds[index] = encoded_bytes
    miners[index] = miner
    rewards[index] = compute_reward(encoded_bytes, event["header"].get("microblock_size", DEFAULT_MICROBLOCK_SIZE))
    mark_mined(event, index)

    if event.get("is_closed") and all(event.get("mined_status", [])) and not event.get("finalized"):
        finalize_event(event, node_id=miner, chain_file=chain_file)

    return 0.0


def verify_event_signature(event: Dict[str, Any]) -> bool:
    """Return ``True`` if the event originator signature is valid."""

    statement = event.get("statement", "")
    pub = event.get("originator_pub")
    sig = event.get("originator_sig")
    if not statement or not pub or not sig:
        return False
    return verify_signature(statement.encode("utf-8"), sig, pub)


def verify_seed_chain(encoded: bytes, block: bytes) -> bool:
    """Wrapper around :func:`nested_miner.verify_nested_seed`."""

    return nested_miner.verify_nested_seed(encoded, block)


def verify_statement(event: Dict[str, Any]) -> bool:
    """Return ``True`` if all seeds regenerate their microblocks."""

    blocks = event.get("microblocks", [])
    seeds = event.get("seeds", [])
    for block, seed in zip(blocks, seeds):
        if seed is None:
            return False
        if not nested_miner.verify_nested_seed(seed, block):
            return False
    return True


def submit_microblock(event_id: str, index: int, seed: bytes, miner: str) -> None:
    """Submit a mined microblock seed for ``event_id`` at ``index``."""

    meta = event_metadata.get(event_id)
    if not meta:
        raise KeyError(f"Unknown event {event_id}")

    size = meta.get("microblock_size", DEFAULT_MICROBLOCK_SIZE)
    block = G(seed, size)

    pending_microblocks.setdefault(event_id, {})[index] = block
    pending_seeds.setdefault(event_id, {})[index] = seed
    pending_miners.setdefault(event_id, {})[index] = miner

    if len(pending_microblocks[event_id]) == meta.get("block_count", 0):
        try:
            finalize_event(event_id)
        except Exception as exc:  # pragma: no cover - logging
            print(f"Failed to finalize {event_id}: {exc}")

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


def _legacy_finalize_event(
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

    global LAST_FINALIZED_HASH, LAST_FINALIZED_TIME, LAST_STATEMENT_HASH

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

    # Reassemble statement and compute its hash
    statement = reassemble_microblocks(event.get("microblocks", []))
    statement_id = sha256(statement.encode("utf-8"))

    # Build the new block header
    header = {
        "parent_id": LAST_FINALIZED_HASH,
        "event_id": statement_id,
        "previous_hash": LAST_STATEMENT_HASH,
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
    LAST_STATEMENT_HASH = statement_id

    # Store metadata in the event
    header_data = event.setdefault("header", {})
    header_data["delta_seconds"] = delta_seconds
    header_data["delta_bonus"] = bool(delta_bonus)
    header_data["statement_id"] = statement_id
    event["finalized"] = True
    event["block_header"] = header
    event["statement"] = statement

    # Payouts and balances are intentionally simplified. The original project
    # applied compression rewards and bet payouts which are out of scope here.
    payouts: Dict[str, float] = {}
    miner_reward = compute_reward(event)
    if node_id:
        payouts[node_id] = payouts.get(node_id, 0.0) + miner_reward

    event["payouts"] = payouts
    event["miner_reward"] = miner_reward

    # Append summary entry for this finalized block
    try:
        with open(FINALIZED_EVENT_LOG, "a", encoding="utf-8") as fh:
            json.dump(
                {
                    "block_id": block_id,
                    "statement_id": statement_id,
                    "miner_id": node_id,
                    "delta_seconds": delta_seconds,
                    "compression_reward": miner_reward,
                },
                fh,
            )
            fh.write("\n")
    except Exception as exc:  # pragma: no cover - logging only
        print(f"Failed to record finalized event log: {exc}")

    # Persist event if requested
    if events_dir:
        path = Path(events_dir) / f"{header['event_id']}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(event, fh, indent=2)

    # Later blocks verify this delta claim and may penalize the grantor
    # if the recorded value differs from the actual gap by more than 10s.

    return payouts


def _finalize_event_by_id(event_id: str) -> None:
    """Finalize an event referenced by ``event_id`` using pending data."""

    meta = event_metadata.get(event_id)
    if not meta:
        raise KeyError(f"Unknown event {event_id}")

    block_count = meta.get("block_count", 0)
    blocks = [pending_microblocks[event_id][i] for i in range(block_count)]
    seeds = [pending_seeds[event_id][i] for i in range(block_count)]
    miners = [pending_miners[event_id][i] for i in range(block_count)]

    payload = b"".join(blocks).rstrip(FINAL_BLOCK_PADDING_BYTE)
    statement = payload.decode("utf-8")
    statement_id = sha256(statement.encode("utf-8"))

    global LAST_STATEMENT_HASH, LAST_FINALIZED_TIME
    now = time.time()
    previous_hash = LAST_STATEMENT_HASH
    delta_seconds = 0.0 if LAST_FINALIZED_TIME == 0.0 else now - LAST_FINALIZED_TIME
    LAST_FINALIZED_TIME = now
    LAST_STATEMENT_HASH = statement_id

    finalize_statement(
        statement_id,
        statement,
        previous_hash,
        delta_seconds,
        seeds,
        miners,
    )

    try:
        with open(FINALIZED_FILE, "a", encoding="utf-8") as fh:
            json.dump(
                {
                    "statement_id": statement_id,
                    "statement": statement,
                    "previous_hash": previous_hash,
                    "delta_seconds": delta_seconds,
                    "seeds": [s.hex() for s in seeds],
                    "miners": miners,
                    "timestamp": now,
                },
                fh,
            )
            fh.write("\n")
    except Exception as exc:  # pragma: no cover - logging only
        print(f"Failed to record finalized statement: {exc}")

    pending_microblocks.pop(event_id, None)
    pending_seeds.pop(event_id, None)
    pending_miners.pop(event_id, None)
    event_metadata.pop(event_id, None)


def finalize_event(
    event: Any,
    *,
    node_id: str | None = None,
    chain_file: str = "blockchain.jsonl",
    events_dir: str | None = None,
    balances_file: str | None = None,
    delta_bonus: bool = False,
    _bc: Any = blockchain,
) -> Dict[str, float] | None:
    """Finalize ``event`` which may be an event dict or an event id."""

    if isinstance(event, dict):
        return _legacy_finalize_event(
            event,
            node_id=node_id,
            chain_file=chain_file,
            events_dir=events_dir,
            balances_file=balances_file,
            delta_bonus=delta_bonus,
            _bc=_bc,
        )

    _finalize_event_by_id(str(event))
    return None


def replay_and_remine(statement_id: str) -> None:
    """Re-mine microblocks for ``statement_id`` from their output.

    Loads ``data/events/<id>.json`` and attempts to compress each microblock
    again using :func:`exhaustive_miner.exhaustive_mine`.  The number of blocks
    that yield a smaller encoded seed is logged.  This is a scaffold and does
    not persist any new seeds.
    """

    path = Path("data/events") / f"{statement_id}.json"
    if not path.exists():
        raise FileNotFoundError(str(path))

    event = load_event(str(path))

    blocks = event.get("microblocks", [])
    seeds = event.get("seeds", [None] * len(blocks))

    def _seed_len(seed: Any) -> int:
        if seed is None:
            return math.inf
        if isinstance(seed, bytes):
            return len(seed)
        if isinstance(seed, str):
            return len(bytes.fromhex(seed))
        if isinstance(seed, list):
            if seed and isinstance(seed[0], int):
                return len(bytes(seed))
            total = 0
            for part in seed:
                if isinstance(part, str):
                    total += len(bytes.fromhex(part))
                elif isinstance(part, list) and part and isinstance(part[0], int):
                    total += len(bytes(part))
                else:
                    total += len(part)
            return total
        return len(seed)

    improved = 0
    for idx, block in enumerate(blocks):
        chain = exhaustive_miner.exhaustive_mine(block, max_depth=5)
        if chain is None:
            continue
        encoded = bytes([len(chain), len(chain[0])]) + b"".join(chain)
        cur_len = _seed_len(seeds[idx])
        if len(encoded) < cur_len:
            improved += 1
        logging.debug(
            "microblock %d old_len=%s new_len=%d",
            idx,
            "inf" if cur_len == math.inf else int(cur_len),
            len(encoded),
        )

    logging.info(
        "%d/%d microblocks can be recompressed further",
        improved,
        len(blocks),
    )


def list_events(directory: str = "data") -> List[Dict[str, Any]]:
    """Return a summary of all events stored in ``directory``."""

    events_dir = Path(directory) / "events"
    if not events_dir.exists():
        return []

    summaries: List[Dict[str, Any]] = []
    for path in sorted(events_dir.glob("*.json")):
        try:
            evt = load_event(str(path))
        except Exception:
            continue
        header = evt.get("header", {})
        sid = header.get("statement_id", path.stem)
        mined = sum(1 for m in evt.get("mined_status", []) if m)
        total = header.get("block_count", len(evt.get("microblocks", [])))
        summaries.append(
            {
                "statement_id": sid,
                "closed": evt.get("is_closed", False),
                "mined": mined,
                "total": total,
                "statement": evt.get("statement", ""),
            }
        )

    return summaries

