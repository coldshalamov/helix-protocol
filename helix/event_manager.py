import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from datetime import datetime
from nacl import signing

from .config import GENESIS_HASH
from .signature_utils import verify_signature, sign_data
from .merkle_utils import build_merkle_tree
from . import nested_miner, betting_interface

DEFAULT_MICROBLOCK_SIZE = 8
FINAL_BLOCK_PADDING_BYTE = b"\x00"

def sha256(data: bytes) -> str:
    """Return hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()

def nesting_penalty(depth: int) -> int:
    return depth * 5

def reward_for_depth(depth: int) -> float:
    return max(1.0 - 0.1 * depth, 0.1)

def calculate_reward(seed: bytes, depth: int, microblock_size: int) -> float:
    if len(seed) > microblock_size:
        raise ValueError("Seed too large")
    return reward_for_depth(depth)

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
    return payload.decode("utf-8", errors="replace")

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
            print(f"Duplicate statement_id {statement_id} already finalized; skipping")
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

def mark_mined(event: Dict[str, Any], index: int) -> None:
    event["mined_status"][index] = True
    if all(event["mined_status"]):
        event["is_closed"] = True
        print(f"Event {event['header']['statement_id']} is now closed.")

def finalize_event(
    event: Dict[str, Any], *, node_id: Optional[str] = None, chain_file: str = "blockchain.jsonl"
) -> Dict[str, float]:
    """Resolve bets, calculate rewards and append a finalized block.

    Parameters
    ----------
    event:
        Event dictionary with mining information.
    node_id:
        Identifier (usually public key) of the miner finalizing the event.
    chain_file:
        Location of the blockchain file. Defaults to ``blockchain.jsonl``.
    """
    if not event.get("is_closed"):
        raise ValueError("event is not fully mined")

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

    originator = event.get("originator_pub") or event.get("header", {}).get("originator_pub")
    if success and originator:
        refund = pot * 0.01
        payouts[originator] = payouts.get(originator, 0.0) + refund
        pot -= refund

    if winner_total > 0:
        for bet in winners:
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if pub:
                payout = pot * (amt / winner_total)
                payouts[pub] = payouts.get(pub, 0.0) + payout

    event["payouts"] = payouts

    hdr_serializable = {
        k: (v.hex() if isinstance(v, (bytes, bytearray)) else v)
        for k, v in event["header"].items()
    }

    evt_id = hdr_serializable.get("statement_id")

    # Determine parent block from existing chain if available
    parent_id = GENESIS_HASH
    try:
        import blockchain as _bc
    except Exception:  # pragma: no cover - fallback when module missing
        _bc = None

    if _bc is not None:
        if hasattr(_bc, "get_chain_tip"):
            try:
                parent_id = _bc.get_chain_tip(chain_file)
            except Exception:
                parent_id = GENESIS_HASH
        else:
            try:
                chain = _bc.load_chain(chain_file)
                if chain:
                    last = chain[-1]
                    parent_id = last.get("block_id", last.get("id", GENESIS_HASH))
            except Exception:
                parent_id = GENESIS_HASH

    block_content = {
        "parent_id": parent_id,
        "event_ids": [evt_id],
        "timestamp": datetime.utcnow().isoformat(),
        "miner": node_id,
    }
    block_id = sha256(json.dumps(block_content, sort_keys=True).encode("utf-8"))
    block_content["block_id"] = block_id

    if _bc is not None and hasattr(_bc, "append_block"):
        _bc.append_block(block_content, chain_file)
    else:
        # Fallback JSONL writer
        line = json.dumps(block_content, separators=(",", ":"))
        path = Path(chain_file)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return payouts

def accept_mined_seed(
    event: Dict[str, Any],
    index: int,
    seed_chain: List[bytes] | bytes,
    *,
    miner: Optional[str] = None,
) -> float:
    block = event["microblocks"][index]
    if isinstance(seed_chain, (bytes, bytearray)):
        depth = seed_chain[0]
        seed_len = seed_chain[1]
        seed = seed_chain[2 : 2 + seed_len]
    else:
        seed = seed_chain[0]
        depth = len(seed_chain)

    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
    refund = 0.0

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
    if isinstance(old_chain, (bytes, bytearray)):
        old_seed_len = old_chain[1]
        old_seed = old_chain[2 : 2 + old_seed_len]
    else:
        old_seed = old_chain[0]

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
        new_tree = []
        for level in data["merkle_tree"]:
            new_level = [h.hex() if isinstance(h, (bytes, bytearray)) else h for h in level]
            new_tree.append(new_level)
        data["merkle_tree"] = new_tree
    if isinstance(data.get("header", {}).get("merkle_root"), (bytes, bytearray)):
        data["header"]["merkle_root"] = data["header"]["merkle_root"].hex()
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


def append_block(block_header: Dict[str, Any], chain_file: str = "blocks.json") -> None:
    """Append ``block_header`` to the blockchain file."""
    path = Path(chain_file)
    chain: List[Dict[str, Any]] = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                chain = json.load(f)
            except Exception:
                chain = []
    chain.append(block_header)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chain, f, indent=2)
