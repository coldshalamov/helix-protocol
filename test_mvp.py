import json
import os
import sys
from pathlib import Path

# Ensure repository root on path
sys.path.append(str(Path(__file__).resolve().parent))

from helix import event_manager, minihelix, betting_interface, helix_node
from helix.wallet import load_wallet, generate_wallet


def main() -> None:
    wallet_file = Path("wallet.json")
    if wallet_file.exists():
        pub, priv = load_wallet(wallet_file)
        print("Loaded existing wallet")
    else:
        pub, priv = generate_wallet(wallet_file)
        print("Generated new wallet")

    chain_file = "helix_chain.json"
    if not os.path.exists(chain_file):
        with open(chain_file, "w", encoding="utf-8") as fh:
            json.dump([], fh)

    statement = "Helix is to blockchain what logic is to language"
    event = event_manager.create_event(
        statement,
        microblock_size=3,
        private_key=priv,
    )
    event_manager.save_event(event, "data/events")

    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block)
        if seed is not None:
            event_manager.accept_mined_seed(event, idx, [seed])
    event_manager.save_event(event, "data/events")

    bet = betting_interface.submit_bet(
        event["header"]["statement_id"], "YES", 1, str(wallet_file)
    )
    betting_interface.record_bet(event, bet)

    node = helix_node.HelixNode(
        events_dir="data/events",
        balances_file="data/balances.json",
        chain_file=chain_file,
        node_id=pub,
        network=helix_node.LocalGossipNetwork(),
        microblock_size=3,
    )
    node.events[event["header"]["statement_id"]] = event
    node.finalize_event(event)

    balances = node.balances
    print("Wallet balance:", balances.get(pub, 0.0))


if __name__ == "__main__":
    main()
