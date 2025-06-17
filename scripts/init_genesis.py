#!/usr/bin/env python3
"""Initialize the Helix genesis block with fully mined microblocks."""

from __future__ import annotations

import json
import time
from pathlib import Path
from helix import event_manager, signature_utils, nested_miner


def main() -> None:
    # Load or create wallet
    pub, priv = signature_utils.load_or_create_keys("wallet.json")

    statement = "Helix is to data what logic is to language."
    microblock_size = 3
    signature = signature_utils.sign_statement(statement, priv)

    event = event_manager.create_event(
        statement=statement,
        microblock_size=microblock_size,
        private_key=priv,
    )
    event["originator_pub"] = pub
    event["originator_sig"] = signature

    # Prepare mining
    mined_count = 0
    total_blocks = len(event["microblocks"])
    print(f"Mining {total_blocks} microblocks with max_depth=500, attempts=500000...")

    for idx, block in enumerate(event["microblocks"]):
        start_time = time.time()
        result = nested_miner.find_nested_seed(block, max_depth=500, attempts=500_000)
        elapsed = time.time() - start_time

        if result is None:
            print(f"Microblock {idx}: ❌ no seed found (after {elapsed:.2f}s)")
            continue

        event["seeds"][idx] = result.encoded
        event["seed_depths"][idx] = result.depth
        event_manager.mark_mined(event, idx)

        seed_len = result.encoded[1]
        ratio = microblock_size / seed_len if seed_len else 0
        print(
            f"Microblock {idx}: ✅ depth={result.depth}, compression={ratio:.2f}x, time={elapsed:.2f}s"
        )
        mined_count += 1

    if mined_count != total_blocks:
        raise RuntimeError(
            f"Only {mined_count}/{total_blocks} microblocks were successfully mined."
        )

    # Save and finalize
    events_dir = Path("data/events")
    events_dir.mkdir(parents=True, exist_ok=True)
    event_manager.save_event(event, str(events_dir))

    payouts = event_manager.finalize_event(
        event=event,
        node_id="GENESIS_NODE",
        chain_file="chain.json",
        balances_file="balances.json",
    )

    # Final print
    print("✅ Finalized Genesis block")
    print("Statement:", statement)
    print("Payouts:", json.dumps(payouts, indent=2))


if __name__ == "__main__":
    main()
