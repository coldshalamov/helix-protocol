import json
from helix.gossip import LocalGossipNetwork, GossipNode
from helix.peer_discovery import PeerDiscovery


def test_peer_persistence(tmp_path):
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)

    peers_file = tmp_path / "peers.json"

    pd_a = PeerDiscovery(node_a, host="127.0.0.1", port=1111, peers_file=str(peers_file))
    pd_b = PeerDiscovery(node_b, host="127.0.0.1", port=2222, peers_file=str(peers_file))

    # first handshake A -> B
    pd_a.send_hello()
    pd_b.handle_message(node_b.receive(timeout=1))
    pd_a.handle_message(node_a.receive(timeout=1))

    # second handshake B -> A
    pd_b.send_hello()
    pd_a.handle_message(node_a.receive(timeout=1))
    pd_b.handle_message(node_b.receive(timeout=1))

    assert set(pd_a.known_peers.keys()) == {"A", "B"}
    assert set(pd_b.known_peers.keys()) == {"A", "B"}

    with open(peers_file, "r", encoding="utf-8") as fh:
        saved = json.load(fh)
    assert {p["node_id"] for p in saved} == {"A", "B"}

    node_c = GossipNode("C", network)
    pd_c = PeerDiscovery(node_c, peers_file=str(peers_file))
    assert {"A", "B"} <= set(pd_c.known_peers.keys())
