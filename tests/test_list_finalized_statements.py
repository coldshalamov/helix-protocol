import json
import pytest

from helix import statement_registry as sr


def test_list_finalized_statements(tmp_path, monkeypatch):
    path = tmp_path / "finalized_statements.jsonl"
    entries = [
        {"statement_id": "a", "timestamp": 1.0, "delta_seconds": 0.1, "seeds": ["aa"]},
        {"statement_id": "b", "timestamp": 2.0, "delta_seconds": 0.2, "seeds": ["bb", "01"]},
        {"statement_id": "c", "timestamp": 3.0, "delta_seconds": 0.3, "seeds": ["cc"]},
    ]
    with open(path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    monkeypatch.setattr(sr, "_FINALIZED_FILE", str(path))

    result = sr.list_finalized_statements(limit=2)
    assert result == [
        ("c", 3.0, 0.3, 1),
        ("b", 2.0, 0.2, 2),
    ]
