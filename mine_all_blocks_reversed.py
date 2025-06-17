#!/usr/bin/env python3
"""Parallel miner that searches for seeds matching all known microblocks.

This script loads unmined events from disk and continuously generates random
nested seed chains. Each generated microblock is hashed and compared against
all pending microblocks. When a match is found the corresponding event file is
updated unless ``--dry-run`` is specified.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from helix import event_manager, minihelix, nested_miner

# Shared structures
hash_lock = threading.Lock()
target_hashes: set[bytes] = set()
hash_to_info: dict[bytes, tuple[str, int, int]] = {}
stop_event = threading.Event()


def load_targets(events_dir: Path) -> None:
    """Load all unmined microblock hashes from ``events_dir``."""
    hashes: set[bytes] = set()
    info: dict[bytes, tuple[str, int, int]] = {}
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            try:
                event = event_manager.load_event(str(path))
            except Exception as exc:  # pragma: no cover - unexpected file error
                print(f"Failed to load {path}: {exc}")
                continue
            block_size = event.get("header", {}).get(
                "microblock_size", minihelix.DEFAULT_MICROBLOCK_SIZE
            )
            for idx, block in enumerate(event.get("microblocks", [])):
                seeds = event.get("seeds", [None] * len(event.get("microblocks", [])))
                if seeds[idx] is not None:
                    continue
                digest = hashlib.sha256(block).digest()
                hashes.add(digest)
                info[digest] = (str(path), idx, block_size)
    with hash_lock:
        target_hashes.clear()
        target_hashes.update(hashes)
        hash_to_info.clear()
        hash_to_info.update(info)


def refresh_loop(events_dir: Path, interval: int = 10) -> None:
    """Background thread periodically refreshing targets."""
    while not stop_event.is_set():
        load_targets(events_dir)
        time.sleep(interval)


def mine_worker(max_depth: int, dry_run: bool) -> None:
    """Worker thread generating random nested seed chains."""
    rng = random.Random(os.urandom(16))
    while not stop_event.is_set():
        with hash_lock:
            if not target_hashes:
                time.sleep(0.5)
                continue
            sizes = list({info[2] for info in hash_to_info.values()})
        block_size = rng.choice(sizes)
        seed_len = rng.choice([1, 2])
        depth = rng.randint(1, max_depth)
        base_seed = os.urandom(seed_len)

        chain: list[bytes] = [base_seed]
        current = base_seed
        for _ in range(1, depth):
            current = minihelix.G(current, block_size)
            chain.append(current)

        encoded = bytes([len(chain), len(base_seed)]) + b"".join(chain)
        out = nested_miner.unpack_seed_chain(encoded, block_size=block_size)
        digest = hashlib.sha256(out).digest()

        with hash_lock:
            if digest not in target_hashes:
                continue
            path, index, _ = hash_to_info[digest]
        ratio = len(out) / len(base_seed) if len(base_seed) else 0.0
        print(
            f"Match event={Path(path).name} index={index} depth={len(chain)} ratio={ratio:.2f} seed={encoded.hex()}"
        )
        if dry_run:
            continue
        try:
            event = event_manager.load_event(path)
            event_manager.accept_mined_seed(event, index, encoded)
            event_manager.save_event(event, str(Path(path).parent))
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            print(f"Failed to record mined seed: {exc}")
        load_targets(Path(path).parent)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mine all Helix microblocks using reverse search",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir", default=".", help="Directory containing the events folder"
    )
    parser.add_argument(
        "--threads", type=int, default=8, help="Number of worker threads"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not write any files"
    )
    args = parser.parse_args()

    events_dir = Path(args.data_dir) / "events"
    load_targets(events_dir)

    refresher = threading.Thread(target=refresh_loop, args=(events_dir,), daemon=True)
    refresher.start()

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = [executor.submit(mine_worker, 500, args.dry_run) for _ in range(args.threads)]
        try:
            for fut in futures:
                fut.result()
        except KeyboardInterrupt:  # pragma: no cover - manual interruption
            stop_event.set()
            print("Stopping miners...")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
