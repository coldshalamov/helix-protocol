import json
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em
from helix import betting_interface as bi
from helix import signature_utils as su


@pytest.fixture(autouse=True)
def _mock_verify(monkeypatch):
    monkeypatch.setattr(em.nested_miner, "verify_nested_seed", lambda c, b: True)


def test_payout_summary_written(tmp_path):
    events_dir = tmp_path / "events"
    event = em.create_event("payout", microblock_size=2)
    for idx in range(event["header"]["block_count"]):
        em.accept_mined_seed(event, idx, bytes([1, 1]) + b"a")

    pub, priv = su.generate_keypair()
    keyfile = tmp_path / "k.txt"
    su.save_keys(str(keyfile), pub, priv)
    evt_id = event["header"]["statement_id"]
    bet = bi.submit_bet(evt_id, "YES", 10, str(keyfile))
    bi.record_bet(event, bet)

    em.finalize_event(event)
    em.save_event(event, str(events_dir))

    payout_file = events_dir / f"{evt_id}_payouts.json"
    assert payout_file.exists()
    data = em.load_payout_summary(str(payout_file))
    assert data["winning_side"] == "YES"
    assert data["total_stake"] == 10
    assert data["payouts"][pub] == pytest.approx(10.0)

