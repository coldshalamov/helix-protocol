#!/usr/bin/env python3
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


if __name__ == "__main__":
    main()
