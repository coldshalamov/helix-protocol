import json
import inspect
import time
from pathlib import Path
from typing import Dict, Tuple, Any
from datetime import datetime

from . import event_manager

# Tracking for compression rewards and delta bonus verification
_REWARD_HISTORY: dict[tuple[str, int], int] = {}
_BLOCK_HEADERS: dict[str, dict[str, Any]] = {}
_PENDING_BONUS: dict[str, str] = {}
_VERIFICATION_QUEUE: list[tuple[dict[str, Any] | None, bool, str]] = []

# Fixed delta bonus amount minted when a block is finalized
_BONUS_AMOUNT = 1.0


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
            raise PermissionError("_update_total_supply can only be called from chain_validator.validate_and_mint")

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


def apply_mining_results(event: Dict[str, Any], balances: Dict[str, float]) -> None:
    """Apply compression rewards and delta bonuses for ``event``."""

    miners = event.get("miners") or []
    seeds = event.get("seeds", [])
    microblocks = event.get("microblocks", [])
    header = event.get("block_header", {})
    evt_id = header.get("block_id", event.get("header", {}).get("statement_id", ""))

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

    # Compression rewards with stacking
    for idx, miner in enumerate(miners):
        if not miner:
            continue
        if idx >= len(seeds) or idx >= len(microblocks):
            continue
        seed_bytes = _to_bytes(seeds[idx])
        block_bytes = microblocks[idx]
        if not seed_bytes or not isinstance(block_bytes, (bytes, bytearray)):
            continue
        saved = max(0, len(block_bytes) - len(seed_bytes))
        key = (evt_id, idx)
        prev = _REWARD_HISTORY.get(key, 0)
        delta = saved - prev
        if delta > 0:
            _REWARD_HISTORY[key] = saved
            balances[miner] = balances.get(miner, 0.0) + float(delta)
            log_ledger_event(
                "mint",
                miner,
                float(delta),
                "compression_reward",
                evt_id,
            )

    # Delta bonus logic
    global _BLOCK_HEADERS, _PENDING_BONUS, _VERIFICATION_QUEUE

    current_finalizer = header.get("finalizer") or header.get("miner")
    block_id = header.get("block_id")

    # Process queued verification from prior block
    if _VERIFICATION_QUEUE:
        prev_hdr, granted, grant_block = _VERIFICATION_QUEUE.pop(0)
        miner = _PENDING_BONUS.pop(grant_block, None)
        if miner:
            if miner == current_finalizer:
                balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                log_ledger_event("mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block)
            elif granted and prev_hdr:
                parent = _BLOCK_HEADERS.get(prev_hdr.get("parent_id"))
                if parent and delta_claim_valid(prev_hdr, parent):
                    balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                    log_ledger_event("mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block)
                else:
                    log_ledger_event("burn", miner, _BONUS_AMOUNT, "delta_penalty", grant_block)
            else:
                balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                log_ledger_event("mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block)

    if header:
        # Pay bonus to previous block finalizer
        prev_hdr = _BLOCK_HEADERS.get(header.get("parent_id"))
        if prev_hdr:
            prev_finalizer = prev_hdr.get("finalizer") or prev_hdr.get("miner")
            if prev_finalizer:
                balances[prev_finalizer] = balances.get(prev_finalizer, 0.0) + _BONUS_AMOUNT
                log_ledger_event("mint", prev_finalizer, _BONUS_AMOUNT, "delta_bonus", block_id)

        # Queue verification for this block's grant
        if block_id:
            _BLOCK_HEADERS[block_id] = header
            _VERIFICATION_QUEUE.append((prev_hdr, bool(prev_hdr), block_id))
            if current_finalizer:
                _PENDING_BONUS[block_id] = current_finalizer


def apply_delta_bonus(miner: str, balances: Dict[str, float], amount: float) -> None:
    """Credit ``amount`` HLX delta bonus to ``miner``."""

    if not miner:
        return
    balances[miner] = balances.get(miner, 0.0) + float(amount)


def delta_claim_valid(prev_block: Dict[str, Any], parent_block: Dict[str, Any], *, threshold: float = 10.0) -> bool:
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
    "delta_claim_valid",
    "log_ledger_event",
    "record_compression_rewards",
]
