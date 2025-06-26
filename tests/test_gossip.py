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
    node_a.send_message({"type": "SEED", "payload": "123"})
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


def test_no_duplicate_broadcast():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)

    msg = {"type": "STATEMENT", "event_id": "x", "index": 1}
    node_a.send_message(msg)
    node_a.send_message(msg)

    received = node_b.receive(timeout=1)
    with pytest.raises(queue.Empty):
        node_b.receive(timeout=0.1)
    assert received["type"] == "STATEMENT"


def test_receive_deduplicates():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)

    msg = {"type": "STATEMENT", "event_id": "y", "index": 2}
    network.send("A", msg)
    network.send("A", msg)

    received = node_b.receive(timeout=1)
    with pytest.raises(queue.Empty):
        node_b.receive(timeout=0.1)
    assert received["type"] == "STATEMENT"


def test_network_filters_duplicate():
    network = LocalGossipNetwork()
    node_a = GossipNode("A", network)
    node_b = GossipNode("B", network)

    msg = {"type": "STATEMENT", "event_id": "z", "index": 3}
    network.send("A", msg)
    network.send("A", msg)

    assert node_b._queue.qsize() == 1
    received = node_b.receive(timeout=1)
    with pytest.raises(queue.Empty):
        node_b.receive(timeout=0.1)
    assert received["type"] == "STATEMENT"
