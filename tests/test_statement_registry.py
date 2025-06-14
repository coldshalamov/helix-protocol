import pytest

pytest.importorskip("nacl")

from helix import event_manager
from helix.statement_registry import StatementRegistry


def test_reject_duplicate_statement():
    registry = StatementRegistry()
    event_manager.create_event("Unique statement", registry=registry)
    with pytest.raises(ValueError):
        event_manager.create_event("Unique statement", registry=registry)

    # different text allowed
    event_manager.create_event("unique statement", registry=registry)


def test_registry_persistence(tmp_path):
    registry = StatementRegistry()
    event_manager.create_event("Persisted", registry=registry)
    reg_file = tmp_path / "registry.json"
    registry.save(str(reg_file))

    new_reg = StatementRegistry()
    new_reg.load(str(reg_file))
    with pytest.raises(ValueError):
        event_manager.create_event("Persisted", registry=new_reg)


def test_rebuild_from_events(tmp_path):
    registry = StatementRegistry()
    event = event_manager.create_event("Finalized", registry=registry)
    # close the event
    for i in range(event["header"]["block_count"]):
        event_manager.mark_mined(event, i)
    event_manager.save_event(event, str(tmp_path))

    new_reg = StatementRegistry()
    new_reg.rebuild_from_events(str(tmp_path))
    with pytest.raises(ValueError):
        event_manager.create_event("Finalized", registry=new_reg)


