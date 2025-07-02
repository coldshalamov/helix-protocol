import json
import pytest

pytest.importorskip("nacl")

from helix import helix_cli as cli


def test_view_chain(tmp_path, capsys):
    chain_path = tmp_path / "chain.json"
    data = [
        {
            "id": "b1",
            "parent_id": "genesis",
            "events": ["e1", "e2"],
            "timestamp": 123456,
            "miner": "MINER",
        }
    ]
    chain_path.write_text(json.dumps(data))

    cli.main(["view-chain", "--data-dir", str(tmp_path)])
    out = capsys.readouterr().out.strip()
    assert "0 e1 123456" in out
