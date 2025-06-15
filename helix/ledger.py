```python
import json
from pathlib import Path
from typing import Dict, Tuple, Any

from . import event_manager


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

    If the file does not exist, return ``0.0``.
    """
    file = Path(path)
    if not file.exists():
        return 0.0
    with open(file, "r", encoding="utf-8") as f:
        return float(json.load(f))


def update_total_supply(delta: float, path: str = "supply.json") -> None:
    """Increase total supply by ``delta`` and persist the new value."""
    total = get_total_supply(path) + float(delta)
    file = Path(path)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(total, f)


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
    if net_reward:
        update_total_supply(net_reward)

    for idx, miner in enumerate(miners):
        if miner:
            reward = rewards[idx] if idx < len(rewards) else 0.0
            balances[miner] = balances.get(miner, 0.0) + reward

        old_miner = refund_miners[idx]
        if old_miner:
            refund = refunds[idx] if idx < len(refunds) else 0.0
            balances[old_miner] = balances.get(old_miner, 0.0) + refund


__all__ = [
    "load_balances",
    "save_balances",
    "get_total_supply",
    "update_total_supply",
    "compression_stats",
    "apply_mining_results",
]
```
