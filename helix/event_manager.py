from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from .signature_utils import verify_signature


def accept_mined_seed(event: Dict[str, Any], index: int, seed_chain: List[bytes], *, miner: Optional[str] = None) -> float:
    """Accept ``seed_chain`` for microblock ``index`` of ``event``.

    ``seed_chain`` contains the starting seed followed by any intermediate
    values.  Its length represents the depth of the nested mining.  The chain
    is verified with :func:`verify_nested_seed` before it is applied.
    """
    seed = seed_chain[0]
    depth = len(seed_chain)

    block = event["microblocks"][index]
    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
    refund = 0.0

    microblock_size = event.get("header", {}).get("microblock_size", DEFAULT_MICROBLOCK_SIZE)
    if len(seed) > microblock_size:
        raise ValueError("seed length exceeds microblock size")

    if event["seeds"][index] is None:
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            event["miners"][index] = miner
        if "refund_miners" in event:
            event["refund_miners"][index] = None
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
            old_miner = event["miners"][index]
            event["miners"][index] = miner
        else:
            old_miner = None
        if "refund_miners" in event:
            event["refund_miners"][index] = old_miner
        event["refunds"][index] += refund
        print(
            f"Replaced seed at index {index}: length {len(old_seed)} depth {old_depth} -> length {len(seed)} depth {depth}"
        )

    return refund


def verify_event_signature(event: Dict[str, Any]) -> bool:
    """Verify the originator signature on the event statement.

    The ``originator_pub`` key must correspond to the private key that
    produced ``originator_sig`` over the event's ``statement``.  If the
    signature is present but invalid a :class:`ValueError` is raised.  The
    function returns ``True`` when a valid signature is present and ``False``
    when the event lacks signature information.
    """

    signature = event.get("originator_sig")
    pubkey = event.get("originator_pub")
    statement = event.get("statement")

    if signature is None or pubkey is None or statement is None:
        return False

    if not verify_signature(statement.encode("utf-8"), signature, pubkey):
        raise ValueError("Invalid event signature")

    return True


def verify_originator_signature(event: Dict[str, Any]) -> bool:
    """Verify the signature embedded in the event header."""

    header = event.get("header", {})
    signature = header.get("originator_sig")
    pubkey = header.get("originator_pub")

    if signature is None or pubkey is None:
        return False

    payload = {k: v for k, v in header.items() if k not in {"originator_sig", "originator_pub"}}
    header_hash = hashlib.sha256(repr(payload).encode("utf-8")).digest()

    if not verify_signature(header_hash, signature, pubkey):
        raise ValueError("Invalid originator signature")

    return True
