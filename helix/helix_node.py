from __future__ import annotations

import logging
import random
import threading
from pathlib import Path
from typing import Any, Dict, Generator

try:
    from . import event_manager
    from .signature_utils import verify_signature
    from .ledger import load_balances, save_balances
    from .minihelix import mine_seed as find_seed, verify_seed
except ImportError:  # pragma: no cover - allow running as a script
    from helix import event_manager
    from helix.signature_utils import verify_signature
    from helix.ledger import load_balances, save_balances
    from helix.minihelix import mine_seed as find_seed, verify_seed

# ----------------------------------------------------------------------------
# Signature Verification
# ----------------------------------------------------------------------------

def verify_originator_signature(event: Dict[str, Any]) -> bool:
    """Return ``True`` if the event header signature is valid."""
    header = event.get("header", {}).copy()
    sig = header.pop("originator_sig", None)
    pub = header.pop("originator_pub", None)
    if not sig or not pub:
        return False
    return verify_signature(repr(header).encode("utf-8"), sig, pub)

# ----------------------------------------------------------------------------
# Helper functions and mocks
# ----------------------------------------------------------------------------

def submit_statement_queue() -> Generator[str, None, None]:
    """Yield new statements submitted to the node.

    In a real deployment this would interface with a network queue or RPC
    layer. For now it simply yields a single hardcoded statement.
    """
    statement = (
        "The James Webb telescope detected complex organic molecules in interstellar space."
    )
    yield statement


def auto_resolve_bets(event: Dict[str, Any]) -> None:
    """Deprecated helper kept for backward compatibility."""
    logging.info(
        "Auto resolving bets for event %s (mocked payout)",
        event["header"]["statement_id"],
    )

# ----------------------------------------------------------------------------
# Core node logic
# ----------------------------------------------------------------------------

class HelixNode:
    """A basic Helix protocol node that mines incoming statements."""

    def __init__(
        self,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        *,
        events_dir: str = "events",
        balances_file: str = "balances.json",
    ) -> None:
        self.microblock_size = microblock_size
        self.logger = logging.getLogger(self.__class__.__name__)
        self.events_dir = events_dir
        self.balances_file = balances_file
        self.balances = load_balances(self.balances_file)

    # ------------------------------------------------------------------
    # Event lifecycle
    # ------------------------------------------------------------------
    def listen_for_statements(self) -> Generator[str, None, None]:
        """Yield new statements awaiting processing."""
        yield from submit_statement_queue()

    def create_event(self, statement: str) -> Dict[str, Any]:
        self.logger.info("Creating event for statement: %s", statement)
        statement_id = event_manager.sha256(statement.encode("utf-8"))
        path = Path(self.events_dir) / f"{statement_id}.json"
        if path.exists():
            evt = event_manager.load_event(path)
            if evt.get("statement") == statement:
                self.logger.info("Loaded existing event %s", statement_id)
                return evt
        return event_manager.create_event(statement, self.microblock_size)

    def mine_microblock(self, event: Dict[str, Any], index: int) -> None:
        """Mine a single microblock and update the event state."""
        miner_id = random.randint(1000, 9999)
        self.logger.info("Miner %s started microblock %d", miner_id, index)
        target = event["microblocks"][index]
        seed = find_seed(target, max_attempts=1000000)
        if seed is not None and verify_seed(seed, target):
            event["seeds"][index] = seed
            event_manager.mark_mined(event, index)
            status = "mined"
        else:
            status = "failed"
        self.logger.info("Microblock %d %s by miner %s", index, status, miner_id)
        mined = sum(1 for m in event["mined_status"] if m)
        total = len(event["microblocks"])
        self.logger.info(
            "Progress: %d/%d mined",
            mined,
            total,
        )

    def mine_event(self, event: Dict[str, Any]) -> None:
        """Verify originator signature and mine all microblocks for an event."""
        if not verify_originator_signature(event):
            self.logger.error("Invalid originator signature. Event rejected.")
            return

        threads = []
        for i in range(event["header"]["block_count"]):
            t = threading.Thread(target=self.mine_microblock, args=(event, i))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if event["is_closed"]:
            self.resolve_bets(event)
            path = event_manager.save_event(event, self.events_dir)
            self.logger.info("Saved event to %s", path)
            statement = event_manager.reassemble_microblocks(event["microblocks"])
            self.logger.info("Event closed. Reassembled statement: %s", statement)
        else:
            self.logger.warning("Event did not close properly")

    # ------------------------------------------------------------------
    # Bet resolution
    # ------------------------------------------------------------------
    def resolve_bets(self, event: Dict[str, Any]) -> None:
        """Distribute betting pool to winners and originator."""
        yes_bets = event.get("bets", {}).get("YES", [])
        no_bets = event.get("bets", {}).get("NO", [])
        yes_total = sum(b.get("amount", 0) for b in yes_bets)
        no_total = sum(b.get("amount", 0) for b in no_bets)
        if yes_total == no_total:
            winner = "YES"
        else:
            winner = "YES" if yes_total > no_total else "NO"
        event["result"] = winner
        pot = yes_total + no_total
        originator = event["header"].get("originator_pub")
        origin_cut = pot * 0.01 if originator else 0
        if originator:
            self.balances[originator] = self.balances.get(originator, 0) + origin_cut
        winner_pool = pot - origin_cut
        winners = event["bets"][winner]
        total_winner = sum(b["amount"] for b in winners) or 1
        for bet in winners:
            share = bet["amount"] / total_winner
            reward = share * winner_pool
            key = bet["pubkey"]
            self.balances[key] = self.balances.get(key, 0) + reward
        save_balances(self.balances, self.balances_file)

    def run(self) -> None:
        """Main execution loop for the node."""
        for statement in self.listen_for_statements():
            event = self.create_event(statement)
            self.mine_event(event)
            self.logger.info("Final event state: %s", event)


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    node = HelixNode()
    node.run()


if __name__ == "__main__":
    main()
