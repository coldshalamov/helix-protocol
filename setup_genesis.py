```python
from __future__ import annotations

import os

from helix.signature_utils import generate_keypair, save_keys
from helix.ledger import save_balances
from helix.event_manager import create_event, save_event, mark_mined
from helix.minihelix import mine_seed
from helix import exhaustive_miner, miner, minihelix


STATEMENT = "Helix is to data what logic is to language."
MICROBLOCK_SIZE = 3
KEYFILE = "data/genesis_keys.json"
BALANCES_FILE = "data/balances.json"
EVENTS_DIR = "data/events"


def _mine_microblocks(event: dict) -> None:
    """Mine all microblocks for ``event`` using flat, nested, or brute-force mining."""

    FLAT_ATTEMPTS = 5_000_000
    BRUTE_FORCE_ATTEMPTS = 10_000_000

    for idx, block in enumerate(event["microblocks"]):
        print(f"Mining microblock {idx}")

        seed = miner.find_seed(block, attempts=FLAT_ATTEMPTS)
        depth = 1
        if seed is not None and minihelix.verify_seed(seed, block):
            print(f"  Flat mining success: length {len(seed)}")
        else:
            print(f"  Flat mining failed for index {idx}, trying exhaustive...")
            seed = None
            chain = exhaustive_miner.exhaustive_mine(block, max_depth=3)
            if chain is not None:
                depth = len(chain)
                seed = chain[0]
                if minihelix.verify_seed(seed, block):
                    print(
                        f"  Nested mining success: length {len(seed)} depth {depth}"
                    )
            if seed is None:
                print(
                    f"  Nested mining failed for index {idx}, using brute force with {BRUTE_FORCE_ATTEMPTS} attempts..."
                )
                seed = mine_seed(block, max_attempts=BRUTE_FORCE_ATTEMPTS)
                if seed is not None and minihelix.verify_seed(seed, block):
                    print(f"  Brute-force success: length {len(seed)}")
                depth = 1

        if seed is None or not minihelix.verify_seed(seed, block):
            print(f"Failed to mine microblock {idx}")
            raise RuntimeError(f"Failed to mine microblock {idx}")

        event["seeds"][idx] = seed
        event["seed_depths"][idx] = depth
        mark_mined(event, idx)


def _print_summary(event: dict) -> None:
    """Print summary of mined blocks with compression stats."""

    micro_size = event.get("header", {}).get("microblock_size", MICROBLOCK_SIZE)
    block_count = len(event.get("microblocks", []))
    total_saved = 0
    total_original = micro_size * block_count
    total_compressed = 0

    print("Block summary:")
    for idx, seed in enumerate(event.get("seeds", [])):
        if seed is None:
            continue
        depth = event.get("seed_depths", [1] * block_count)[idx] or 1
        length = len(seed)
        saved = max(0, micro_size - length)
        total_saved += saved
        total_compressed += length
        print(
            f"  Block {idx}: seed length {length}, depth {depth}, saved {saved} bytes"
        )

    ratio = (
        (total_original / total_compressed) if total_compressed else 0
    )
    print(f"Total blocks: {block_count}")
    print(f"Estimated compression ratio: {ratio:.2f}x")


def main() -> None:
    os.makedirs(EVENTS_DIR, exist_ok=True)

    pubkey, privkey = generate_keypair()
    save_keys(KEYFILE, pubkey, privkey)

    balances = {pubkey: {"balance": 0, "genesis_tokens": 1000}}
    save_balances(balances, BALANCES_FILE)

    event = create_event(
        STATEMENT,
        microblock_size=MICROBLOCK_SIZE,
        private_key=privkey,
    )
    _mine_microblocks(event)
    path = save_event(event, EVENTS_DIR)
    print(f"Genesis event saved to {path}")

    _print_summary(event)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
```
