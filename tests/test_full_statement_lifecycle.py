import pytest

pytest.importorskip("nacl")

from helix import minihelix
from helix import event_manager as em


def test_full_statement_lifecycle(tmp_path):
    statement = "ikijegwbl"
    event = em.create_event(statement, microblock_size=3)

    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block)
        assert seed is not None
        em.accept_mined_seed(event, idx, [seed])

    assert event["is_closed"]

    chain_file = tmp_path / "chain.jsonl"
    payouts = em.finalize_event(event, node_id="MINER", chain_file=str(chain_file))

    assert em.reassemble_microblocks(event["microblocks"]) == statement

    assert event["payouts"] == payouts
    assert payouts["MINER"] == pytest.approx(3.0)
    assert event["miner_reward"] == pytest.approx(3.0)
