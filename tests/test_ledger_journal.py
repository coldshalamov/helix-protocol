import json
import hashlib
from chain_validator import validate_and_mint


def _make_block(parent: str | None = None) -> dict:
    body = {"parent_id": parent}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    body["block_id"] = digest
    return body


def test_mint_logs_entry(tmp_path):
    block = _make_block()
    journal = tmp_path / "ledger_journal.jsonl"
    supply = tmp_path / "supply.json"

    validate_and_mint(block, "WALLET", 5.0, "test", supply_file=str(supply), journal_file=str(journal))

    data = journal.read_text().strip().splitlines()
    assert len(data) == 1
    entry = json.loads(data[0])
    assert entry["action"] == "mint"
    assert entry["wallet"] == "WALLET"
    assert entry["amount"] == 5.0
    assert entry["reason"] == "test"
    assert entry["block"] == block["block_id"]
    assert isinstance(entry["timestamp"], int)

    total = json.load(open(supply))
    assert total["total"] == 5.0
