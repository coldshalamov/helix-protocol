#!/usr/bin/env python3
"""Initialize the Helix genesis block with fully mined microblocks."""

from __future__ import annotations

import json
import time
from pathlib import Path
from helix import (
    event_manager,
    signature_utils,
    exhaustive_miner,
)

CHECKPOINT_FILE = Path("start_index.txt")

def main() -> None:
    # 1. Load or create wallet
    pub, priv = signature_utils.load_or_create_keys("wallet.json")

    # 2. Define genesis statement
    statement = "Helix is to data what logic is to language."
    microblock_size = 3
    signature = signature_utils.sign_statement(statement, priv)

    # 3. Prepare event directory
    events_dir = Path("data/events")
    events_dir.mkdir(parents=True, exist_ok=True)
    statement_id = event_manager.sha256(statement.encode("utf-8"))
    event_path = events_dir / f"{statement_id}.json"

    # 4. Create or load event
    if event_path.exists():
        event = event_manager.load_event(str(event_path))
    else:
        event = event_manager.create_event(
            statement=statement,
            microblock_size=microblock_size,
            private_key=priv,
        )
        event["originator_pub"] = pub
        event["originator_sig"] = signature
        event_manager.save_event(event, str(events_dir))

    # 5. Read checkpoint index
    start_index = 0
    if CHECKPOINT_FILE.exists():
        try:
            start_index = int(CHECKPOINT_FILE.read_text())
        except Exception:
            start_index = 0

    # 6. Mine each microblock
    total_blocks = len(event["microblocks"])
    mined_count = 0

    print(f"Mining {total_blocks} microblocks with max_depth=500, using start_index={start_index}...")

    for idx, block in enumerate(event["microblocks"]):
        if event["seeds"][idx] is not None:
            continue

        start_time = time.time()
        chain = exhaustive_miner.exhaustive_mine(
            block,
            max_depth=500,
            start_index=start_index,
            checkpoint_path=str(CHECKPOINT_FILE),
        )
        elapsed = time.time() - start_time

        if chain is None:
            print(f"Microblock {idx}: ❌ no seed found (after {elapsed:.2f}s)")
            continue

        seed_len = len(chain[0]) if chain else 0
        ratio = microblock_size / seed_len if seed_len else 0
        print(f"Microblock {idx}: ✅ depth={len(chain)}, compression={ratio:.2f}x, time={elapsed:.2f}s")

        event_manager.accept_mined_seed(event, idx, chain)
        event_manager.save_event(event, str(events_dir))
        mined_count += 1

        try:
            start_index = int(CHECKPOINT_FILE.read_text())
        except Exception:
            start_index = 0

    if mined_count != total_blocks:
        raise RuntimeError(
            f"Only {mined_count}/{total_blocks} microblocks were successfully mined."
        )

    # 7. Finalize the event and add to chain
    payouts = event_manager.finalize_event(
        event=event,
        node_id="GENESIS_NODE",
        chain_file="chain.json",
        balances_file="balances.json",
    )

    # 8. Load finalized block hash
    block_hash = None
    chain_file = Path("chain.json")
    if chain_file.exists():
        try:
            with open(chain_file, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
                if lines:
                    block = json.loads(lines[-1])
                    block_hash = block.get("block_id")
        except Exception:
            pass

    print("✅ Finalized Genesis block")
    print("Block hash:", block_hash)
    print("Statement:", statement)
    print("Payouts:", json.dumps(payouts, indent=2))

if __name__ == "__main__":
    main()
