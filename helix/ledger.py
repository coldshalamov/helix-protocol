import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Tuple

from . import event_manager

_BLOCK_HEADERS: Dict[str, Dict[str, Any]] = {}
_PENDING_BONUS: Dict[str, str] = {}
_VERIFICATION_QUEUE: list[tuple[Dict[str, Any] | None, bool, str]] = []
_BONUS_AMOUNT = 2.0


def delta_claim_valid(current: Dict[str, Any], parent: Dict[str, Any]) -> bool:
    """Return ``True`` if ``current`` accurately reports time delta from ``parent``."""

    try:
        if current.get("parent_id") != parent.get("block_id"):
            return True

        cur_ts = datetime.fromisoformat(current.get("timestamp"))
        parent_ts = datetime.fromisoformat(parent.get("timestamp"))
        actual_delta = (cur_ts - parent_ts).total_seconds()
        claimed = float(current.get("delta_seconds", 0))
        return abs(actual_delta - claimed) <= 10
    except Exception:
        return False


def get_total_supply(path: str = "supply.json") -> float:
    """Return the recorded total HLX supply."""
    if not os.path.exists(path):
        return 0.0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return float(json.load(fh).get("total", 0.0))
    except Exception:
        return 0.0


def load_balances(path: str) -> Dict[str, float]:
    """Return balances mapping from ``path`` if it exists."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return {str(k): float(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def save_balances(balances: Dict[str, float], path: str) -> None:
    """Persist ``balances`` to ``path``."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(balances, fh, indent=2)


def log_ledger_event(
    action: str,
    wallet: str,
    amount: float,
    reason: str,
    block_hash: str,
    *,
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    entry = {
        "action": action,
        "wallet": wallet,
        "amount": amount,
        "reason": reason,
        "block": block_hash,
        "timestamp": int(time.time()),
    }
    with open(journal_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _update_total_supply(delta: float, *, path: str = "supply.json") -> None:
    total = 0.0
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                total = float(json.load(fh).get("total", 0.0))
        except Exception:
            total = 0.0
    total += delta
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"total": total}, fh)


def apply_delta_bonus(
    wallet: str,
    balances: Dict[str, float],
    amount: float,
    *,
    block_hash: str = "",
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    balances[wallet] = balances.get(wallet, 0.0) + amount
    log_ledger_event("mint", wallet, amount, "delta_bonus", block_hash, journal_file=journal_file)


def apply_delta_penalty(
    wallet: str,
    balances: Dict[str, float],
    amount: float,
    *,
    block_hash: str = "",
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    balances[wallet] = balances.get(wallet, 0.0) - amount
    log_ledger_event("burn", wallet, amount, "delta_penalty", block_hash, journal_file=journal_file)


def compression_stats(events_dir: str) -> Tuple[int, float]:
    """Return total bytes saved and HLX minted for events in ``events_dir``."""
    total_saved = 0
    total_hlx = 0.0
    if not os.path.isdir(events_dir):
        return total_saved, total_hlx

    for path in os.listdir(events_dir):
        if not path.endswith(".json"):
            continue
        evt = event_manager.load_event(os.path.join(events_dir, path))
        seeds = evt.get("seeds", [])
        microblocks = evt.get("microblocks", [])
        rewards = evt.get("rewards", [])
        refunds = evt.get("refunds", [])
        total_hlx += sum(rewards) - sum(refunds)
        for blk, seed in zip(microblocks, seeds):
            if seed is None:
                continue
            blk_bytes = bytes.fromhex(blk) if isinstance(blk, str) else blk
            seed_bytes = bytes(seed) if isinstance(seed, list) else seed
            total_saved += max(0, len(blk_bytes) - len(seed_bytes))
    return total_saved, total_hlx


def apply_mining_results(
    event: Dict[str, Any],
    balances: Dict[str, float],
    *,
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Apply compression rewards and delta bonuses for ``event`` to ``balances``."""
    miners = event.get("miners") or []
    microblocks = event.get("microblocks") or []
    seeds = event.get("seeds") or []
    header = event.get("block_header", {})
    block_hash = header.get("block_id", event.get("header", {}).get("statement_id", ""))

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

    # Compression rewards with stacking
    for idx, miner in enumerate(miners):
        if not miner or idx >= len(seeds) or idx >= len(microblocks):
            continue

        seed_bytes = _to_bytes(seeds[idx])
        block_hex = microblocks[idx]
        block_bytes = (
            bytes.fromhex(block_hex) if isinstance(block_hex, str) else block_hex
        )

        if not seed_bytes or not isinstance(block_bytes, (bytes, bytearray)):
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
                log_ledger_event(
                    "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                )
            elif granted and prev_hdr:
                parent = _BLOCK_HEADERS.get(prev_hdr.get("parent_id"))
                if parent and delta_claim_valid(prev_hdr, parent):
                    balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                    log_ledger_event(
                        "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                    )
                else:
                    log_ledger_event(
                        "burn", miner, _BONUS_AMOUNT, "delta_penalty", grant_block
                    )
            else:
                balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                log_ledger_event(
                    "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                )

    if header:
        # Pay bonus to previous block finalizer
        prev_hdr = _BLOCK_HEADERS.get(header.get("parent_id"))
        if prev_hdr:
            prev_finalizer = prev_hdr.get("finalizer") or prev_hdr.get("miner")
            if prev_finalizer:
                balances[prev_finalizer] = balances.get(prev_finalizer, 0.0) + _BONUS_AMOUNT
                log_ledger_event(
                    "mint", prev_finalizer, _BONUS_AMOUNT, "delta_bonus", block_id
                )

        # Queue verification for this block's grant
        if block_id:
            _BLOCK_HEADERS[block_id] = header
            _VERIFICATION_QUEUE.append((prev_hdr, bool(prev_hdr), block_id))
            if current_finalizer:
                _PENDING_BONUS[block_id] = current_finalizer


__all__ = [
    "load_balances",
    "save_balances",
    "log_ledger_event",
    "apply_delta_bonus",
    "apply_delta_penalty",
    "apply_mining_results",
    "compression_stats",
    "get_total_supply",
    "_update_total_supply",
]
