#!/usr/bin/env python3
"""One-time utility to create the Helix genesis event."""

from __future__ import annotations

import json
from pathlib import Path

from helix.event_manager import create_event

STATEMENT = "Helix begins with this truth."
MICROBLOCK_SIZE = 3
KEYFILE = "wallet.txt"
EVENTS_DIR = "events"
GENESIS_FILE = "genesis.json"


def main() -> None:
    event = create_event(STATEMENT, microblock_size=MICROBLOCK_SIZE, keyfile=KEYFILE)
    Path(EVENTS_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(EVENTS_DIR) / GENESIS_FILE

    data = event.copy()
    data["microblocks"] = [b.hex() for b in event.get("microblocks", [])]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    genesis_hash = event["header"]["statement_id"]
    print(f"Saved genesis event to {path}")
    print(f"GENESIS_HASH = {genesis_hash}")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
