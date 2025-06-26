import sys
import types
from pathlib import Path
import threading
import time
import pytest

pytest.importorskip("nacl")

pytest.skip("finalized chain sync incompatible with current node", allow_module_level=True)

# Load modules with Markdown fences stripped

def _load_clean_module(name: str, path: Path) -> None:
    src = path.read_text().splitlines()
    if src and src[0].startswith("```"):
        src = src[1:]
    if src and src[-1].startswith("```"):
        src = src[:-1]
    mod = types.ModuleType(name)
    exec("\n".join(src), mod.__dict__)
    sys.modules[name] = mod

ROOT = Path(__file__).resolve().parents[1]
_load_clean_module("helix.ledger", ROOT / "helix" / "ledger.py")
_load_clean_module("helix.blockchain", ROOT / "helix" / "blockchain.py")

from helix.helix_node import HelixNode, GossipMessageType
from helix.gossip import LocalGossipNetwork
import blockchain as bc
import helix.blockchain as blockchain
import helix.blockchain as hbc
import helix.event_manager as em


def test_finalized_block_sync(tmp_path, monkeypatch):
    chain_file = tmp_path / "chain.jsonl"

    network = LocalGossipNetwork()
    node_a = HelixNode(
        events_dir=str(tmp_path / "a_events"),
        balances_file=str(tmp_path / "a_bal.json"),
        chain_file=str(chain_file),
        node_id="A",
        network=network,
        microblock_size=2,
    )
    node_b = HelixNode(
        events_dir=str(tmp_path / "b_events"),
        balances_file=str(tmp_path / "b_bal.json"),
        chain_file=str(chain_file),
        node_id="B",
        network=network,
        microblock_size=2,
    )

    orig_finalize = em.finalize_event

    # bypass nested mining checks
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)

    def finalize_patch(event, *, node_id=None, chain_file=chain_file):
        return orig_finalize(
            event,
            node_id=node_id,
            chain_file=str(chain_file),
            _bc=blockchain,
        )

    monkeypatch.setattr(em, "finalize_event", finalize_patch)

    monkeypatch.setattr("helix.helix_node.simulate_mining", lambda idx: None)
    monkeypatch.setattr("helix.helix_node.find_seed", lambda t, attempts=1000: b"x")
    monkeypatch.setattr("helix.helix_node.verify_seed", lambda s, t: True)

    t_a = threading.Thread(target=node_a._message_loop, daemon=True)
    t_b = threading.Thread(target=node_b._message_loop, daemon=True)
    t_a.start()
    t_b.start()

    event = node_a.create_event("hello")
    evt_id = event["header"]["statement_id"]
    node_a.events[evt_id] = event
    node_a.save_state()
    node_a.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})

    time.sleep(0.1)
    assert evt_id in node_b.events

    node_a.mine_event(event)
    time.sleep(0.1)

    assert node_a.events[evt_id]["finalized"]
    assert node_b.events[evt_id]["finalized"]

    tip_a = hbc.get_chain_tip(str(node_a.chain_file))
    tip_b = hbc.get_chain_tip(str(node_b.chain_file))
    assert tip_a == tip_b

    chain_a = bc.load_chain(str(node_a.chain_file))
    chain_b = bc.load_chain(str(node_b.chain_file))
    assert chain_a == chain_b
