from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, TYPE_CHECKING

from nacl import signing
from . import betting_interface, nested_miner
from .config import GENESIS_HASH
from .signature_utils import sign_data, verify_signature

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry

DEFAULT_MICROBLOCK_SIZE = 8  # bytes
FINAL_BLOCK_PADDING_BYTE = b"\x00"
BASE_REWARD = 1.0

def nesting_penalty(depth: int) -> int:
    if depth < 1:
        raise ValueError("depth must be >= 1")
    return depth - 1

def reward_for_depth(depth: int) -> float:
    return BASE_REWARD / depth

def calculate_reward(base: float, depth: int) -> float:
    """Return the scaled reward for ``depth``."""
    if depth < 1:
        raise ValueError("depth must be >= 1")
    reward = base / depth
    return round(reward, 4)

def compute_reward(seed: bytes, original_size: int) -> float:
    """Return mining reward based on compression achieved.

    ``seed`` is the outermost seed used to regenerate a microblock.
    ``original_size`` is the length of the microblock prior to compression.

    The reward scales linearly with the number of bytes saved relative to the
    original size.
    """
    if original_size <= 0:
        raise ValueError("original_size must be > 0")
    saved = max(0, original_size - len(seed))
    return BASE_REWARD * saved / original_size

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def pad_block(data: bytes, size: int) -> bytes:
    if len(data) < size:
        return data + FINAL_BLOCK_PADDING_BYTE * (size - len(data))
    return data

def split_into_microblocks(
    statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE
) -> Tuple[List[bytes], int, int]:
    encoded = statement.encode("utf-8")
    total_len = len(encoded)
    block_count = math.ceil(total_len / microblock_size)
    blocks = [
        pad_block(encoded[i : i + microblock_size], microblock_size)
        for i in range(0, total_len, microblock_size)
    ]
    return blocks, block_count, total_len

def reassemble_microblocks(blocks: List[bytes]) -> str:
    payload = b"".join(blocks).rstrip(FINAL_BLOCK_PADDING_BYTE)
    return payload.decode("utf-8")

def build_merkle_tree(blocks: List[bytes]) -> Tuple[str, List[List[str]]]:
    """Return the Merkle root and full tree for ``blocks``.

    Leaves are SHA-256 hashes of each microblock. Each parent node is the
    SHA-256 hash of the concatenated child hashes. When a level has an odd
    number of nodes, the last hash is duplicated.
    """

    if not blocks:
        raise ValueError("no blocks to build merkle tree")

    level: List[bytes] = [hashlib.sha256(b).digest() for b in blocks]
    tree: List[List[bytes]] = [level]

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = [
            hashlib.sha256(level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
        tree.append(next_level)
        level = next_level

    root_hex = level[0].hex()
    tree_hex: List[List[str]] = [[h.hex() for h in lvl] for lvl in tree]
    return root_hex, tree_hex

def create_event(
    statement: str,
    microblock_size: int = DEFAULT_MICROBLOCK_SIZE,
    *,
    parent_id: str = GENESIS_HASH,
    private_key: Optional[str] = None,
    registry: Optional["StatementRegistry"] = None,
) -> Dict[str, Any]:
    microblocks, block_count, total_len = split_into_microblocks(
        statement, microblock_size
    )
    merkle_root, merkle_tree = build_merkle_tree(microblocks)
    statement_id = sha256(statement.encode("utf-8"))
    if registry is not None:
        if registry.has_id(statement_id):
            print(
                f"Duplicate statement_id {statement_id} already finalized; skipping"
            )
            raise ValueError("Duplicate statement")
        registry.check_and_add(statement)

    header = {
        "statement_id": statement_id,
        "original_length": total_len,
        "microblock_size": microblock_size,
        "block_count": block_count,
        "parent_id": parent_id,
        "merkle_root": merkle_root,
    }

    originator_pub: Optional[str] = None
    originator_sig: Optional[str] = None
    if private_key is not None:
        key_bytes = base64.b64decode(private_key)
        signing_key = signing.SigningKey(key_bytes)
        originator_pub = base64.b64encode(signing_key.verify_key.encode()).decode("ascii")
        originator_sig = sign_data(statement.encode("utf-8"), private_key)

    event = {
        "header": header,
        "statement": statement,
        "microblocks": microblocks,
        "merkle_tree": merkle_tree,
        "mined_status": [False] * block_count,
        "seeds": [None] * block_count,
        "seed_depths": [0] * block_count,
        "penalties": [0] * block_count,
        "rewards": [0.0] * block_count,
        "refunds": [0.0] * block_count,
        "is_closed": False,
        "bets": {"YES": [], "NO": []},
    }
    if originator_pub is not None:
        event["originator_pub"] = originator_pub
        event["originator_sig"] = originator_sig
    return event

def finalize_event(event: Dict[str, Any]) -> Dict[str, float]:
    """Resolve bets and miner rewards for ``event``.

    Returns a mapping of participant pubkeys to payout amounts which is also
    stored in ``event['payouts']``.
    """
    seeds = event.get("seeds", [])
    blocks = event.get("microblocks", [])
    if len(seeds) == len(blocks) and all(seeds):
        recombined: List[bytes] = []
        for idx, (enc, block) in enumerate(zip(seeds, blocks)):
            if not nested_miner.verify_nested_seed(enc, block):
                raise ValueError(f"invalid seed chain for microblock {idx}")
            depth, seed_len = nested_miner.decode_header(enc[0])
            offset = 1
            seed = enc[offset : offset + seed_len]
            offset += seed_len
            current = seed
            for _ in range(1, depth):
                next_seed = enc[offset : offset + len(block)]
                offset += len(block)
                current = nested_miner.G(current, len(block))
                current = next_seed
            final_block = nested_miner.G(current, len(block))
            recombined.append(final_block)
        statement = reassemble_microblocks(recombined)
        digest = sha256(statement.encode("utf-8"))
        if digest != event.get("header", {}).get("statement_id"):
            raise ValueError("final statement hash mismatch")

    yes_raw = event.get("bets", {}).get("YES", [])
    no_raw = event.get("bets", {}).get("NO", [])

    valid_yes = [b for b in yes_raw if betting_interface.verify_bet(b)]
    valid_no = [b for b in no_raw if betting_interface.verify_bet(b)]

    event["bets"]["YES"] = valid_yes
    event["bets"]["NO"] = valid_no

    yes_total = sum(b.get("amount", 0) for b in valid_yes)
    no_total = sum(b.get("amount", 0) for b in valid_no)

    success = yes_total > no_total
    winners = valid_yes if success else valid_no
    winner_total = yes_total if success else no_total

    pot = yes_total + no_total
    payouts: Dict[str, float] = {}

    originator = event.get("header", {}).get("originator_pub")
    if success and originator:
        refund = pot * 0.01
        payouts[originator] = payouts.get(originator, 0.0) + refund
        pot -= refund

    miners = event.get("miners", [])
    seeds = event.get("seeds", [])
    blocks = event.get("microblocks", [])
    for miner_id, seed_chain, block in zip(miners, seeds, blocks):
        if miner_id is None or seed_chain is None:
            continue
        if isinstance(seed_chain, (bytes, bytearray)):
            _, seed_len = nested_miner.decode_header(seed_chain[0])
            seed = seed_chain[1 : 1 + seed_len]
        else:
            seed = seed_chain[0]
        reward = compute_reward(seed, len(block))
        payouts[miner_id] = payouts.get(miner_id, 0.0) + reward

    if winner_total > 0:
        for bet in winners:
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if pub:
                payout = pot * (amt / winner_total)
                payouts[pub] = payouts.get(pub, 0.0) + payout

    event["payouts"] = payouts
    return payouts

def mark_mined(
    event: Dict[str, Any], index: int, *, events_dir: Optional[str] = None
) -> None:
    if event["is_closed"]:
        return
    event["mined_status"][index] = True
    if all(event["mined_status"]):
        event["is_closed"] = True
        print(f"Event {event['header']['statement_id']} is now closed.")
        finalize_event(event)
        if events_dir is not None:
            save_event(event, events_dir)

def accept_mined_seed(event: Dict[str, Any], index: int, seed_chain: List[bytes], *, miner: Optional[str] = None) -> float:
    """Record ``seed_chain`` as the mining solution for ``microblock[index]``.

    Only the first seed in ``seed_chain`` is validated against the microblock
    size.  Nested seeds are merely checked for correctness via
    :func:`nested_miner.verify_nested_seed`.
    """
    if isinstance(seed_chain, (bytes, bytearray)):
        depth, seed_len = nested_miner.decode_header(seed_chain[0])
        seed = seed_chain[1 : 1 + seed_len]
    else:
        seed = seed_chain[0]
        depth = len(seed_chain)
        seed_len = len(seed)
    block = event["microblocks"][index]
    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = compute_reward(seed, len(block))
    refund = 0.0

    microblock_size = event.get("header", {}).get("microblock_size", DEFAULT_MICROBLOCK_SIZE)
    if len(seed) > microblock_size:
        raise ValueError("seed length exceeds microblock size")

    if event["seeds"][index] is None:
        event["seeds"][index] = seed_chain
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            event["miners"][index] = miner
        if "refund_miners" in event:
            event["refund_miners"][index] = None
        mark_mined(event, index)
        return 0.0

    old_chain = event["seeds"][index]
    old_depth = event["seed_depths"][index]
    old_seed = old_chain[0] if isinstance(old_chain, list) else old_chain

    replace = False
    if len(seed) < len(old_seed):
        replace = True
    elif len(seed) == len(old_seed) and depth < old_depth:
        replace = True

    if replace:
        refund = event["rewards"][index] - reward
        event["seeds"][index] = seed_chain
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            old_miner = event["miners"][index]
            event["miners"][index] = miner
        else:
            old_miner = None
        if "refund_miners" in event:
            event["refund_miners"][index] = old_miner
        event["refunds"][index] += refund
        print(f"Replaced seed at index {index}: length {len(old_seed)} depth {old_depth} -> length {len(seed)} depth {depth}")

    return refund

def save_event(event: Dict[str, Any], directory: str) -> str:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"{event['header']['statement_id']}.json"
    data = event.copy()
    data["microblocks"] = [b.hex() for b in event["microblocks"]]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]
    if "merkle_tree" in data:
        data["merkle_tree"] = data["merkle_tree"]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(filename)

def verify_originator_signature(event: Dict[str, Any]) -> bool:
    """Verify the originator signature attached to ``event``."""
    header = event.get("header", {})
    signature = header.get("originator_sig")
    pubkey = header.get("originator_pub")

    if signature is None or pubkey is None:
        return False

    payload = {k: v for k, v in header.items() if k not in {"originator_sig", "originator_pub"}}
    header_hash = sha256(repr(payload).encode("utf-8")).encode("utf-8")

    if not verify_signature(header_hash, signature, pubkey):
        raise ValueError("Invalid originator signature")

    return True

def verify_event_signature(event: Dict[str, Any]) -> bool:
    """Verify the signature for ``event`` recorded at the root level."""
    signature = event.get("originator_sig")
    pubkey = event.get("originator_pub")
    statement = event.get("statement")

    if signature is None or pubkey is None or statement is None:
        return False

    if not verify_signature(statement.encode("utf-8"), signature, pubkey):
        raise ValueError("Invalid event signature")

    return True

def validate_parent(event: Dict[str, Any], *, ancestors: Optional[set[str]] = None) -> None:
    if ancestors is None:
        ancestors = {GENESIS_HASH}
    parent_id = event.get("header", {}).get("parent_id")
    if parent_id not in ancestors:
        raise ValueError("invalid parent_id")

def load_event(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["microblocks"] = [bytes.fromhex(b) for b in data.get("microblocks", [])]
    if "seeds" in data:
        data["seeds"] = [bytes.fromhex(s) if isinstance(s, str) and s else None for s in data["seeds"]]
    if "merkle_tree" not in data and data.get("microblocks"):
        root, tree = build_merkle_tree(data["microblocks"])
        data["merkle_tree"] = tree
        if "header" in data:
            data["header"].setdefault("merkle_root", root)
    block_count = len(data.get("microblocks", []))
    block_count = len(data.get("microblocks", []))
    data.setdefault("seed_depths", [0] * block_count)
    data.setdefault("penalties", [0] * block_count)
    data.setdefault("rewards", [0.0] * block_count)
    data.setdefault("refunds", [0.0] * block_count)
    validate_parent(data)
    return data

__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "FINAL_BLOCK_PADDING_BYTE",
    "split_into_microblocks",
    "reassemble_microblocks",
    "build_merkle_tree",
    "create_event",
    "mark_mined",
    "nesting_penalty",
    "reward_for_depth",
    "calculate_reward",
    "compute_reward",
    "accept_mined_seed",
    "finalize_event",
    "save_event",
    "verify_originator_signature",
    "verify_event_signature",
    "load_event",
    "validate_parent",
]
