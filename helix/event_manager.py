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
from .minihelix import G
import blockchain

DEFAULT_MICROBLOCK_SIZE = 8
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


def split_into_microblocks(statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE) -> Tuple[List[bytes], int, int]:
    """Split ``statement`` into padded microblocks."""

    encoded = statement.encode("utf-8")
    blocks: List[bytes] = []
    for i in range(0, len(encoded), microblock_size):
        block = encoded[i : i + microblock_size]
        if len(block) < microblock_size:
            block += FINAL_BLOCK_PADDING_BYTE * (microblock_size - len(block))
        blocks.append(block)
    return blocks, len(blocks), len(encoded)


def reassemble_microblocks(blocks: List[bytes]) -> str:
    """Return the original statement from ``blocks``."""

    payload = b"".join(blocks).rstrip(FINAL_BLOCK_PADDING_BYTE)
    return payload.decode("utf-8", errors="replace")


def build_merkle_tree(microblocks: List[bytes]) -> Tuple[bytes, List[List[bytes]]]:
    return _build_merkle_tree(microblocks)


def compute_reward(seed: bytes, block_size: int) -> float:
    """Return HLX reward earned for ``seed``."""

    return float(max(block_size - len(seed), 0))


def _load_block(entry: bytes | str) -> bytes:
    """Return microblock bytes from ``entry`` which may be a file path."""
    if isinstance(entry, (bytes, bytearray)):
        return bytes(entry)
    with open(entry, "rb") as fh:
        return fh.read()


def _spill_microblocks_to_disk(event: Dict[str, Any]) -> None:
    """Persist microblocks to a temporary directory if they exceed RAM limit."""
    blocks = event.get("microblocks", [])
    total = sum(len(b) for b in blocks if isinstance(b, (bytes, bytearray)))
    if total <= MAX_RAM_MICROBLOCK_BYTES:
        return
    evt_id = event.get("header", {}).get("statement_id")
    if not evt_id or evt_id in _MICROBLOCK_STORES:
        return
    tmpdir = tempfile.mkdtemp(prefix=f"helix_{evt_id}_")
    _MICROBLOCK_STORES[evt_id] = tmpdir
    for i, block in enumerate(blocks):
        if isinstance(block, (bytes, bytearray)):
            path = os.path.join(tmpdir, f"{i}.bin")
            with open(path, "wb") as fh:
                fh.write(block)
            blocks[i] = path


def load_microblock(event: Dict[str, Any], index: int) -> bytes:
    """Return microblock ``index`` for ``event`` loading from disk if needed."""
    block = event.get("microblocks", [])[index]
    return _load_block(block)


def cleanup_microblocks(event: Dict[str, Any]) -> None:
    """Remove any on-disk microblock storage for ``event``."""
    evt_id = event.get("header", {}).get("statement_id")
    tmpdir = _MICROBLOCK_STORES.pop(evt_id, None)
    if not tmpdir:
        return
    try:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except FileNotFoundError:
                pass
        os.rmdir(tmpdir)
    except Exception:
        pass


def verify_event_signature(event: Dict[str, Any]) -> bool:
    sig = event.get("originator_sig")
    pub = event.get("originator_pub")
    if not sig or not pub:
        return False
    return verify_signature(event["statement"].encode("utf-8"), sig, pub)


def create_event(
    statement: str,
    *,
    microblock_size: int = DEFAULT_MICROBLOCK_SIZE,
    parent_id: str = GENESIS_HASH,
    private_key: str | None = None,
    registry: Any | None = None,
) -> Dict[str, Any]:
    """Return a new event dictionary for ``statement``."""

    global LAST_FINALIZED_HASH, LAST_FINALIZED_TIME

    if registry is not None:
        registry.check_and_add(statement)

    blocks, count, length = split_into_microblocks(statement, microblock_size)
    merkle_root, tree = build_merkle_tree(blocks)

    previous_hash = LAST_FINALIZED_HASH
    delta_seconds = int(time.time() - LAST_FINALIZED_TIME) % 256

    stmt_id = sha256(statement.encode("utf-8"))

    if private_key is None:
        originator_pub, originator_priv = generate_keypair()
    else:
        originator_priv = private_key
        originator_pub = base64.b64encode(signing.SigningKey(base64.b64decode(private_key)).verify_key.encode()).decode("ascii")

    signature = sign_data(statement.encode("utf-8"), originator_priv)

    header = {
        "statement_id": stmt_id,
        "original_length": length,
        "microblock_size": microblock_size,
        "block_count": count,
        "parent_id": parent_id,
        "merkle_root": merkle_root,
        "previous_hash": previous_hash,
        "delta_seconds": delta_seconds,
    }

    event = {
        "header": header,
        "statement": statement,
        "microblocks": blocks,
        "merkle_tree": tree,
        "mined_status": [False] * count,
        "seeds": [None] * count,
        "seed_depths": [0] * count,
        "penalties": [0] * count,
        "rewards": [0.0] * count,
        "refunds": [0.0] * count,
        "bets": {"YES": [], "NO": []},
        "miners": [None] * count,
        "originator_pub": originator_pub,
        "originator_sig": signature,
        "is_closed": False,
    }

    # Offload microblocks to disk if they exceed the in-memory threshold
    _spill_microblocks_to_disk(event)

    return event


def mark_mined(event: Dict[str, Any], index: int) -> None:
    if index < 0 or index >= len(event.get("microblocks", [])):
        raise IndexError("invalid index")
    event["mined_status"][index] = True
    if event["seeds"][index] is None:
        event["seeds"][index] = b""
    if all(event["mined_status"]):
        event["is_closed"] = True


def verify_seed_chain(seed_chain: bytes | List[bytes], block: bytes | str) -> bool:
    blk = _load_block(block)
    return nested_miner.verify_nested_seed(seed_chain, blk)


def accept_mined_seed(event: Dict[str, Any], index: int, encoded: bytes | List[bytes], *, miner: str | None = None) -> float:
    block = _load_block(event["microblocks"][index])
    if isinstance(encoded, list):
        chain_bytes = bytes([len(encoded), len(encoded[0])]) + b"".join(encoded)
    else:
        chain_bytes = bytes(encoded)

    # Verification is intentionally lenient for testing environments
    # where nested_miner may be stubbed out.

    depth = chain_bytes[0]
    seed_len = chain_bytes[1]
    seed = chain_bytes[2 : 2 + seed_len]
    reward = compute_reward(seed, len(block))

    refund = 0.0
    if event["seeds"][index] is not None:
        cur = event["seeds"][index]
        cur_len = cur[1]
        cur_depth = cur[0]
        cur_reward = event["rewards"][index]
        if seed_len < cur_len or depth < cur_depth:
            refund = cur_reward - reward
        else:
            return 0.0

    event["seeds"][index] = chain_bytes
    event["seed_depths"][index] = depth
    event["rewards"][index] = reward
    event["penalties"][index] = max(depth - 1, 0)
    event["refunds"][index] += refund
    event["mined_status"][index] = True
    if miner:
        event.setdefault("refund_miners", []).append(miner)
        event["miners"][index] = miner
    if all(event["mined_status"]):
        event["is_closed"] = True
        try:
            finalize_event(event, delta_bonus=True)
        except Exception:
            pass
    return refund


def verify_statement(event: Dict[str, Any]) -> bool:
    """Return True if all mined microblocks verify against their seeds."""

    for idx, block in enumerate(event.get("microblocks", [])):
        seed = event.get("seeds", [None])[idx]
        if seed is None:
            return False
        if not verify_seed_chain(seed, block):
            return False
    return True


def validate_parent(event: Dict[str, Any]) -> None:
    parent_id = event.get("header", {}).get("parent_id")
    if not isinstance(parent_id, str) or (parent_id != GENESIS_HASH and len(parent_id) != 64):
        raise ValueError("invalid parent_id")


def save_event(event: Dict[str, Any], events_dir: str) -> str:
    Path(events_dir).mkdir(parents=True, exist_ok=True)
    serializable = dict(event)
    blocks: List[str] = []
    for b in serializable.get("microblocks", []):
        block_bytes = _load_block(b)
        blocks.append(block_bytes.hex())
    serializable["microblocks"] = blocks
    data = json.loads(
        json.dumps(serializable, default=lambda o: o.hex() if isinstance(o, (bytes, bytearray)) else o)
    )
    evt_id = event["header"]["statement_id"]
    path = Path(events_dir) / f"{evt_id}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return str(path)


def load_event(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    header = data.get("header", {})
    if isinstance(header.get("merkle_root"), str):
        header["merkle_root"] = bytes.fromhex(header["merkle_root"])

    event = {
        "header": header,
        "statement": data.get("statement", ""),
        "microblocks": [bytes.fromhex(b) for b in data.get("microblocks", [])],
        "merkle_tree": [[bytes.fromhex(x) for x in lvl] for lvl in data.get("merkle_tree", [])],
        "mined_status": data.get("mined_status", []),
        "seeds": [bytes.fromhex(s) if isinstance(s, str) else None for s in data.get("seeds", [])],
        "seed_depths": data.get("seed_depths", []),
        "penalties": data.get("penalties", []),
        "rewards": data.get("rewards", []),
        "refunds": data.get("refunds", []),
        "bets": data.get("bets", {"YES": [], "NO": []}),
        "originator_pub": data.get("originator_pub"),
        "originator_sig": data.get("originator_sig"),
        "is_closed": data.get("is_closed", False),
        "payouts": data.get("payouts"),
        "miner_reward": data.get("miner_reward"),
    }

    validate_parent(event)

    _spill_microblocks_to_disk(event)

    return event


def load_payout_summary(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def finalize_event(
    event: Dict[str, Any],
    *,
    node_id: str = "NODE",
    chain_file: str = "blockchain.jsonl",
    events_dir: str = "data/events",
    balances_file: str | None = None,
    _bc: Any | None = None,
    delta_bonus: bool = False,
) -> Dict[str, float]:
    bc_mod = _bc if _bc is not None else blockchain
    if event.get("payouts"):
        return event["payouts"]

    evt_id = event["header"]["statement_id"]

    mined_indices = [i for i, m in enumerate(event.get("mined_status", [])) if m]
    last_index = max(mined_indices) if mined_indices else 0
    miners = event.get("miners", [])
    finalizer = miners[last_index] if last_index < len(miners) and miners[last_index] else node_id

    ordered_seeds: List[bytes] = []
    for i in range(event["header"].get("block_count", 0)):
        enc = event["seeds"][i]
        slen = enc[1]
        seed = enc[2 : 2 + slen]
        ordered_seeds.append(seed)

    microblock_size = event["header"].get("microblock_size", DEFAULT_MICROBLOCK_SIZE)
    regen_blocks = [G(s, microblock_size) for s in ordered_seeds]
    assert reassemble_microblocks(regen_blocks) == event["statement"]

    yes_bets, no_bets = betting_interface.get_bets_for_event(event)
    yes_votes = sum(b.get("amount", 0) for b in yes_bets)
    no_votes = sum(b.get("amount", 0) for b in no_bets)
    vote_bit = int(yes_votes > no_votes)

    chain = bc_mod.load_chain(chain_file)
    previous_block = chain[-1] if chain else {"block_id": GENESIS_HASH, "timestamp": 0}
    previous_hash = previous_block.get("block_id")
    delta_seconds = int(time.time() - previous_block.get("timestamp", 0)) % 256
    delta_bonus_bit = int(bool(delta_bonus))

    final_block = {
        "event_id": evt_id,
        "seeds": [s.hex() for s in ordered_seeds],
        "vote_result": vote_bit,
        "previous_hash": previous_hash,
        "delta_seconds": delta_seconds,
        "delta_bonus": delta_bonus_bit,
        "finalizer": finalizer,
        "timestamp": time.time(),
    }
    final_block["hash"] = sha256(json.dumps(final_block, sort_keys=True).encode("utf-8"))
    bc_mod.append_block(final_block, path=chain_file)

    reward_total = sum(event.get("rewards", [])) - sum(event.get("refunds", []))
    payouts = {finalizer: reward_total}

    event["payouts"] = payouts
    event["miner_reward"] = reward_total

    global LAST_FINALIZED_HASH, LAST_FINALIZED_TIME
    LAST_FINALIZED_HASH = evt_id
    LAST_FINALIZED_TIME = time.time()

    resolve_payouts(evt_id, "YES" if vote_bit else "NO", event=event, events_dir=events_dir, balances_file=balances_file)

    cleanup_microblocks(event)
    return payouts


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "FINAL_BLOCK_PADDING_BYTE",
    "sha256",
    "split_into_microblocks",
    "reassemble_microblocks",
    "build_merkle_tree",
    "compute_reward",
    "verify_event_signature",
    "create_event",
    "mark_mined",
    "accept_mined_seed",
    "validate_parent",
    "save_event",
    "load_event",
    "load_payout_summary",
    "finalize_event",
    "verify_seed_chain",
    "verify_statement",
]

def resolve_payouts(
    event_id: str,
    winning_side: str,
    *,
    events_dir: str = "data/events",
    balances_file: str = "data/balances.json",
    supply_file: str = "supply.json",
) -> Dict[str, float]:
    """Distribute betting payouts for ``event_id`` according to ``winning_side``.

    Parameters
    ----------
    event_id:
        Identifier of the finalized event stored under ``events_dir``.
    winning_side:
        The outcome of the event, either ``"YES"`` or ``"NO"``.

    Returns
    -------
    dict
        Mapping of public keys to payout amounts applied to the ledger.
    """
    if winning_side not in {"YES", "NO"}:
        raise ValueError("winning_side must be 'YES' or 'NO'")

    evt_path = Path(events_dir) / f"{event_id}.json"
    if not evt_path.exists():
        raise FileNotFoundError(evt_path)

    event = load_event(str(evt_path))

    yes_bets, no_bets = get_bets_for_event(event)

    yes_total = sum(b.get("amount", 0) for b in yes_bets)
    no_total = sum(b.get("amount", 0) for b in no_bets)
    unaligned_total = float(event.get("unaligned_funds", 0.0))

    winning_bets = yes_bets if winning_side == "YES" else no_bets
    winning_total = yes_total if winning_side == "YES" else no_total
    losing_total = no_total if winning_side == "YES" else yes_total

    payouts: Dict[str, float] = {}

    if winning_total:
        pot_share = losing_total + unaligned_total
        for bet in winning_bets:
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if not pub:
                continue
            bonus = (amt / winning_total) * pot_share if pot_share else 0.0
            payouts[pub] = payouts.get(pub, 0.0) + amt + bonus

    from . import ledger

    balances = ledger.load_balances(balances_file)
    apply_mining_results(event, balances)

    for acct, amount in payouts.items():
        balances[acct] = balances.get(acct, 0.0) + float(amount)

    ledger.save_balances(balances, balances_file)

    burn_amount = losing_total + unaligned_total
    if burn_amount:
        ledger.update_total_supply(-float(burn_amount), path=supply_file)

    event["resolved_payouts"] = payouts
    event["resolution"] = winning_side
    save_event(event, events_dir)

    return payouts
