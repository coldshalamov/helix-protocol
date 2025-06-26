from helix import event_manager, minihelix, betting_interface, helix_node
from helix.signature_utils import load_private_key
from helix.ledger import load_balances
from wallet import load_wallet, generate_wallet
from helix.gossip import LocalGossipNetwork


def main() -> None:
    wallet_file = "wallet.json"
    try:
        pub, _ = load_wallet(wallet_file)
        print("Loaded existing wallet")
    except FileNotFoundError:
        pub, _ = generate_wallet(wallet_file)
        print("Generated new wallet")

    priv = load_private_key(wallet_file)

    print("Submitting statement...")
    event = event_manager.create_event(
        "MVP test statement",
        microblock_size=3,
        private_key=priv,
    )
    event_manager.save_event(event, "data/events")

    print("Mining microblocks...")
    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block)
        if seed is not None:
            event_manager.accept_mined_seed(event, idx, [seed])
    event_manager.save_event(event, "data/events")

    print("Placing YES bet...")
    bet = betting_interface.submit_bet(
        event["header"]["statement_id"], "YES", 1, wallet_file
    )
    betting_interface.record_bet(event, bet)

    print("Finalizing event...")
    network = LocalGossipNetwork()
    node = helix_node.HelixNode(
        events_dir="data/events",
        balances_file="data/balances.json",
        chain_file="data/blockchain.jsonl",
        node_id=pub,
        network=network,
        microblock_size=3,
    )
    node.events[event["header"]["statement_id"]] = event
    node.finalize_event(event)

    balances = load_balances("data/balances.json")
    print("Wallet balance:", balances.get(pub, 0.0))


if __name__ == "__main__":
    main()
