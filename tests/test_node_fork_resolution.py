import threading
import time
import types
import sys
import pytest

pytest.importorskip("nacl")

from helix.helix_node import HelixNode, GossipMessageType
from helix.gossip import LocalGossipNetwork
import helix.event_manager as em
import blockchain as bc
import helix.blockchain as hbc


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    stub = types.ModuleType("helix.nested_miner")
    stub.verify_nested_seed = lambda c, b: True
    sys.modules["helix.nested_miner"] = stub
    monkeypatch.setattr(em, "nested_miner", stub)


def test_node_resolve_fork(tmp_path, monkeypatch):
    network = LocalGossipNetwork()
    chain_a = tmp_path / "a.jsonl"
    chain_b = tmp_path / "b.jsonl"
    node_a = HelixNode(events_dir=str(tmp_path / "a_events"), balances_file=str(tmp_path / "a_bal.json"), chain_file=str(chain_a), node_id="A", network=network, microblock_size=2)
    node_b = HelixNode(events_dir=str(tmp_path / "b_events"), balances_file=str(tmp_path / "b_bal.json"), chain_file=str(chain_b), node_id="B", network=network, microblock_size=2)

    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda t, attempts=1000: b"x")
    monkeypatch.setattr("helix.helix_node.verify_seed", lambda s, t: True)

    t_a = threading.Thread(target=node_a._message_loop, daemon=True)
    t_b = threading.Thread(target=node_b._message_loop, daemon=True)
    t_a.start()
    t_b.start()

    ev_a = node_a.create_event("one")
    id_a = ev_a["header"]["statement_id"]
    node_a.events[id_a] = ev_a
    node_a.mine_event(ev_a)
    node_a.finalize_event(ev_a)

    ev_b1 = node_b.create_event("one")
    id_b1 = ev_b1["header"]["statement_id"]
    node_b.events[id_b1] = ev_b1
    node_b.mine_event(ev_b1)
    node_b.finalize_event(ev_b1)

    ev_b2 = node_b.create_event("two")
    id_b2 = ev_b2["header"]["statement_id"]
    node_b.events[id_b2] = ev_b2
    node_b.mine_event(ev_b2)
    node_b.finalize_event(ev_b2)

    time.sleep(0.2)

    chain_a_blocks = bc.load_chain(str(chain_a))
    chain_b_blocks = bc.load_chain(str(chain_b))
    assert chain_a_blocks == chain_b_blocks
    assert len(node_a.blockchain) == len(node_b.blockchain) == 2

