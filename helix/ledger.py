import json
import inspect
import time
from pathlib import Path
from typing import Dict, Tuple, Any
from datetime import datetime

from . import event_manager


def log_ledger_event(
    action: str,
    wallet: str,
    amount: float,
    reason: str,
    block_hash: str,
    *,
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Append a ledger event to the journal."""

    entry = {
        "action": action,
        "wallet": wallet,
        "amount": float(amount),
        "reason": reason,
        "block": block_hash,
        "timestamp": int(time.time()),
    }
    with open(journal_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def load_balances(path: str) -> Dict[str, float]:
    """Return wallet balances from ``path`` if it exists, else empty dict."""
    file = Path(path)
    if not file.exists():
        return {}
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_balances(balances: Dict[str, float], path: str) -> None:
    """Persist ``balances`` to ``path`` as JSON."""
    file = Path(path)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(balances, f, indent=2)


def get_total_supply(path: str = "supply.json") -> float:
    """Return total HLX supply stored in ``path``.

    The file is expected to contain a JSON object with a ``"total"`` field.
    If the file does not exist, ``0.0`` is returned.
    """
    file = Path(path)
    if not file.exists():
        return 0.0
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return float(data.get("total", 0.0))
    return float(data)


def _update_total_supply(delta: float, path: str = "supply.json") -> None:
    """Increase total supply by ``delta`` and persist the new value.

    This helper is restricted to :func:`chain_validator.validate_and_mint` to
    avoid arbitrary minting of HLX. A :class:`PermissionError` is raised if the
    caller is not the validator.
    """
    frame = inspect.currentframe()
    if frame is not None:
        caller = frame.f_back
        mod = caller.f_globals.get("__name__") if caller else None
        func = caller.f_code.co_name if caller else None
        if mod != "chain_validator" or func != "validate_and_mint":
            raise PermissionError(
                "_update_total_supply can only be called from chain_validator.validate_and_mint"
            )

    total = get_total_supply(path) + float(delta)
    file = Path(path)
    with open(file, "w", encoding="utf-8") as f:
        json.dump({"total": total}, f, indent=2)


def compression_stats(events_dir: str) -> Tuple[int, float]:
    """Return total bytes saved and HLX earned across finalized events.

    Parameters
    ----------
    events_dir:
        Directory containing event JSON files.
    """
    path = Path(events_dir)
    if not path.exists():
        return 0, 0.0

    saved = 0
    hlx = 0.0
    for event_file in path.glob("*.json"):
        event = event_manager.load_event(str(event_file))
        if not event.get("is_closed"):
            continue
        micro_size = event["header"].get(
            "microblock_size", event_manager.DEFAULT_MICROBLOCK_SIZE
        )
        for seed in event.get("seeds", []):
            if seed is None:
                continue
            saved += max(0, micro_size - len(seed))
        rewards = event.get("rewards", [])
        refunds = event.get("refunds", [])
        hlx += sum(rewards) - sum(refunds)

    return saved, hlx


def apply_mining_results(
    event: Dict[str, Any],
    balances: Dict[str, float],
    *,
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Apply compression rewards recorded in ``event`` to ``balances``.

    Rewards are calculated from the byte savings of each mined microblock and
    applied cumulatively.  If a microblock is further compressed later, only the
    additional savings are rewarded to the new miner.  All payouts are logged to
    ``journal_file`` with ``compression_reward`` as the reason.
    """

    miners = event.get("miners") or []
    microblocks = event.get("microblocks") or []
    seeds = event.get("seeds") or []
    if not miners or not microblocks or not seeds:
        return

    block_hash = event.get("block_header", {}).get(
        "block_id", event.get("header", {}).get("statement_id", "")
    )

    credited = event.setdefault("_credited_lengths", [0] * len(miners))

    def _to_bytes(seed_entry: Any) -> bytes | None:
        if seed_entry is None:
            return None
        if isinstance(seed_entry, (bytes, bytearray)):
            return bytes(seed_entry)
        if isinstance(seed_entry, list):
            if not seed_entry:
                return None
            if isinstance(seed_entry[0], int):
                return bytes(seed_entry)
            return _to_bytes(seed_entry[-1])
        return None

    for idx, miner in enumerate(miners):
        if not miner:
            continue

        seed_bytes = _to_bytes(seeds[idx]) if idx < len(seeds) else None
        block_hex = microblocks[idx] if idx < len(microblocks) else ""
        block_bytes = bytes.fromhex(block_hex) if block_hex else b""

        if not seed_bytes or len(seed_bytes) >= len(block_bytes):
            continue

        saved = len(block_bytes) - len(seed_bytes)
        already = credited[idx] if idx < len(credited) else 0
        delta = saved - already
        if delta <= 0:
            continue

        balances[miner] = balances.get(miner, 0.0) + float(delta)
        log_ledger_event(
            "mint",
            miner,
            float(delta),
            "compression_reward",
            block_hash,
            journal_file=journal_file,
        )
        credited[idx] = saved

    event["_credited_lengths"] = credited


def apply_delta_bonus(
    miner: str,
    balances: Dict[str, float],
    amount: float,
    *,
    block_hash: str = "",
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Credit ``amount`` HLX delta bonus to ``miner`` and log the event."""

    if not miner:
        return
    balances[miner] = balances.get(miner, 0.0) + float(amount)
    log_ledger_event(
        "mint",
        miner,
        float(amount),
        "delta_bonus",
        block_hash,
        journal_file=journal_file,
    )


def apply_delta_penalty(
    miner: str,
    balances: Dict[str, float],
    amount: float,
    *,
    block_hash: str = "",
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Remove ``amount`` HLX from ``miner`` as a delta penalty."""

    if not miner:
        return
    balances[miner] = balances.get(miner, 0.0) - float(amount)
    log_ledger_event(
        "burn",
        miner,
        float(amount),
        "delta_penalty",
        block_hash,
        journal_file=journal_file,
    )


def delta_claim_valid(
    prev_block: Dict[str, Any], parent_block: Dict[str, Any], *, threshold: float = 10.0
) -> bool:
    """Return ``True`` if ``prev_block``'s delta claim matches the actual gap.

    The difference between ``prev_block['delta_seconds']`` and the time
    difference of ``prev_block`` and ``parent_block`` is compared against
    ``threshold`` seconds.
    """

    try:
        ts_prev = datetime.fromisoformat(prev_block["timestamp"]).timestamp()
        ts_parent = datetime.fromisoformat(parent_block["timestamp"]).timestamp()
    except Exception:
        return True

    claimed = float(prev_block.get("delta_seconds", 0.0))
    actual = ts_prev - ts_parent
    return abs(claimed - actual) <= threshold


def record_compression_rewards(
    event: Dict[str, Any],
    *,
    bonus: float = 0.0,
    journal_file: str = "ledger_journal.jsonl",
    supply_file: str = "supply.json",
) -> float:
    """Record compression rewards for ``event`` in the ledger.

    Each microblock miner is credited with HLX equal to the bytes saved by its
    submitted seed. Optionally ``bonus`` HLX is awarded to the miner of the last
    microblock for compiling the final block. The total minted amount is also
    added to the running supply.
    """

    if not event.get("is_closed"):
        raise ValueError("event must be closed before rewarding")

    header = event.get("header", {})
    micro_size = int(
        header.get("microblock_size", event_manager.DEFAULT_MICROBLOCK_SIZE)
    )
    seeds = event.get("seeds", [])
    miners = event.get("miners", [None] * len(seeds))
    block_hash = event.get("block_header", {}).get(
        "block_id", header.get("statement_id", "")
    )

    total = 0.0

    def _to_bytes(seed_entry: Any) -> bytes | None:
        if seed_entry is None:
            return None
        if isinstance(seed_entry, (bytes, bytearray)):
            return bytes(seed_entry)
        if isinstance(seed_entry, list):
            if not seed_entry:
                return None
            if isinstance(seed_entry[0], int):
                return bytes(seed_entry)
            # assume nested list of seeds, last element is innermost seed
            return _to_bytes(seed_entry[-1])
        return None

    for idx, seed_entry in enumerate(seeds):
        miner = miners[idx] if idx < len(miners) else None
        seed_bytes = _to_bytes(seed_entry)
        if miner and seed_bytes:
            reward = float(max(0, micro_size - len(seed_bytes)))
            if reward > 0:
                log_ledger_event(
                    "mint",
                    miner,
                    reward,
                    "compression_reward",
                    block_hash,
                    journal_file=journal_file,
                )
                total += reward

    if miners and miners[-1] and bonus:
        log_ledger_event(
            "mint",
            miners[-1],
            float(bonus),
            "finalization_bonus",
            block_hash,
            journal_file=journal_file,
        )
        total += float(bonus)

    if total:
        _update_total_supply(total, path=supply_file)

    return total


__all__ = [
    "load_balances",
    "save_balances",
    "get_total_supply",
    "compression_stats",
    "apply_mining_results",
    "apply_delta_bonus",
    "apply_delta_penalty",
    "delta_claim_valid",
    "log_ledger_event",
    "record_compression_rewards",
]
