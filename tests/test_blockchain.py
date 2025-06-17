import pytest
import blockchain as bc

pytest.importorskip("nacl")


def test_finalize_appends_block(tmp_path):
    import helix.event_manager as em
    from helix import minihelix, nested_miner

    chain_file = tmp_path / "chain.jsonl"

    seed = b"a"
    target_block = minihelix.G(seed, 2)
    event = em.create_event(target_block.decode("utf-8"), microblock_size=2)
    encoded = bytes([1, len(seed)]) + seed
    assert nested_miner.verify_nested_seed(encoded, target_block)
    em.accept_mined_seed(event, 0, encoded)
    assert event["is_closed"], "event should be closed once mined"

    before = bc.load_chain(str(chain_file))
    em.finalize_event(event, node_id="NODE", chain_file=str(chain_file))
    after = bc.load_chain(str(chain_file))

    assert len(after) == len(before) + 1
    assert event["header"]["statement_id"] in after[-1]["event_ids"]
