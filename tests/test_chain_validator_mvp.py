import json
import pytest

import chain_validator as cv
from helix import minihelix


def test_tiebreak_delta_equal():
    a = {"seed": b"a", "delta_seconds": 1.0, "pubkey": "b"}
    b = {"seed": b"b", "delta_seconds": 1.0, "pubkey": "a"}
    winner = cv.resolve_seed_collision(a, b)
    assert winner is a


def test_tiebreak_pubkey_equal():
    a = {"seed": b"b", "delta_seconds": 1.0, "pubkey": "a"}
    c = {"seed": b"a", "delta_seconds": 1.0, "pubkey": "a"}
    winner = cv.resolve_seed_collision(a, c)
    assert winner is a


def test_validate_and_mint(tmp_path):
    micro = minihelix.G(b"a", 3)
    journal = tmp_path / "ledger_journal.jsonl"
    supply = tmp_path / "supply.json"
    amount = cv.validate_and_mint(b"a", micro, "alice", "block1", journal_path=str(journal), supply_path=str(supply))
    assert amount == 2.0
    with open(journal, "r", encoding="utf-8") as fh:
        line = json.loads(fh.readline())
    assert line["wallet"] == "alice"
    assert line["amount"] == amount
    with open(supply, "r", encoding="utf-8") as fh:
        total = json.load(fh)["total"]
    assert total == amount

    # invalid seed should raise
    with pytest.raises(ValueError):
        cv.validate_and_mint(b"aaa", micro, "alice", "block1", journal_path=str(journal), supply_path=str(supply))

