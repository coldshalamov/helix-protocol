import hashlib
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em
from helix.helix_node import verify_originator_signature
from helix import signature_utils as su


def test_create_event_with_signature(tmp_path):
    statement = "Helix test statement"
    pub, priv = su.generate_keypair()
    keyfile = tmp_path / "keys.txt"
    su.save_keys(str(keyfile), pub, priv)

    event = em.create_event(statement, microblock_size=4, keyfile=str(keyfile))

    header_hash = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    assert event["header"]["statement_id"] == header_hash
    assert len(event["microblocks"]) == event["header"]["block_count"]
    assert verify_originator_signature(event)


def test_create_event_without_signature():
    event = em.create_event("No sig", microblock_size=4)
    assert not verify_originator_signature(event)
