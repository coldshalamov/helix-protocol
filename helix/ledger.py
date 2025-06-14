import json
from pathlib import Path
from typing import Dict, Tuple

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


__all__ = ["load_balances", "save_balances", "compression_stats"]
