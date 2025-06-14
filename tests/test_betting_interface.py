import pytest

pytest.importorskip("nacl")

from helix import betting_interface as bi
from helix import event_manager as em
from helix import signature_utils as su


def test_submit_and_verify_bet(tmp_path):
    pub, priv = su.generate_keypair()
    keyfile = tmp_path / "keys.txt"
    su.save_keys(str(keyfile), pub, priv)

    event = em.create_event("Bet event")

    bet = bi.submit_bet(event["header"]["statement_id"], "YES", 10, str(keyfile))
    assert bi.verify_bet(bet)

    bi.record_bet(event, bet)
    assert bet in event["bets"]["YES"]


def test_invalid_bet_choice(tmp_path):
    pub, priv = su.generate_keypair()
    keyfile = tmp_path / "keys.txt"
    su.save_keys(str(keyfile), pub, priv)

    with pytest.raises(ValueError):
        bi.submit_bet("id", "MAYBE", 5, str(keyfile))

