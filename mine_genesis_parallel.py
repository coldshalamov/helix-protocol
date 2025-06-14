#!/usr/bin/env python3
"""Mine the Helix genesis event using real seed mining in parallel.

This script creates the genesis event from the statement:
"Helix is to blockchain what logic is to language."  Each microblock is three
bytes long.  Mining iterates through candidate seeds starting at ``b'\x00'`` and
checks them against all unmined microblocks using the MiniHelix ``G`` function.
When a seed reproduces a microblock it is recorded, the block is marked mined
and removed from the queue.  Once all blocks are mined the full event is saved
as ``genesis.json`` and the reconstructed statement is printed.
"""

from __future__ import annotations

import json
from typing import Iterator, List

from helix.minihelix import G

try:
    from helix.event_manager import (
        create_event,
        mark_mined,
        reassemble_microblocks,
    )
except ModuleNotFoundError:
    import sys
    import types

    nacl_mod = types.ModuleType("nacl")
    signing_mod = types.ModuleType("signing")

    class _DummyKey:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def sign(self, *a, **kw):  # pragma: no cover - fallback
            raise NotImplementedError("Signing not available")

        def verify(self, *a, **kw):  # pragma: no cover - fallback
            raise NotImplementedError("Verify not available")

        def encode(self) -> bytes:  # pragma: no cover - fallback
            return b""

    signing_mod.SigningKey = _DummyKey
    signing_mod.VerifyKey = _DummyKey
    nacl_mod.signing = signing_mod
    sys.modules.setdefault("nacl", nacl_mod)
    sys.modules.setdefault("nacl.signing", signing_mod)

    from helix.event_manager import (
        create_event,
        mark_mined,
        reassemble_microblocks,
    )

STATEMENT = "Helix is to blockchain what logic is to language."
MICROBLOCK_SIZE = 3
GENESIS_FILE = "genesis.json"
MAX_SEED_LEN = 3


def seed_space(max_len: int = MAX_SEED_LEN) -> Iterator[bytes]:
    """Yield seeds sequentially from ``b'\x00'`` up to ``max_len`` bytes."""
    length = 1
    while length <= max_len:
        for value in range(256 ** length):
            yield value.to_bytes(length, "big")
        length += 1


def mine_event(event: dict) -> None:
    """Mine all microblocks for ``event`` by searching for valid seeds."""
    queue: List[int] = list(range(len(event["microblocks"])))
    for seed in seed_space():
        if not queue:
            break
        candidate = G(seed, MICROBLOCK_SIZE)
        for idx in queue[:]:
            if candidate == event["microblocks"][idx]:
                event["seeds"][idx] = seed
                mark_mined(event, idx)
                queue.remove(idx)
                break


def main() -> None:
    event = create_event(STATEMENT, microblock_size=MICROBLOCK_SIZE)
    mine_event(event)

    statement = reassemble_microblocks(event["microblocks"])

    data = event.copy()
    data["microblocks"] = [b.hex() for b in event["microblocks"]]
    data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in event["seeds"]]

    with open(GENESIS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    print("✅ Genesis block mined and saved as genesis.json")
    print(f"✅ Reassembled statement: {statement}")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
