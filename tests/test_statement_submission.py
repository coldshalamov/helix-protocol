import hashlib
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em
from helix.event_manager import verify_event_signature
from helix import signature_utils as su


def test_create_event_with_signature():
    statement = "Helix test statement"
    pub, priv = su.generate_keypair()
    event = em.create_event(statement, microblock_size=4, private_key=priv)

    header_hash = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    assert event["header"]["statement_id"] == header_hash
    assert len(event["microblocks"]) == event["header"]["block_count"]
    merkle_root, tree = em.build_merkle_tree(event["microblocks"])
    assert event["header"]["merkle_root"] == merkle_root
    assert event["merkle_tree"] == tree
    assert verify_event_signature(event)


def test_create_event_without_signature():
    event = em.create_event("No sig", microblock_size=4)
    assert "merkle_root" in event["header"]
    assert isinstance(event.get("merkle_tree"), list)
    assert not verify_event_signature(event)
