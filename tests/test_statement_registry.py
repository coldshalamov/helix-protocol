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


def test_cleanup_events(tmp_path):
    registry = StatementRegistry()

    events_dir = tmp_path / "events"
    events_dir.mkdir()

    evt1 = event_manager.create_event("keep", registry=registry)
    event_manager.save_event(evt1, str(events_dir))
    evt2 = event_manager.create_event("remove", registry=registry)
    event_manager.save_event(evt2, str(events_dir))

    (events_dir / "bad.json").write_text("{not valid")

    chain_file = tmp_path / "blockchain.jsonl"
    bc_block = {
        "parent_id": "0" * 64,
        "event_ids": [evt1["header"]["statement_id"]],
        "block_id": "1" * 64,
    }
    import blockchain as bc
    bc.append_block(bc_block, path=str(chain_file))

    removed = registry.cleanup_events(str(events_dir), chain_file=str(chain_file))

    remaining = {p.name for p in events_dir.glob("*.json")}
    assert f"{evt1['header']['statement_id']}.json" in remaining
    assert f"{evt2['header']['statement_id']}.json" not in remaining
    assert "bad.json" not in remaining
    assert len(removed) == 2


