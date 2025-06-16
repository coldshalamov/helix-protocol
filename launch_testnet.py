import json

from helix import event_manager, merkle_utils, nested_miner, minihelix, betting_interface, signature_utils
import blockchain


def main() -> None:
    # Create a simple event for a test statement
    statement = "Testnet demonstration statement"
    event = event_manager.create_event(statement, microblock_size=2)
    evt_id = event["header"]["statement_id"]
    print(f"Created event {evt_id} with {len(event['microblocks'])} microblocks")

    # Simulate mining by accepting a dummy seed for each microblock
    nested_miner.verify_nested_seed = lambda chain, block, max_steps=1000: True
    for idx, _ in enumerate(event["microblocks"]):
        seed = b"x"
        event_manager.accept_mined_seed(event, idx, [seed])
        print(f"Mined microblock {idx} with mock seed {seed.hex()}")

    # Generate two example bets and record them
    pub_yes, priv_yes = signature_utils.generate_keypair()
    pub_no, priv_no = signature_utils.generate_keypair()
    bet_yes = {
        "event_id": evt_id,
        "choice": "YES",
        "amount": 10,
        "pubkey": pub_yes,
        "signature": signature_utils.sign_data(
            repr({
                "event_id": evt_id,
                "choice": "YES",
                "amount": 10,
                "pubkey": pub_yes,
            }).encode("utf-8"),
            priv_yes,
        ),
    }
    bet_no = {
        "event_id": evt_id,
        "choice": "NO",
        "amount": 5,
        "pubkey": pub_no,
        "signature": signature_utils.sign_data(
            repr({
                "event_id": evt_id,
                "choice": "NO",
                "amount": 5,
                "pubkey": pub_no,
            }).encode("utf-8"),
            priv_no,
        ),
    }
    betting_interface.record_bet(event, bet_yes)
    betting_interface.record_bet(event, bet_no)
    print("Placed mock bets")

    # Finalize the event and append a block
    payouts = event_manager.finalize_event(event, node_id="TESTNODE")
    print("Event finalized. Payouts:")
    print(json.dumps(payouts, indent=2))

    chain = blockchain.load_chain()
    final_block = chain[-1] if chain else None
    if final_block:
        print("Final block data:")
        print(json.dumps(final_block, indent=2))

    # Display Merkle root and proof for first microblock
    root = event["header"]["merkle_root"]
    proof = merkle_utils.generate_merkle_proof(0, event["merkle_tree"])
    valid = merkle_utils.verify_merkle_proof(event["microblocks"][0], proof, root, 0)
    print(f"Merkle root: {root.hex()}")
    print("Proof for block 0:", [p.hex() for p in proof])
    print("Proof valid:", valid)


if __name__ == "__main__":
    main()
