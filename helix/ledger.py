import json
import inspect
import time
from pathlib import Path
from typing import Dict, Tuple, Any

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
    """Apply mining rewards and refunds from ``event`` to ``balances``.

    ``event`` should contain ``miners`` listing the miner for each microblock.
    If ``refund_miners`` is present, refund amounts are credited to the miner
    that was replaced for that microblock.
    """

    miners = event.get("miners")
    if not miners:
        return

    rewards = event.get("rewards", [])
    refunds = event.get("refunds", [])
    refund_miners = event.get("refund_miners", [None] * len(miners))

    net_reward = sum(rewards) - sum(refunds)

    for idx, miner in enumerate(miners):
        if miner:
            reward = rewards[idx] if idx < len(rewards) else 0.0
            balances[miner] = balances.get(miner, 0.0) + reward

        old_miner = refund_miners[idx]
        if old_miner:
            refund = refunds[idx] if idx < len(refunds) else 0.0
            balances[old_miner] = balances.get(old_miner, 0.0) + refund


def apply_delta_bonus(miner: str, balances: Dict[str, float], amount: float) -> None:
    """Credit ``amount`` HLX delta bonus to ``miner``."""

    if not miner:
        return
    balances[miner] = balances.get(miner, 0.0) + float(amount)

__all__ = [
    "load_balances",
    "save_balances",
    "get_total_supply",
    "compression_stats",
    "apply_mining_results",
    "apply_delta_bonus",
    "log_ledger_event",
]
