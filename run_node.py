from helix.helix_node import HelixNode
from helix.gossip import LocalGossipNetwork
import threading


def main() -> None:
    print("Starting Helix node...")
    network = LocalGossipNetwork()
    node = HelixNode(network=network, node_id="LIVE")

    # launch background gossip listener
    gossip_thread = threading.Thread(target=node._message_loop, daemon=True)
    gossip_thread.start()
    print("Gossip thread started")

    # begin sync/mining loop
    node.start_sync_loop()

    # keep process alive
    gossip_thread.join()


if __name__ == "__main__":
    main()
