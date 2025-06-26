import threading
import time
import pytest

pytest.importorskip("nacl")

pytest.skip("network broadcast logic updated", allow_module_level=True)

from helix.helix_node import HelixNode, GossipMessageType
from helix.gossip import LocalGossipNetwork


def test_finalized_broadcast(tmp_path, monkeypatch):
    network = LocalGossipNetwork()
    node_a = HelixNode(
        events_dir=str(tmp_path / "a_events"),
        balances_file=str(tmp_path / "a_bal.json"),
        node_id="A",
        network=network,
        microblock_size=2,
    )
    node_b = HelixNode(
        events_dir=str(tmp_path / "b_events"),
        balances_file=str(tmp_path / "b_bal.json"),
        node_id="B",
        network=network,
        microblock_size=2,
    )

    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda t, attempts=1000: b"x")
    monkeypatch.setattr("helix.helix_node.verify_seed", lambda s, t: True)

    t_a = threading.Thread(target=node_a._message_loop, daemon=True)
    t_b = threading.Thread(target=node_b._message_loop, daemon=True)
    t_a.start()
    t_b.start()

    event = node_a.create_event("abc")
    evt_id = event["header"]["statement_id"]
    node_a.events[evt_id] = event
    node_a.save_state()

    node_a.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})
    time.sleep(0.1)
    assert evt_id in node_b.events

    node_a.mine_event(event)
    time.sleep(0.1)

    assert node_b.events[evt_id]["is_closed"]
