#!/usr/bin/env python3
"""One-time utility to create the Helix genesis event.

This script creates, mines and signs the Helix genesis event and writes the
resulting JSON to ``genesis.json`` in the repository root.  It relies on
``minihelix.mine_seed`` for proof of work and ``signature_utils`` for the
Ed25519 signature handling.
"""

from __future__ import annotations

import json
from pathlib import Path

import hashlib

from helix.event_manager import create_event, mark_mined
from helix.minihelix import mine_seed
from helix.signature_utils import load_or_create_keys

STATEMENT = "Helix is to data what logic is to language."
MICROBLOCK_SIZE = 3
KEYFILE = "wallet.txt"
GENESIS_FILE = "genesis.json"


def main() -> None:
    _, priv = load_or_create_keys(KEYFILE)
    event = create_event(STATEMENT, microblock_size=MICROBLOCK_SIZE, private_key=priv)

    for index, block in enumerate(event["microblocks"]):
        seed = mine_seed(block)
        if seed is None:
            raise RuntimeError(f"Failed to mine microblock {index}")
        event["seeds"][index] = seed
        mark_mined(event, index)

    path = Path(GENESIS_FILE)

    data = event.copy()
    data["microblocks"] = [b.hex() for b in event.get("microblocks", [])]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"Saved genesis event to {path}")
    print(f"GENESIS_HASH = {digest}")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
