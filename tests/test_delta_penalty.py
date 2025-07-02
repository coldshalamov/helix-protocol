import pytest
from helix.ledger import delta_claim_valid
from datetime import datetime, timedelta


def _block(block_id, parent_id, timestamp, delta):
    return {
        "block_id": block_id,
        "parent_id": parent_id,
        "timestamp": timestamp.isoformat(),
        "delta_seconds": delta,
    }


def test_delta_claim_honest():
    parent = _block("p", "g", datetime.utcnow(), 0)
    child_ts = datetime.utcnow() + timedelta(seconds=5)
    child = _block("c", "p", child_ts, 5)
    assert delta_claim_valid(child, parent)


def test_delta_claim_dishonest():
    parent = _block("p", "g", datetime.utcnow(), 0)
    child_ts = datetime.utcnow() + timedelta(seconds=5)
    child = _block("c", "p", child_ts, 20)
    assert not delta_claim_valid(child, parent)


def test_delta_claim_invalid_parent():
    parent = _block("p", "g", datetime.utcnow(), 0)
    child = _block("c", "x", datetime.utcnow(), 5)
    # Parent mismatch results in True (no penalty applied)
    assert delta_claim_valid(child, parent)
