import pytest
pytest.importorskip("nacl")

from helix import event_manager as em
from helix import minihelix
import blockchain as bc


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_auto_finalize_miner(tmp_path, monkeypatch):
    chain_file = tmp_path / "chain.jsonl"

    orig_finalize = em.finalize_event

    def patched_finalize(event, *args, **kw):
        kw.setdefault("chain_file", str(chain_file))
        kw.setdefault("events_dir", str(tmp_path))
        kw.setdefault("balances_file", None)
        return orig_finalize(event, *args, **kw)

    monkeypatch.setattr(em, "finalize_event", patched_finalize)

    seed_a = b"a"
    seed_b = b"b"
    statement_bytes = minihelix.G(seed_a, 1) + minihelix.G(seed_b, 1)
    statement = statement_bytes.decode("latin1")

    event = em.create_event(statement, microblock_size=1)

    em.accept_mined_seed(event, 0, [seed_a], miner="M0")
    em.accept_mined_seed(event, 1, [seed_b], miner="M1")

    chain = bc.load_chain(str(chain_file))
    assert len(chain) == 1
    block = chain[0]
    assert block["finalizer"] == "M1"
    assert block["delta_bonus"] == 1
    assert block["event_id"] == event["header"]["statement_id"]
    assert event.get("payouts")
