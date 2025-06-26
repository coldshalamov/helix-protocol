import json
import pytest

pytest.importorskip("nacl")

import pytest

from helix import helix_cli


pytest.skip("submit-statement command removed", allow_module_level=True)


def test_submit_statement(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    statement = "The Earth revolves around the Sun."
    helix_cli.main(["submit-statement", statement, "--block-size", "8"])
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert out_lines
    event_id = out_lines[0].split()[-1] if len(out_lines[0].split()) > 1 else out_lines[0]
    event_file = tmp_path / "data" / "events" / f"{event_id}.json"
    assert event_file.exists()
    with open(event_file, "r", encoding="utf-8") as f:
        evt = json.load(f)
    assert evt["header"]["block_count"] == len(evt["microblocks"])
    assert int(out_lines[1].split()[-1]) == evt["header"]["block_count"]

