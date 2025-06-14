#!/usr/bin/env python3
"""Command-line helper to run the genesis setup.

This script executes :func:`setup_genesis.main` and then prints a
short summary of the resulting balances and mined microblocks.  It is
intended as a lightweight entry point so users can test the genesis
block creation without needing to explore the full codebase.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from setup_genesis import main as setup_main, BALANCES_FILE, EVENTS_DIR
except Exception as exc:  # pragma: no cover - import failure
    raise SystemExit(f"Failed to import setup_genesis: {exc}")


def _show_balances() -> None:
    path = Path(BALANCES_FILE)
    if not path.exists():
        print("No balances file created")
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            balances = json.load(fh)
    except Exception as exc:  # pragma: no cover - unexpected file error
        print(f"Error reading balances: {exc}")
        return
    print("Balances:")
    print(json.dumps(balances, indent=2))


def _show_microblocks() -> None:
    events = Path(EVENTS_DIR)
    if not events.exists():
        print("No events directory found")
        return
    for path in sorted(events.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                event = json.load(fh)
        except Exception as exc:  # pragma: no cover - unexpected file error
            print(f"Error reading {path.name}: {exc}")
            continue
        mined = sum(1 for m in event.get("mined_status", []) if m)
        total = len(event.get("microblocks", []))
        print(f"{path.name}: {mined}/{total} microblocks mined")


def main() -> None:
    try:
        setup_main()
    except Exception as exc:  # pragma: no cover - runtime failure
        print(f"Error while running setup_genesis: {exc}")
        sys.exit(1)

    _show_balances()
    _show_microblocks()


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
