import threading
import time
import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode, GossipMessageType, simulate_mining, find_seed, verify_seed
from helix.gossip import LocalGossipNetwork
from helix import event_manager


def test_single_node_microblock(tmp_path, monkeypatch, capsys):
    network = LocalGossipNetwork()
    events_dir = tmp_path / "test_events"
    node = HelixNode(
        events_dir=str(events_dir),
        balances_file=str(tmp_path / "balances.json"),
        node_id="A",
        network=network,
        microblock_size=3,
    )

    # accelerate mining
    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda target, attempts=10000: b"x")
    monkeypatch.setattr("helix.helix_node.verify_seed", lambda s, t: True)

    t = threading.Thread(target=node._message_loop, daemon=True)
    t.start()

    statement = "abc"
    event = node.create_event(statement)
    evt_id = event["header"]["statement_id"]
    node.events[evt_id] = event
    node.save_state()

    send_event = event.copy()
    send_event["microblocks"] = [b.hex() for b in send_event["microblocks"]]
    node.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": send_event})
    node.mine_event(event)
    time.sleep(0.1)

    assert event["is_closed"]
    reassembled = event_manager.reassemble_microblocks(event["microblocks"])
    assert reassembled == statement

    print("SUCCESS")
