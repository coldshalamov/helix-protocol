```python
#!/usr/bin/env python3
"""Initialize the Helix genesis block with fully mined microblocks."""

from __future__ import annotations

import json
from pathlib import Path
from helix import (
    event_manager,
    signature_utils,
    exhaustive_miner,
)

CHECKPOINT_FILE = Path("start_index.txt")


def main() -> None:
    # 1. Load or create Ed25519 wallet keys
    pub, priv = signature_utils.load_or_create_keys("wallet.json")

    # 2. The genesis statement
    statement = "Helix is to data what logic is to language."

    # 3. Set microblock size
    microblock_size = 3

    # 4. Sign the statement
    signature = signature_utils.sign_statement(statement, priv)

    # 5. Prepare event file
    events_dir = Path("data/events")
    events_dir.mkdir(parents=True, exist_ok=True)
    statement_id = event_manager.sha256(statement.encode("utf-8"))
    event_path = events_dir / f"{statement_id}.json"

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

    # 6. Read checkpoint index
    start_index = 0
    if CHECKPOINT_FILE.exists():
        try:
            start_index = int(CHECKPOINT_FILE.read_text())
        except Exception:
            start_index = 0

    # 7. Mine each microblock
    for idx, block in enumerate(event["microblocks"]):
        if event["seeds"][idx] is not None:
            continue

        chain = exhaustive_miner.exhaustive_mine(
            block,
            max_depth=500,
            start_index=start_index,
            checkpoint_path=str(CHECKPOINT_FILE),
        )
        if chain is None:
            print(f"Microblock {idx}: no seed found")
            continue

        # Accept the mined chain into the event using built-in function
        event_manager.accept_mined_seed(event, idx, chain)
        event_manager.save_event(event, str(events_dir))

        try:
            start_index = int(CHECKPOINT_FILE.read_text())
        except Exception:
            start_index = 0

        seed_len = len(chain[0]) if chain else 0
        ratio = microblock_size / seed_len if seed_len else 0
        print(f"Microblock {idx}: depth={len(chain)}, compression={ratio:.2f}x")

    # 8. Final save
    event_manager.save_event(event, str(events_dir))

    # 9. Finalize the event and update chain
    payouts = event_manager.finalize_event(
        event=event,
        node_id="GENESIS_NODE",
        chain_file="chain.json",
        balances_file="balances.json",
    )

    # 10. Report results
    chain_file = Path("chain.json")
    block_hash = None
    if chain_file.exists():
        try:
            with open(chain_file, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
                if lines:
                    block = json.loads(lines[-1])
                    block_hash = block.get("block_id")
        except Exception:
            pass

    print("Finalized block hash:", block_hash)
    print("Statement:", statement)
    print("Payout distribution:")
    print(json.dumps(payouts, indent=2))


if __name__ == "__main__":
    main()
```
