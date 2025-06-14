import json
import pytest

pytest.importorskip("nacl")

from helix import event_manager as em
from helix.config import GENESIS_HASH


def test_load_event_with_valid_parent(tmp_path):
    event = em.create_event("valid")
    path = em.save_event(event, str(tmp_path))
    loaded = em.load_event(path)
    assert loaded["header"]["parent_id"] == GENESIS_HASH


def test_load_event_invalid_parent(tmp_path):
    event = em.create_event("bad")
    event["header"]["parent_id"] = "badparent"
    path = em.save_event(event, str(tmp_path))
    with pytest.raises(ValueError):
        em.load_event(path)
