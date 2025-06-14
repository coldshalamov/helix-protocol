import hashlib
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import event_manager, minihelix, nested_miner
from .config import GENESIS_HASH
from .ledger import load_balances, save_balances
from .gossip import GossipNode, LocalGossipNetwork


class GossipMessageType:
    """Basic gossip message types used between :class:`HelixNode` peers."""

    NEW_STATEMENT = "NEW_STATEMENT"
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    FINALIZED = "FINALIZED"


def simulate_mining(index: int) -> None:
    """Placeholder hook executed before mining ``index``."""
    return None


def find_seed(target: bytes, attempts: int = 1_000_000) -> Optional[bytes]:
    """Search for a seed regenerating ``target``."""
    return minihelix.mine_seed(target, max_attempts=attempts)


def verify_seed(seed: bytes, target: bytes) -> bool:
    """Verify ``seed`` regenerates ``target``."""
    return minihelix.verify_seed(seed, target)


def verify_statement_id(event: Dict[str, Any]) -> bool:
    """Return ``True`` if the statement_id matches the statement hash."""
    statement = event.get("statement")
    stmt_id = event.get("header", {}).get("statement_id")
    if not isinstance(statement, str) or not stmt_id:
        return False
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    return digest == stmt_id


class HelixNode(GossipNode):
    """Minimal Helix node used for tests."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        node_id: str = "NODE",
        network: Optional[LocalGossipNetwork] = None,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        genesis_file: str = "genesis.json",
        max_nested_depth: int = 3,
    ) -> None:
        if network is None:
            network = LocalGossipNetwork()
        super().__init__(node_id, network)
        self.events_dir = events_dir
        self.balances_file = balances_file
        self.microblock_size = microblock_size
        self.genesis_file = genesis_file
        self.max_nested_depth = max_nested_depth
        self.genesis = self._load_genesis(genesis_file)
        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances: Dict[str, int] = {}
        self.load_state()

    def _load_genesis(self, path: str) -> dict:
        data = Path(path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != GENESIS_HASH:
            raise ValueError("genesis.json does not match GENESIS_HASH")
        return json.loads(data.decode("utf-8"))

    def load_state(self) -> None:
        Path(self.events_dir).mkdir(parents=True, exist_ok=True)
        for fname in os.listdir(self.events_dir):
            if not fname.endswith(".json"):
                continue
            try:
                event = event_manager.load_event(os.path.join(self.events_dir, fname))
            except Exception:
                continue
            if event.get("header", {}).get("parent_id") != GENESIS_HASH:
                continue
            self.events[event["header"]["statement_id"]] = event
        self.balances = load_balances(self.balances_file)

    def save_state(self) -> None:
        for event in self.events.values():
            event_manager.save_event(event, self.events_dir)
        save_balances(self.balances, self.balances_file)

    def create_event(self, statement: str, *, private_key: Optional[str] = None) -> dict:
        return event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            parent_id=GENESIS_HASH,
            private_key=private_key,
        )

    def import_event(self, event: dict) -> None:
        if event.get("header", {}).get("parent_id") != GENESIS_HASH:
            raise ValueError("invalid parent_id")
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    def mine_event(self, event: dict) -> None:
        evt_id = event["header"]["statement_id"]
        for idx, block in enumerate(event["microblocks"]):
            if event.get("is_closed"):
                break
            if event["seeds"][idx]:
                continue
            simulate_mining(idx)
            best_seed: Optional[bytes] = None
            best_depth = 0
            best_chain: Optional[list[bytes]] = None

            seed = find_seed(block)
            if seed and verify_seed(seed, block):
                best_seed = seed
                best_depth = 1

            for depth in range(2, self.max_nested_depth + 1):
                if best_seed is not None and best_depth <= depth:
                    break
                result = nested_miner.find_nested_seed(block, max_depth=depth)
                if result:
                    chain, found_depth = result
                    if not nested_miner.verify_nested_seed(chain, block):
                        continue
                    candidate = chain[0]
                    if (
                        best_seed is None
                        or found_depth < best_depth
                        or (found_depth == best_depth and len(candidate) < len(best_seed))
                    ):
                        best_seed = candidate
                        best_depth = found_depth
                        best_chain = chain

            if best_seed is not None and best_chain is not None:
                previous_seed = event["seeds"][idx]
                previous_depth = event["seed_depths"][idx]

                event_manager.accept_mined_seed(event, idx, best_chain)

                self.send_message(
                    {
                        "type": GossipMessageType.MINED_MICROBLOCK,
                        "event_id": evt_id,
                        "index": idx,
                        "seed": best_seed.hex(),
                        "depth": best_depth,
                    }
                )

                if previous_seed is not None and event["seeds"][idx] == previous_seed:
                    reason = []
                    if len(best_seed) != len(previous_seed):
                        reason.append("same length")
                    if best_depth >= previous_depth:
                        reason.append("depth not improved")
                    print(f"Seed for block {idx} rejected ({', '.join(reason)})")

                event_manager.save_event(event, self.events_dir)

                if event.get("is_closed"):
                    self.finalize_event(event)
                    break

    def finalize_event(self, event: dict) -> None:
        yes_bets = event.get("bets", {}).get("YES", [])
        no_bets = event.get("bets", {}).get("NO", [])

        yes_total = sum(b.get("amount", 0) for b in yes_bets)
        no_total = sum(b.get("amount", 0) for b in no_bets)

        success = yes_total > no_total
        winners = yes_bets if success else no_bets
        winner_total = yes_total if success else no_total

        pot = yes_total + no_total
        refund = 0.0
        originator = event.get("header", {}).get("originator_pub")
        if success and originator:
            refund = pot * 0.01
            self.balances[originator] = self.balances.get(originator, 0) + refund
            pot -= refund

        if winner_total > 0:
            for bet in winners:
                pub = bet.get("pubkey")
                amt = bet.get("amount", 0)
                if pub:
                    payout = pot * (amt / winner_total)
                    self.balances[pub] = self.balances.get(pub, 0) + payout

        self.save_state()
        self.send_message(
            {
                "type": GossipMessageType.FINALIZED,
                "event": event,
                "balances": self.balances,
            }
        )

    def _handle_message(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == GossipMessageType.NEW_STATEMENT:
            event = message.get("event")
            if event:
                try:
                    self.import_event(event)
                    self.save_state()
                except ValueError:
                    pass
        elif msg_type == GossipMessageType.MINED_MICROBLOCK:
            evt_id = message.get("event_id")
            index = message.get("index")
            seed_hex = message.get("seed")
            depth = message.get("depth", 1)
            if (
                not isinstance(evt_id, str)
                or not isinstance(index, int)
                or not isinstance(seed_hex, str)
            ):
                return
            event = self.events.get(evt_id)
            if not event:
                return
            if index < 0 or index >= len(event["microblocks"]):
                return
            try:
                seed = bytes.fromhex(seed_hex)
            except ValueError:
                return
            block = event["microblocks"][index]
            try:
                d = int(depth)
            except Exception:
                d = 1
            chain = [seed]
            current = seed
            for _ in range(1, d):
                current = minihelix.G(current, len(block))
                chain.append(current)
            current = minihelix.G(current, len(block))
            if current != block:
                return
            event_manager.accept_mined_seed(event, index, chain)
            event_manager.save_event(event, self.events_dir)
        elif msg_type == GossipMessageType.FINALIZED:
            event = message.get("event")
            if not isinstance(event, dict):
                return
            if not verify_statement_id(event):
                return
            try:
                event_manager.validate_parent(event)
            except ValueError:
                return
            evt_id = event.get("header", {}).get("statement_id")
            if not evt_id:
                return
            if evt_id not in self.events:
                self.import_event(event)
            else:
                self.events[evt_id].update(event)
            self.events[evt_id]["is_closed"] = True

            balances = message.get("balances")
            if isinstance(balances, dict):
                for k, v in balances.items():
                    self.balances[k] = v
            else:
                for bet in event.get("bets", {}).get("YES", []):
                    pub = bet.get("pubkey")
                    amt = bet.get("amount", 0)
                    if pub:
                        self.balances[pub] = self.balances.get(pub, 0) + amt
            self.save_state()

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=1.0)
            except queue.Empty:
                continue
            self._handle_message(msg)


def main() -> None:
    """Run a standalone Helix node that mines and syncs via gossip."""
    data_dir = Path("data")
    events_dir = data_dir / "events"
    balances_file = data_dir / "balances.json"
    node = HelixNode(events_dir=str(events_dir), balances_file=str(balances_file))

    threading.Thread(target=node._message_loop, daemon=True).start()

    try:
        while True:
            for event in list(node.events.values()):
                if not event.get("is_closed"):
                    node.mine_event(event)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "HelixNode",
    "simulate_mining",
    "find_seed",
    "verify_seed",
    "verify_statement_id",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
