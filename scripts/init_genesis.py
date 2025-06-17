#!/usr/bin/env python3
"""Initialize the Helix genesis block with fully mined microblocks."""

from __future__ import annotations

import json
from pathlib import Path
from helix import event_manager, signature_utils, nested_miner


def main() -> None:
    # 1. Load or create Ed25519 wallet keys
    pub, priv = signature_utils.load_or_create_keys("wallet.json")

    # 2. The genesis statement
    statement = "Helix is to data what logic is to language."

    # 3. Set microblock size
    microblock_size = 3

    # 4. Sign the statement
    signature = signature_utils.sign_statement(statement, priv)

    # 5. Create the event
    event = event_manager.create_event(
        statement=statement,
        microblock_size=microblock_size,
        private_key=priv,
    )
    event["originator_pub"] = pub
    event["originator_sig"] = signature

    # 6. Mine each microblock
    for idx, block in enumerate(event["microblocks"]):
        result = nested_miner.find_nested_seed(block, max_depth=500)
        if result is None:
            print(f"Microblock {idx}: no seed found")
            continue

        event["seeds"][idx] = result.encoded
        event["seed_depths"][idx] = result.depth
        event_manager.mark_mined(event, idx)

        seed_len = result.encoded[1]
        ratio = microblock_size / seed_len if seed_len else 0
        print(
            f"Microblock {idx}: depth={result.depth}, compression={ratio:.2f}x"
        )

        # verify the mined result by reassembling the chain
        chain = nested_miner.decode_chain(result.encoded, len(block))
        current = chain[0]
        for step in chain[1:]:
            current = nested_miner.G(current, len(block))
        current = nested_miner.G(current, len(block))
        if current != block:
            print(f"WARNING: verification failed for microblock {idx}")

    # 7. Save event to disk
    events_dir = Path("data/events")
    events_dir.mkdir(parents=True, exist_ok=True)
    event_manager.save_event(event, str(events_dir))

    # 8. Finalize the event
    payouts = event_manager.finalize_event(
        event=event,
        node_id="GENESIS_NODE",
        chain_file="chain.json",
        balances_file="balances.json",
    )

    # 9. Report results
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
