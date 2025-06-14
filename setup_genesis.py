from __future__ import annotations

import os

from helix.signature_utils import generate_keypair, save_keys
from helix.ledger import save_balances
from helix.event_manager import create_event, save_event, mark_mined
from helix.minihelix import mine_seed
from helix import nested_miner, miner, minihelix


STATEMENT = "Helix is to data what logic is to language."
MICROBLOCK_SIZE = 3
KEYFILE = "data/genesis_keys.json"
BALANCES_FILE = "data/balances.json"
EVENTS_DIR = "data/events"


def _mine_microblocks(event: dict) -> None:
    """Mine all microblocks for ``event`` using flat or nested seeds."""
    for idx, block in enumerate(event["microblocks"]):
        # Try flat mining first
        seed = miner.find_seed(block)
        if seed is None or not minihelix.verify_seed(seed, block):
            result = nested_miner.find_nested_seed(block)
            if result is not None:
                chain, _ = result
                seed = chain[0]
        if seed is None:
            seed = mine_seed(block)
        if seed is None:
            raise RuntimeError(f"Failed to mine microblock {idx}")
        event["seeds"][idx] = seed
        mark_mined(event, idx)


def main() -> None:
    os.makedirs(EVENTS_DIR, exist_ok=True)

    pubkey, privkey = generate_keypair()
    save_keys(KEYFILE, pubkey, privkey)

    balances = {pubkey: {"balance": 0, "genesis_tokens": 1000}}
    save_balances(balances, BALANCES_FILE)

    event = create_event(
        STATEMENT,
        microblock_size=MICROBLOCK_SIZE,
        keyfile=KEYFILE,
    )
    _mine_microblocks(event)
    path = save_event(event, EVENTS_DIR)
    print(f"Genesis event saved to {path}")


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()

