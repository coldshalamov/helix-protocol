diff --git a//dev/null b/helix/helix_node.py
index 0000000000000000000000000000000000000000..136e83bd40387d1b27f72d33f82a634985ef4628 100644
--- a//dev/null
+++ b/helix/helix_node.py
@@ -0,0 +1,142 @@
+"""Simulated Helix node that mines statements using MiniHelix."""
+
+from __future__ import annotations
+
+import logging
+import random
+import threading
+import time
+from typing import Any, Dict, Generator, List
+
+try:  # pragma: no cover - handle package/script imports
+    from . import event_manager, minihelix
+except ImportError:  # pragma: no cover
+    import event_manager  # type: ignore
+    import minihelix  # type: ignore
+
+# ----------------------------------------------------------------------------
+# Helper functions and mocks
+# ----------------------------------------------------------------------------
+
+def submit_statement_queue() -> Generator[str, None, None]:
+    """Yield example statements awaiting compression.
+
+    In a real deployment this would pull from a network or database queue. For
+    this demo we just return a couple of hardcoded statements.
+    """
+    yield "The James Webb telescope detected complex organic molecules in interstellar space."
+    yield "Water was discovered in samples returned from asteroid Bennu."
+
+
+def simulate_mining(target: bytes, attempts: int = 1_000_000) -> bytes | None:
+    """Return a seed that regenerates ``target`` using MiniHelix mining."""
+    start = time.perf_counter()
+    seed = minihelix.mine_seed(target, max_attempts=attempts)
+    duration = time.perf_counter() - start
+    logging.debug("Mining took %.2f seconds", duration)
+    return seed
+
+
+def auto_resolve_bets(event: Dict[str, Any]) -> None:
+    """Simulate the payout step when an event is fully mined."""
+    logging.info(
+        "Auto resolving bets for event %s (mocked payout)",
+        event["header"]["statement_id"],
+    )
+    # Real chain logic would distribute pools and reward the originator here.
+
+# ----------------------------------------------------------------------------
+# Core node logic
+# ----------------------------------------------------------------------------
+
+class HelixNode:
+    """A basic Helix protocol node that mines incoming statements."""
+
+    def __init__(self, microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE) -> None:
+        self.microblock_size = microblock_size
+        self.logger = logging.getLogger(self.__class__.__name__)
+
+    # ------------------------------------------------------------------
+    # Event lifecycle
+    # ------------------------------------------------------------------
+    def listen_for_statements(self) -> Generator[str, None, None]:
+        """Yield new statements awaiting processing."""
+        yield from submit_statement_queue()
+
+    def create_event(self, statement: str) -> Dict[str, Any]:
+        self.logger.info("Creating event for statement: %s", statement)
+        event = event_manager.create_event(statement, self.microblock_size)
+        # store mined seeds alongside microblocks for later inspection
+        event["mined_seeds"] = [None] * event["header"]["block_count"]
+        return event
+
+    def mine_microblock(self, event: Dict[str, Any], index: int) -> None:
+        """Mine a single microblock and update the event state."""
+        miner_id = random.randint(1000, 9999)
+        self.logger.info("Miner %s started microblock %d", miner_id, index)
+
+        target = event["microblocks"][index]
+        seed = simulate_mining(target)
+
+        if seed is None or not minihelix.verify_seed(seed, target):
+            self.logger.error("Miner %s failed to mine microblock %d", miner_id, index)
+            return
+
+        event["mined_seeds"][index] = seed
+        event_manager.mark_mined(event, index)
+
+        mined = sum(1 for m in event["mined_status"] if m)
+        total = len(event["microblocks"])
+        self.logger.info(
+            "Miner %s finished microblock %d (%d/%d mined) seed=%s",
+            miner_id,
+            index,
+            mined,
+            total,
+            seed.hex(),
+        )
+
+    def mine_event(self, event: Dict[str, Any]) -> None:
+        """Spawn threads to mine all microblocks for an event."""
+        threads = []
+        for i in range(event["header"]["block_count"]):
+            t = threading.Thread(target=self.mine_microblock, args=(event, i))
+            t.start()
+            threads.append(t)
+
+        # Wait for all mining threads to complete
+        for t in threads:
+            t.join()
+
+        if event["is_closed"]:
+            statement = event_manager.reassemble_microblocks(event["microblocks"])
+            seeds = [s.hex() if s else None for s in event["mined_seeds"]]
+            self.logger.info("All microblocks mined. Statement: %s", statement)
+            self.logger.info("Mined seeds: %s", seeds)
+            auto_resolve_bets(event)
+        else:
+            self.logger.warning("Event did not close properly")
+
+    def run(self) -> None:
+        """Main execution loop for the node."""
+        for statement in self.listen_for_statements():
+            event = self.create_event(statement)
+            self.mine_event(event)
+            self.logger.info("Final event state: %s", event)
+
+
+# ----------------------------------------------------------------------------
+# Entry point
+# ----------------------------------------------------------------------------
+
+def main() -> None:
+    logging.basicConfig(
+        level=logging.INFO,
+        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
+    )
+    node = HelixNode()
+    node.run()
+
+
+if __name__ == "__main__":
+    main()
