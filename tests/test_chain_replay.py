import hashlib
from pathlib import Path
import pytest

import blockchain as bc
from helix import event_manager


def _find_event_file(evt_id: str) -> Path | None:
    for directory in (Path("data/events"), Path("events")):
        path = directory / f"{evt_id}.json"
        if path.exists():
            return path
    return None


def test_chain_replay():
    chain_path = Path("blockchain.jsonl")
    if not chain_path.exists():
        pytest.skip("blockchain.jsonl not available")

    chain = bc.load_chain(str(chain_path))
    for block in chain:
        delta = block.get("delta_seconds", 0)
        assert delta >= 0
        assert delta < 256

        event_ids = block.get("event_ids") or block.get("event_id") or []
        if isinstance(event_ids, str):
            event_ids = [event_ids]

        for evt_id in event_ids:
            evt_file = _find_event_file(evt_id)
            if not evt_file:
                pytest.skip(f"missing event file for {evt_id}")
            event = event_manager.load_event(str(evt_file))
            statement = event_manager.reassemble_microblocks(event["microblocks"])
            digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
            assert digest == evt_id
            assert digest == event["header"]["statement_id"]
