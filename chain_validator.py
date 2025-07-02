import json
import hashlib
from pathlib import Path
from typing import Dict, Any

from helix import minihelix, blockchain, event_manager
from helix.ledger import load_balances, _update_total_supply, log_ledger_event


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_block_hash(block: Dict[str, Any], parent_id: str | None) -> None:
    block_copy = dict(block)
    block_id = block_copy.pop("block_id", None)
    if block_id is None:
        raise ValueError("missing block_id")
    if parent_id is not None and block_copy.get("parent_id") != parent_id:
        raise ValueError("parent_id mismatch")
    digest = sha256_hex(json.dumps(block_copy, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if digest != block_id:
        raise ValueError("block hash mismatch")


def verify_event(event: Dict[str, Any]) -> None:
    statement = event.get("statement")
    header = event.get("header", {})
    stmt_id = header.get("statement_id")
    if not isinstance(statement, str) or not stmt_id:
        raise ValueError("missing statement or id")
    digest = sha256_hex(statement.encode("utf-8"))
    if digest != stmt_id:
        raise ValueError("statement_id mismatch")

    reassembled = event_manager.reassemble_microblocks(event.get("microblocks", []))
    if reassembled != statement:
        raise ValueError("microblock reassembly mismatch")

    if not event_manager.verify_statement(event):
        raise ValueError("seed verification failed")


def compute_payouts(event: Dict[str, Any], miner: str | None) -> Dict[str, float]:
    header = event.get("header", {})
    yes_raw = event.get("bets", {}).get("YES", [])
    no_raw = event.get("bets", {}).get("NO", [])

    valid_yes = [b for b in yes_raw if event_manager.betting_interface.verify_bet(b)]
    valid_no = [b for b in no_raw if event_manager.betting_interface.verify_bet(b)]

    yes_total = sum(b.get("amount", 0) for b in valid_yes)
    no_total = sum(b.get("amount", 0) for b in valid_no)

    success = yes_total > no_total
    winners = valid_yes if success else valid_no
    winner_total = yes_total if success else no_total

    pot = yes_total + no_total
    payouts: Dict[str, float] = {}

    originator = event.get("originator_pub") or header.get("originator_pub")
    if success and originator:
        refund = pot * 0.01
        payouts[originator] = payouts.get(originator, 0.0) + refund
        pot -= refund

    if winner_total > 0:
        for bet in winners:
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if pub:
                payout = pot * (amt / winner_total)
                payouts[pub] = payouts.get(pub, 0.0) + payout

    miner_reward = event_manager.compute_reward(event)
    if miner:
        payouts[miner] = payouts.get(miner, 0.0) + miner_reward

    unaligned_total = float(event.get("unaligned_funds", 0.0))
    if unaligned_total > 0:
        miner_counts: Dict[str, int] = {}
        for m in event.get("refund_miners", []):
            if m:
                miner_counts[m] = miner_counts.get(m, 0) + 1
        total_count = sum(miner_counts.values())
        if total_count:
            for m, count in miner_counts.items():
                share = unaligned_total * (count / total_count)
                payouts[m] = payouts.get(m, 0.0) + share

    return payouts


def validate_and_mint(
    block: Dict[str, Any],
    wallet: str,
    amount: float,
    reason: str,
    *,
    supply_file: str = "supply.json",
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Validate ``block`` then mint ``amount`` HLX to ``wallet``.

    The block hash is verified and a ledger event is recorded before the total
    supply is increased.
    """

    parent_id = block.get("parent_id")
    verify_block_hash(block, parent_id)

    block_hash = block["block_id"]
    log_ledger_event("mint", wallet, amount, reason, block_hash, journal_file=journal_file)
    _update_total_supply(amount, path=supply_file)


def replay_chain(chain_path: str = "blockchain.jsonl", events_dir: str = "data/events", balances_file: str | None = None) -> None:
    chain_file = Path(chain_path)
    if not chain_file.exists():
        raise SystemExit(f"Chain file {chain_path} not found")

    balances: Dict[str, float] = {}
    if balances_file and Path(balances_file).exists():
        balances = load_balances(balances_file)

    events_path = Path(events_dir)
    parent_id: str | None = None

    with open(chain_file, "r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                block = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_num}: {e}") from e

            verify_block_hash(block, parent_id)

            for evt_id in block.get("event_ids", []):
                evt_path = events_path / f"{evt_id}.json"
                if not evt_path.exists():
                    raise ValueError(f"missing event file {evt_path}")
                event = event_manager.load_event(str(evt_path))
                verify_event(event)

                payouts = compute_payouts(event, block.get("miner"))
                recorded = event.get("payouts", {})
                for acct, amt in payouts.items():
                    rec = recorded.get(acct)
                    if rec is None or abs(rec - amt) > 1e-6:
                        raise ValueError(f"payout mismatch in event {evt_id} for {acct}")
                for acct, amt in payouts.items():
                    balances[acct] = balances.get(acct, 0.0) + amt

            parent_id = block["block_id"]

    print("Chain is valid ✅")


if __name__ == "__main__":
    replay_chain()
