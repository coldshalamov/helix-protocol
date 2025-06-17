#!/usr/bin/env python3
<<<<<<< codex/create-python-script-for-event-generation
"""Initialize and mine the Helix genesis event using nested mining."""

from __future__ import annotations

from helix import event_manager, nested_miner, signature_utils

STATEMENT = "Helix is to data what logic is to language."
MICROBLOCK_SIZE = 3


def main() -> None:
    pub, priv = signature_utils.generate_keypair()

    # Sign the genesis statement for demonstration purposes
    signature = signature_utils.sign_data(STATEMENT.encode("utf-8"), priv)
    print(f"Generated signature: {signature}")

    event = event_manager.create_event(
        STATEMENT,
        microblock_size=MICROBLOCK_SIZE,
        private_key=priv,
    )

    for idx, block in enumerate(event["microblocks"]):
        result = nested_miner.find_nested_seed(block, max_depth=500)
        if result is None:
            print(f"Microblock {idx}: no seed found")
            continue

        event["seeds"][idx] = result.encoded
        event["seed_depths"][idx] = result.depth
        event_manager.mark_mined(event, idx)

        seed_len = result.encoded[1]
        ratio = MICROBLOCK_SIZE / seed_len if seed_len else 0
        print(
            f"Microblock {idx}: depth {result.depth}, compression ratio {ratio:.2f}x"
        )

    try:
        payouts = event_manager.finalize_event(event)
        print("Payouts:", payouts)
    except Exception as exc:  # pragma: no cover - runtime failure
        print(f"Failed to finalize event: {exc}")
        return

    root = event["header"].get("merkle_root")
    statement = event_manager.reassemble_microblocks(event["microblocks"])
    print(f"Merkle root: {root}")
    print(f"Reassembled statement: {statement}")
=======
"""Initialize the Helix genesis block with uncompressed seeds."""

from __future__ import annotations

import json
from pathlib import Path

from helix import event_manager, signature_utils


def main() -> None:
    # 1. Load or create Ed25519 wallet keys
    pub, priv = signature_utils.load_or_create_keys("wallet.json")

    # 2. The genesis statement
    statement = "Helix is to data what logic is to language."

    # 3. Set microblock size
    microblock_size = 3

    # 4. Sign the statement
    signature = signature_utils.sign_statement(statement, priv)

    # 5. Create the event (signature stored separately)
    event = event_manager.create_event(
        statement=statement,
        microblock_size=microblock_size,
        private_key=priv,
    )
    # Override with explicit signature and pubkey
    event["originator_pub"] = pub
    event["originator_sig"] = signature

    # 6. Prepare events directory
    events_dir = Path("data/events")
    events_dir.mkdir(parents=True, exist_ok=True)

    # 7. Treat microblocks as mined seeds
    event_manager.mint_uncompressed_seeds(event)

    # Save the event to disk
    event_manager.save_event(event, str(events_dir))

    # 8. Finalize the event
    payouts = event_manager.finalize_event(
        event=event,
        node_id="GENESIS_NODE",
        chain_file="chain.json",
        balances_file="balances.json",
    )

    # Load block hash from chain file
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

    # 9. Print results
    print("Finalized block hash:", block_hash)
    print("Statement:", statement)
    print("Payout distribution:")
    print(json.dumps(payouts, indent=2))
>>>>>>> main


if __name__ == "__main__":
    main()
