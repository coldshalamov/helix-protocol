import json
from pathlib import Path
from fastapi.testclient import TestClient
from dashboard.backend import main


def test_statement_history_endpoint(tmp_path, monkeypatch):
    finalized = tmp_path / "finalized.jsonl"
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    event = {
        "header": {"statement_id": "abc", "microblock_size": 2, "block_count": 1},
        "statement": "hello",
        "microblocks": ["6869"],
        "seeds": ["aa"],
        "miners": ["m1"],
        "is_closed": True,
        "finalized": True,
    }
    (events_dir / "abc.json").write_text(json.dumps(event))

    entry = {
        "statement_id": "abc",
        "statement": "hello",
        "previous_hash": "00",
        "delta_seconds": 1.0,
        "seeds": ["aa"],
        "miners": ["m1"],
        "timestamp": 10.0,
    }
    finalized.write_text(json.dumps(entry) + "\n")

    monkeypatch.setattr(main, "FINALIZED_FILE", finalized)
    monkeypatch.setattr(main, "EVENTS_DIR", events_dir)

    client = TestClient(main.app)
    resp = client.get("/api/statements/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    rec = data[0]
    assert rec["finalized"] is True
    assert rec["statement_id"] == "abc"
    assert rec["timestamp"] == 10.0
    assert rec["statement"] == "hello"
    assert rec["seeds"] == ["aa"]
    assert "compression_ratio" in rec
