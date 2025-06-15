import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import GENESIS_HASH
from .minihelix import sha256
from .signature_utils import verify_signature
from .merkle import build_merkle_tree

DEFAULT_MICROBLOCK_SIZE = 8
FINAL_BLOCK_PADDING_BYTE = b"\x00"

def nesting_penalty(depth: int) -> int:
    return depth * 5

def reward_for_depth(depth: int) -> float:
    return max(1.0 - 0.1 * depth, 0.1)

def calculate_reward(seed: bytes, depth: int, microblock_size: int) -> float:
    if len(seed) > microblock_size:
        raise ValueError("Seed too large")
    return reward_for_depth(depth)

def mark_mined(event: Dict[str, Any], index: int) -> None:
    event["mined_status"][index] = True
    if all(event["mined_status"]):
        event["is_closed"] = True
        print(f"Event {event['header']['statement_id']} is now closed.")
        finalize_event(event)

def finalize_event(event: Dict[str, Any]) -> None:
    print(f"Finalizing event {event['header']['statement_id']}")

def accept_mined_seed(event: Dict[str, Any], index: int, seed_chain: List[bytes] | bytes, *, miner: Optional[str] = None) -> float:
    from . import nested_miner  # Avoid circular imports
    block = event["microblocks"][index]
    if isinstance(seed_chain, (bytes, bytearray)):
        depth, seed_len = nested_miner.decode_header(seed_chain[0])
        seed = seed_chain[1:1 + seed_len]
    else:
        seed = seed_chain[0]
        depth = len(seed_chain)

    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
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
    signature = event.get("originator_sig")
    pubkey = event.get("originator_pub")
    statement = event.get("statement")
    if signature is None or pubkey is None or statement is None:
        return False
    if not verify_signature(statement.encode("utf-8"), signature, pubkey):
        raise ValueError("Invalid event signature")
    return True

def validate_parent(event: Dict[str, Any], *, ancestors: Optional[Set[str]] = None) -> None:
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
    data.setdefault("seed_depths", [0] * block_count)
    data.setdefault("penalties", [0] * block_count)
    data.setdefault("rewards", [0.0] * block_count)
    data.setdefault("refunds", [0.0] * block_count)
    validate_parent(data)
    return data
