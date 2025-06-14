import logging
import random
import threading
import time
from typing import Any, Dict, Generator

try:
    from . import event_manager
except ImportError:  # pragma: no cover - allow running as a script
    import event_manager

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


def simulate_mining(block_index: int) -> None:
    """Mock the MiniHelix GPoW process for a single microblock."""
    # Future implementation will search for a seed that regenerates the microblock
    # using the MiniHelix algorithm. Here we just sleep for a short random time
    # to emulate work being done.
    time.sleep(random.uniform(0.5, 1.5))


def auto_resolve_bets(event: Dict[str, Any]) -> None:
    """Simulate the payout step when an event is fully mined."""
    logging.info(
        "Auto resolving bets for event %s (mocked payout)",
        event["header"]["statement_id"],
    )
    # Real chain logic would distribute pools and reward the originator here.

# ----------------------------------------------------------------------------
# Core node logic
# ----------------------------------------------------------------------------

class HelixNode:
    """A basic Helix protocol node that mines incoming statements."""

    def __init__(self, microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE) -> None:
        self.microblock_size = microblock_size
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Event lifecycle
    # ------------------------------------------------------------------
    def listen_for_statements(self) -> Generator[str, None, None]:
        """Yield new statements awaiting processing."""
        yield from submit_statement_queue()

    def create_event(self, statement: str) -> Dict[str, Any]:
        self.logger.info("Creating event for statement: %s", statement)
        return event_manager.create_event(statement, self.microblock_size)

    def mine_microblock(self, event: Dict[str, Any], index: int) -> None:
        """Mine a single microblock and update the event state."""
        miner_id = random.randint(1000, 9999)
        self.logger.info("Miner %s started microblock %d", miner_id, index)
        simulate_mining(index)
        event_manager.mark_mined(event, index)
        mined = sum(1 for m in event["mined_status"] if m)
        total = len(event["microblocks"])
        self.logger.info(
            "Miner %s finished microblock %d (%d/%d mined)",
            miner_id,
            index,
            mined,
            total,
        )

    def mine_event(self, event: Dict[str, Any]) -> None:
        """Spawn threads to mine all microblocks for an event."""
        threads = []
        for i in range(event["header"]["block_count"]):
            t = threading.Thread(target=self.mine_microblock, args=(event, i))
            t.start()
            threads.append(t)

        # Wait for all mining threads to complete
        for t in threads:
            t.join()

        if event["is_closed"]:
            auto_resolve_bets(event)
            statement = event_manager.reassemble_microblocks(event["microblocks"])
            self.logger.info("Event closed. Reassembled statement: %s", statement)
        else:
            self.logger.warning("Event did not close properly")

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
