import sys
import types
import pytest
import blockchain as bc

pytest.importorskip("nacl")


def test_finalize_appends_block(tmp_path, monkeypatch):
    # Provide stub nested_miner before importing event_manager
    stub = types.ModuleType("helix.nested_miner")
    stub.verify_nested_seed = lambda chain, block: True
    sys.modules["helix.nested_miner"] = stub

    import helix.event_manager as em

    chain_file = tmp_path / "chain.jsonl"

    def append_block(header, chain_file=chain_file):
        bc.append_block(header, path=str(chain_file))

    monkeypatch.setattr(em, "append_block", append_block)

    event = em.create_event("hi", microblock_size=2)
    em.accept_mined_seed(event, 0, [b"a"])
    assert event["is_closed"], "event should be closed once mined"

    before = bc.load_chain(str(chain_file))
    em.finalize_event(event, node_id="NODE")
    after = bc.load_chain(str(chain_file))

    assert len(after) == len(before) + 1
    assert event["header"]["statement_id"] in after[-1]["event_ids"]
