import json
import threading
import time

from helix.helix_node import HelixNode, GossipMessageType
from helix.gossip import LocalGossipNetwork
from helix import event_manager
import helix.blockchain as blockchain


def main() -> None:
    network = LocalGossipNetwork()
    node = HelixNode(
        events_dir="data/events",
        balances_file="data/balances.json",
        chain_file="data/blockchain.jsonl",
        node_id="CLI",
        network=network,
    )

    msg_thread = threading.Thread(target=node._message_loop, daemon=True)
    msg_thread.start()

    statement = "Test statement via script"
    event = node.create_event(statement)
    evt_id = event["header"]["statement_id"]
    node.events[evt_id] = event
    node.save_state()
    node.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})

    node.mine_event(event)
    time.sleep(0.1)

    node.finalize_event(event)
    time.sleep(0.1)

    print("\nBalances:")
    print(json.dumps(node.balances, indent=2))

    chain = blockchain.load_chain(str(node.chain_file))
    print("\nBlockchain:")
    print(json.dumps(chain, indent=2))


if __name__ == "__main__":
    main()
