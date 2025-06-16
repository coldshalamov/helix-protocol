import pytest
import blockchain as bc

pytest.importorskip("nacl")


def test_finalize_appends_block(tmp_path):
    import helix.event_manager as em
    from helix import minihelix

    chain_file = tmp_path / "chain.jsonl"

    event = em.create_event("hi", microblock_size=2)
    target_block = event["microblocks"][0]
    seed = minihelix.mine_seed(target_block)
    assert seed is not None
    encoded = bytes([1, len(seed)]) + seed
    em.accept_mined_seed(event, 0, encoded)
    assert event["is_closed"], "event should be closed once mined"

    before = bc.load_chain(str(chain_file))
    em.finalize_event(event, node_id="NODE", chain_file=str(chain_file))
    after = bc.load_chain(str(chain_file))

    assert len(after) == len(before) + 1
    assert event["header"]["statement_id"] in after[-1]["event_ids"]
