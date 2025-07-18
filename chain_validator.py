import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Iterable

from helix import minihelix, blockchain, event_manager
from helix.ledger import load_balances, _update_total_supply, log_ledger_event


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pubkey_hash(pub: str | bytes) -> str:
    """Return hex SHA-256 hash of ``pub``."""
    if isinstance(pub, str):
        pub = pub.encode("utf-8")
    return sha256_hex(pub)


def resolve_seed_collision(current: Dict[str, Any] | None, challenger: Dict[str, Any]) -> Dict[str, Any]:
    """Return the canonical seed info between ``current`` and ``challenger``.

    Each mapping must contain ``seed`` (bytes), ``delta_seconds`` (float), and
    ``pubkey`` (str).  ``current`` may be ``None`` indicating no existing seed.
    The function returns the preferred mapping according to canonical
    tie–breaking rules.
    """

    if current is None:
        return challenger

    a, b = current, challenger

    # shorter seed wins
    if len(b["seed"]) < len(a["seed"]):
        return b
    if len(b["seed"]) > len(a["seed"]):
        return a

    # lower delta_seconds wins
    if b["delta_seconds"] < a["delta_seconds"]:
        return b
    if b["delta_seconds"] > a["delta_seconds"]:
        return a

    # lower pubkey hash wins
    ph_a = _pubkey_hash(a["pubkey"])
    ph_b = _pubkey_hash(b["pubkey"])
    if ph_b < ph_a:
        return b
    if ph_b > ph_a:
        return a

    # lexicographically lower seed hash wins
    sh_a = sha256_hex(a["seed"])
    sh_b = sha256_hex(b["seed"])
    if sh_b < sh_a:
        return b
    return a


def validate_and_mint(
    seed: bytes,
    microblock: bytes,
    wallet: str,
    block_hash: str,
    *,
    journal_path: str = "ledger_journal.jsonl",
    supply_path: str = "supply.json",
) -> float:
    """Mint HLX for valid compression proof and log the event.

    Returns the minted amount.
    """

    if minihelix.G(seed, len(microblock)) != microblock:
        raise ValueError("invalid seed for microblock")
    if len(seed) >= len(microblock):
        raise ValueError("seed does not achieve compression")

    amount = float(len(microblock) - len(seed))

    entry = {
        "action": "mint",
        "reason": "compression_reward",
        "wallet": wallet,
        "block": block_hash,
        "timestamp": int(time.time()),
        "amount": amount,
    }
    with open(journal_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    _update_total_supply(amount, path=supply_path)
    return amount


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


def validate_block_mint(
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


def verify_supply_consistency(events_dir: str, supply_path: str) -> bool:
    """Verify that minted HLX in the ledger journal matches ``supply_path``.

    The function sums all ``mint`` actions recorded in ``ledger_journal.jsonl``
    under ``events_dir`` and compares the total against the ``total`` field in
    ``supply_path``.  A :class:`ValueError` is raised if the values differ.
    """

    journal = Path(events_dir) / "ledger_journal.jsonl"
    if not journal.exists():
        raise FileNotFoundError(journal)

    minted = 0.0
    with open(journal, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("action") == "mint":
                minted += float(entry.get("amount", 0.0))

    with open(supply_path, "r", encoding="utf-8") as fh:
        supply_total = float(json.load(fh).get("total", 0.0))

    if abs(minted - supply_total) > 1e-6:
        raise ValueError(f"supply mismatch: journal={minted} expected={supply_total}")
    return True


if __name__ == "__main__":
    replay_chain()
