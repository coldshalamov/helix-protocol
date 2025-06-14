from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from nacl import signing

from . import betting_interface, nested_miner
from .config import GENESIS_HASH
from .signature_utils import sign_data, verify_signature

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
    }

    originator_pub: Optional[str] = None
    originator_sig: Optional[str] = None
    if private_key is not None:
        key_bytes = base64.b64decode(private_key)
        signing_key = signing.SigningKey(key_bytes)
        originator_pub = base64.b64encode(signing_key.verify_key.encode()).decode(
            "ascii"
        )
        originator_sig = sign_data(statement.encode("utf-8"), private_key)

    event = {
        "header": header,
        "statement": statement,
        "microblocks": microblocks,
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
    depths = event.get("seed_depths", [])
    for miner_id, depth in zip(miners, depths):
        if miner_id is None or depth <= 0:
            continue
        reward = calculate_reward(BASE_REWARD, depth)
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


def accept_mined_seed(
    event: Dict[str, Any], index: int, seed_chain: List[bytes], *, miner: Optional[str] = None
) -> float:
    """Accept ``seed_chain`` for microblock ``index`` of ``event``."""

    seed = seed_chain[0]
    depth = len(seed_chain)

    block = event["microblocks"][index]
    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
    refund = 0.0

    microblock_size = event.get("header", {}).get(
        "microblock_size", DEFAULT_MICROBLOCK_SIZE
    )
    if len(seed) > microblock_size:
        raise ValueError("seed length exceeds microblock size")

    if event["seeds"][index] is None:
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            event["miners"][index] = miner
        mark_mined(event, index)
        return 0.0

    old_seed = event["seeds"][index]
    old_depth = event["seed_depths"][index]

    replace = False
    if len(seed) < len(old_seed):
        replace = True
    elif len(seed) == len(old_seed) and depth < old_depth:
        replace = True

    if replace:
        refund = event["rewards"][index] - reward
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            event["miners"][index] = miner
        event["refunds"][index] += refund
        print(
            f"Replaced seed at index {index}: length {len(old_seed)} depth {old_depth} -> length {len(seed)} depth {depth}"
        )

    return refund


def save_event(event: Dict[str, Any], directory: str) -> str:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"{event['header']['statement_id']}.json"
    data = event.copy()
    data["microblocks"] = [b.hex() for b in event["microblocks"]]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]
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

    payload = {
        k: v for k, v in header.items() if k not in {"originator_sig", "originator_pub"}
    }
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
    "create_event",
    "mark_mined",
    "nesting_penalty",
    "reward_for_depth",
    "calculate_reward",
    "accept_mined_seed",
    "finalize_event",
    "save_event",
    "verify_originator_signature",
    "verify_event_signature",
    "load_event",
    "validate_parent",
]

