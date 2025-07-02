from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List

from . import blockchain, betting_interface
from .config import GENESIS_HASH
from .minihelix import G, DEFAULT_MICROBLOCK_SIZE


LAST_FINALIZED_HASH = ""
LAST_FINALIZED_TIME = 0.0


def sha256(data: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


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
    regen_data = b"".join(G(s, microblock_size) for s in ordered_seeds).rstrip(b"\x00")
    assert sha256(regen_data) == evt_id
    assert regen_data.decode("utf-8", errors="replace") == event["statement"]

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

    return payouts
