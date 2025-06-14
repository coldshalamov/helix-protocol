import queue
import pytest

from helix.gossip import LocalGossipNetwork, GossipNode


def test_message_broadcast():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)
    node_a.send_message({"type": "STATEMENT", "payload": "hello"})
    msg = node_b.receive(timeout=1)
    assert msg == {"type": "STATEMENT", "payload": "hello"}


def test_sender_does_not_receive_own_message():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)
    node_a.send_message({"type": "SEED", "payload": b"123"})
    with pytest.raises(queue.Empty):
        node_a.receive(timeout=0.1)
    msg = node_b.receive(timeout=1)
    assert msg["type"] == "SEED"


def test_presence_ping_pong():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)

    node_a.broadcast_presence()
    ping = node_b.receive(timeout=1)
    assert ping["type"] == GossipNode.PRESENCE_PING
    assert node_b.known_peers == {"A"}

    pong = node_a.receive(timeout=1)
    assert pong["type"] == GossipNode.PRESENCE_PONG
    assert node_a.known_peers == {"B"}
