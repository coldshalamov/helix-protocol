#!/usr/bin/env python3
"""Mine the Helix genesis event using parallel flat or nested mining.

This script recreates the genesis event from the statement
"Helix is to data what logic is to language."  Each microblock is three bytes
long.  Mining now uses :func:`helix.miner.find_seed` which is capable of flat or
nested searches.  Multiple worker processes are spawned for every microblock and
the first successful seed halts all workers.  Mined seeds are written back to
``genesis.json`` and the final statement along with ``GENESIS_HASH`` is printed.
"""

from __future__ import annotations

import json
import hashlib
import logging
import multiprocessing as mp
import time
from pathlib import Path
from typing import Tuple, Optional

from helix.miner import find_seed

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

STATEMENT = "Helix is to data what logic is to language."
MICROBLOCK_SIZE = 3
GENESIS_FILE = "genesis.json"

DEFAULT_MAX_DEPTH = 4
DEFAULT_MAX_SEED_LEN = 32
DEFAULT_ATTEMPTS = 10_000_000


def _worker(
    block: bytes,
    queue: mp.Queue,
    max_depth: int,
    max_seed_len: int,
    attempts: int,
) -> None:
    """Worker process that searches for a seed for ``block``."""
    result = find_seed(
        block,
        max_depth=max_depth,
        max_seed_len=max_seed_len,
        attempts=attempts,
    )
    if result is not None:
        queue.put(result)


def mine_event(
    event: dict,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_seed_len: int = DEFAULT_MAX_SEED_LEN,
    max_attempts: int = DEFAULT_ATTEMPTS,
) -> None:
    """Mine all microblocks for ``event`` using parallel workers."""

    cpu_count = mp.cpu_count()
    for idx, block in enumerate(event["microblocks"]):
        if event["seeds"][idx] is not None:
            continue

        logging.info("Mining microblock %d", idx)
        result_q: mp.Queue[Tuple[bytes, int]] = mp.Queue()
        procs = [
            mp.Process(
                target=_worker,
                args=(block, result_q, max_depth, max_seed_len, max_attempts),
            )
            for _ in range(cpu_count)
        ]
        for p in procs:
            p.start()

        seed: Optional[bytes] = None
        depth: int = 0

        while any(p.is_alive() for p in procs):
            try:
                seed, depth = result_q.get_nowait()
                break
            except Exception:
                time.sleep(0.05)

        for p in procs:
            if p.is_alive():
                p.terminate()
            p.join()

        if seed is not None:
            logging.info(
                "  Found seed at depth %d: %s", depth, seed.hex()
            )
            event["seeds"][idx] = seed
            event["seed_depths"][idx] = depth
            mark_mined(event, idx)
        else:
            logging.warning(
                "  No seed found for microblock %d after %d attempts per worker",
                idx,
                max_attempts,
            )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    event = create_event(STATEMENT, microblock_size=MICROBLOCK_SIZE)
    mine_event(
        event,
        max_depth=DEFAULT_MAX_DEPTH,
        max_seed_len=DEFAULT_MAX_SEED_LEN,
        max_attempts=DEFAULT_ATTEMPTS,
    )

    statement = reassemble_microblocks(event["microblocks"])

    data = event.copy()
    data["microblocks"] = [b.hex() for b in event["microblocks"]]
    data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in event["seeds"]]
    data["seed_depths"] = event.get("seed_depths", [])

    with open(GENESIS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

    digest = hashlib.sha256(Path(GENESIS_FILE).read_bytes()).hexdigest()
    print("✅ Genesis block mined and saved as genesis.json")
    print(f"✅ Reassembled statement: {statement}")
    print(f"GENESIS_HASH = {digest}")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
