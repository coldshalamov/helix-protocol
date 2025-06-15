import sys
import types
import hashlib
from pathlib import Path

import pytest
import blockchain as bc
from helix.config import GENESIS_HASH

pytest.importorskip("nacl")


def test_genesis_block_and_chain(tmp_path, monkeypatch):
    # provide stub nested_miner before importing event_manager
    stub = types.ModuleType("helix.nested_miner")
    stub.verify_nested_seed = lambda chain, block: True
    sys.modules["helix.nested_miner"] = stub

    import helix.event_manager as em

    chain_file = tmp_path / "chain.jsonl"

    # verify genesis file hash
    genesis_path = Path("genesis.json")
    data = genesis_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == GENESIS_HASH

    # create a genesis event and mine it
    genesis_event = em.create_event("Genesis block", microblock_size=8)
    for idx in range(genesis_event["header"]["block_count"]):
        em.accept_mined_seed(genesis_event, idx, [b"a"])
    assert genesis_event["is_closed"]

    em.finalize_event(genesis_event, node_id="GEN", chain_file=str(chain_file))
    chain = bc.load_chain(str(chain_file))
    assert len(chain) == 1
    first = chain[0]
    assert first["parent_id"] == GENESIS_HASH
    assert genesis_event["header"]["statement_id"] in first.get("event_ids", [])
    first_id = first["block_id"]

    # create and mine a new event
    ev = em.create_event("test", microblock_size=2)
    for idx in range(ev["header"]["block_count"]):
        em.accept_mined_seed(ev, idx, [b"a"])
    assert ev["is_closed"]

    em.finalize_event(ev, node_id="NODE", chain_file=str(chain_file))
    chain = bc.load_chain(str(chain_file))
    assert len(chain) == 2
    second = chain[1]
    assert second["parent_id"] == first_id
    assert ev["header"]["statement_id"] in second.get("event_ids", [])
