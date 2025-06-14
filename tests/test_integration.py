import json
import threading
import time
import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode, GossipMessageType, simulate_mining, find_seed, verify_seed
from helix.gossip import LocalGossipNetwork


def test_full_lifecycle(tmp_path, monkeypatch):
    network = LocalGossipNetwork()
    node_a = HelixNode(events_dir=str(tmp_path / "a_events"), balances_file=str(tmp_path / "a_bal.json"), node_id="A", network=network, microblock_size=2)
    node_b = HelixNode(events_dir=str(tmp_path / "b_events"), balances_file=str(tmp_path / "b_bal.json"), node_id="B", network=network, microblock_size=2)

    # speed up mining
    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda target, attempts=10000: b"x")
    monkeypatch.setattr("helix.helix_node.verify_seed", lambda s, t: True)

    t_a = threading.Thread(target=node_a._message_loop, daemon=True)
    t_b = threading.Thread(target=node_b._message_loop, daemon=True)
    t_a.start()
    t_b.start()

    statement = "Integration test"
    event = node_a.create_event(statement)
    evt_id = event["header"]["statement_id"]
    node_a.events[evt_id] = event
    node_a.save_state()
    node_a.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})
    node_a.mine_event(event)
    time.sleep(0.1)

    assert evt_id in node_b.events

    yes_bet = {"event_id": evt_id, "choice": "YES", "amount": 10, "pubkey": "user1"}
    no_bet = {"event_id": evt_id, "choice": "NO", "amount": 5, "pubkey": "user2"}
    node_a.events[evt_id]["bets"]["YES"].append(yes_bet)
    node_b.events[evt_id]["bets"]["YES"].append(yes_bet)
    node_a.events[evt_id]["bets"]["NO"].append(no_bet)
    node_b.events[evt_id]["bets"]["NO"].append(no_bet)

    node_a.finalize_event(event)
    time.sleep(0.1)

    assert node_a.balances == node_b.balances

    with open(node_a.balances_file, "r", encoding="utf-8") as fa:
        bal_a = json.load(fa)
    with open(node_b.balances_file, "r", encoding="utf-8") as fb:
        bal_b = json.load(fb)

    assert bal_a == bal_b
    assert yes_bet["pubkey"] in bal_a

