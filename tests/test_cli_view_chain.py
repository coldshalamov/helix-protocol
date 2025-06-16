import json
import pytest

pytest.importorskip("nacl")

from helix import cli


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

    cli.main(["--data-dir", str(tmp_path), "view-chain"])
    out = capsys.readouterr().out.strip()
    assert "0 b1 e1,e2 123456 MINER" in out
