import json
from helix import ledger


def _event(seed):
    return {
        "microblocks": ["616263"],
        "seeds": [seed],
        "miners": ["M"],
        "block_header": {"block_id": "blk"},
    }


def test_cumulative_rewards(tmp_path):
    j = tmp_path / "j.jsonl"
    balances = {}
    event = _event(b"ab")
    ledger.apply_mining_results(event, balances, journal_file=str(j))
    assert balances["M"] == 1.0
    event["seeds"][0] = b"a"
    ledger.apply_mining_results(event, balances, journal_file=str(j))
    assert balances["M"] == 2.0
    entries = [json.loads(l) for l in j.read_text().splitlines()]
    assert len(entries) == 2
    assert all(e["reason"] == "compression_reward" for e in entries)


def test_delta_penalty(tmp_path):
    j = tmp_path / "j.jsonl"
    balances = {}
    ledger.apply_delta_bonus("B", balances, 2, block_hash="h", journal_file=str(j))
    assert balances["B"] == 2
    ledger.apply_delta_penalty("B", balances, 2, block_hash="h", journal_file=str(j))
    assert balances["B"] == 0
    entries = [json.loads(l) for l in j.read_text().splitlines()]
    assert entries[0]["reason"] == "delta_bonus"
    assert entries[1]["reason"] == "delta_penalty"
