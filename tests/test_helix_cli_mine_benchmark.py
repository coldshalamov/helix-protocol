import time
import pytest

pytest.importorskip("nacl")

from helix import helix_cli, nested_miner


def test_mine_benchmark(monkeypatch, capsys):
    monkeypatch.setattr(nested_miner, "hybrid_mine", lambda block, max_depth=4: (b"a", 1))
    times = iter([0.0, 1.0])
    monkeypatch.setattr(time, "perf_counter", lambda: next(times))

    helix_cli.main(["mine-benchmark"])
    out = capsys.readouterr().out
    assert "Time: 1.00s" in out
    assert "G() calls: 0" in out
    assert "Compression ratio: 8.00x" in out

