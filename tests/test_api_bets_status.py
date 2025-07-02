from fastapi.testclient import TestClient

from dashboard.backend import main
from helix import event_manager, betting_interface, signature_utils


def test_bet_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "EVENTS_DIR", tmp_path)

    client = TestClient(main.app)

    event = event_manager.create_event("bet test", microblock_size=2)
    evt_id = event["header"]["statement_id"]

    # create YES bet
    pub1, priv1 = signature_utils.generate_keypair()
    kf1 = tmp_path / "w1.txt"
    signature_utils.save_keys(str(kf1), pub1, priv1)
    bet1 = betting_interface.submit_bet(evt_id, "YES", 5, str(kf1))
    betting_interface.record_bet(event, bet1)

    # create NO bet
    pub2, priv2 = signature_utils.generate_keypair()
    kf2 = tmp_path / "w2.txt"
    signature_utils.save_keys(str(kf2), pub2, priv2)
    bet2 = betting_interface.submit_bet(evt_id, "NO", 3, str(kf2))
    betting_interface.record_bet(event, bet2)

    event_manager.save_event(event, str(tmp_path))

    res = client.get(f"/api/bets/status/{evt_id}")
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "statement_id": evt_id,
        "total_true_bets": 5.0,
        "total_false_bets": 3.0,
    }
