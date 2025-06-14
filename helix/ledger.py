import json
from pathlib import Path
from typing import Dict


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


__all__ = ["load_balances", "save_balances"]
