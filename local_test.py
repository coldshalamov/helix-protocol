from helix.helix_node import HelixNode
from helix.gossip import LocalGossipNetwork
from helix import event_manager
from helix.minihelix import mine_seed, verify_seed
from helix.wallet import Wallet


def main() -> None:
    # Initialize node on a local gossip network
    network = LocalGossipNetwork()
    node = HelixNode(network=network, node_id="LOCAL")

    # Create a simple test statement and associated event
    statement = "Local test statement"
    event = event_manager.create_event(statement, node.microblock_size)
    evt_id = event["header"]["statement_id"]
    node.events[evt_id] = event

    print(f"Created event {evt_id} with {len(event['microblocks'])} blocks")

    # Mine each microblock using the MiniHelix miner
    for idx, block in enumerate(event["microblocks"]):
        seed = mine_seed(block, max_attempts=100000)
        if seed is None:
            raise RuntimeError(f"Failed to mine block {idx}")
        assert verify_seed(seed, block)
        event["seeds"][idx] = seed
        event_manager.mark_mined(event, idx)
        print(f"Mined microblock {idx} with seed {seed.hex()}")

    # Demo wallet places a YES bet
    wallet = Wallet(balance=100)
    bet_amount = 10
    wallet.withdraw(bet_amount)
    event["bets"]["YES"].append({
        "event_id": evt_id,
        "choice": "YES",
        "amount": bet_amount,
        "pubkey": "demo",
    })

    # Resolve bets and update wallet balance (YES wins by default)
    pot = bet_amount
    wallet.deposit(pot)
    node.balances["demo"] = wallet.balance

    final = event_manager.reassemble_microblocks(event["microblocks"])
    print("Final statement:", final)
    print("Balances:", node.balances)


if __name__ == "__main__":
    main()
