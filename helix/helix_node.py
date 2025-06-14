from __future__ import annotations

import json
import logging
import os
import queue
import random
import threading
from pathlib import Path
from typing import Any, Dict, Generator

try:
    from . import event_manager
    from .signature_utils import verify_signature
    from .ledger import load_balances, save_balances
    from .minihelix import mine_seed as find_seed, verify_seed
    from .gossip import GossipNode, LocalGossipNetwork
except ImportError:  # pragma: no cover - allow running as a script
    from helix import event_manager
    from helix.signature_utils import verify_signature
    from helix.ledger import load_balances, save_balances
    from helix.minihelix import mine_seed as find_seed, verify_seed
    from helix.gossip import GossipNode, LocalGossipNetwork

# ----------------------------------------------------------------------------
# Gossip message definitions
# ----------------------------------------------------------------------------

GossipMessage = Dict[str, Any]

class GossipMessageType:
    NEW_STATEMENT = "NEW_STATEMENT"
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    EVENT_FINALIZED = "EVENT_FINALIZED"

# ----------------------------------------------------------------------------
# Signature Verification
# ----------------------------------------------------------------------------

def verify_originator_signature(event: Dict[str, Any]) -> bool:
    header = event.get("header", {}).copy()
    sig = header.pop("originator_sig", None)
    pub = header.pop("originator_pub", None)
    if not sig or not pub:
        return False
    return verify_signature(repr(header).encode("utf-8"), sig, pub)

# ----------------------------------------------------------------------------
# Core node logic
# ----------------------------------------------------------------------------

class HelixNode(GossipNode):
    def __init__(
        self,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        *,
        events_dir: str = "events",
        balances_file: str = "balances.json",
        node_id: str | None = None,
        network: LocalGossipNetwork | None = None,
        peers_file: str = "peers.json",
    ) -> None:
        if network is None:
            network = LocalGossipNetwork()
        if node_id is None:
            node_id = hex(random.randint(0, 0xFFFF))[2:]
        super().__init__(node_id, network)
        self.microblock_size = microblock_size
        self.logger = logging.getLogger(self.__class__.__name__)
        self.events_dir = events_dir
        self.balances_file = balances_file
        self.peers_file = peers_file
        self.balances = load_balances(self.balances_file)
        self.events: Dict[str, Dict[str, Any]] = {}
        self.known_peers: set[str] = set()
        self.load_state()
        self.update_known_peers()

    def update_known_peers(self) -> None:
        try:
            self.known_peers = set(self.network._nodes.keys())
            self.save_state()
        except Exception as exc:
            print(f"Failed to update peers: {exc}")

    def load_state(self) -> None:
        if os.path.exists(self.peers_file):
            try:
                with open(self.peers_file, "r", encoding="utf-8") as fh:
                    peers = json.load(fh)
                    if isinstance(peers, list):
                        self.known_peers = set(peers)
            except Exception as exc:
                print(f"Error loading peers: {exc}")

        if os.path.isdir(self.events_dir):
            for fname in os.listdir(self.events_dir):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(self.events_dir, fname)
                try:
                    event = event_manager.load_event(path)
                    evt_id = event["header"]["statement_id"]
                    self.events[evt_id] = event
                except Exception as exc:
                    print(f"Failed to load event {fname}: {exc}")

        for evt in list(self.events.values()):
            if not evt.get("is_closed"):
                threading.Thread(target=self.mine_event, args=(evt,)).start()

    def save_state(self) -> None:
        try:
            with open(self.peers_file, "w", encoding="utf-8") as fh:
                json.dump(list(self.known_peers), fh, indent=2)
        except Exception as exc:
            print(f"Error saving peers: {exc}")

        for event in self.events.values():
            try:
                event_manager.save_event(event, self.events_dir)
            except Exception as exc:
                print(f"Failed to save event {event['header']['statement_id']}: {exc}")

    def listen_for_statements(self) -> Generator[str, None, None]:
        yield "The James Webb telescope detected complex organic molecules in interstellar space."

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
        miner_id = random.randint(1000, 9999)
        self.logger.info("Miner %s started microblock %d", miner_id, index)
        target = event["microblocks"][index]
        seed = find_seed(target, max_attempts=1000000)
        if seed is not None and verify_seed(seed, target):
            event["seeds"][index] = seed
            msg = {
                "type": GossipMessageType.MINED_MICROBLOCK,
                "event_id": event["header"]["statement_id"],
                "index": index,
                "seed": seed.hex(),
            }
            self.send_message(msg)
            event_manager.mark_mined(event, index)
            status = "mined"
        else:
            status = "failed"
        self.logger.info("Microblock %d %s by miner %s", index, status, miner_id)
        mined = sum(1 for m in event["mined_status"] if m)
        total = len(event["microblocks"])
        self.logger.info("Progress: %d/%d mined", mined, total)

    def mine_event(self, event: Dict[str, Any]) -> None:
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
            self.send_message(
                {
                    "type": GossipMessageType.EVENT_FINALIZED,
                    "event_id": event["header"]["statement_id"],
                }
            )
        else:
            self.logger.warning("Event did not close properly")

    def handle_message(self, message: GossipMessage) -> None:
        try:
            mtype = message.get("type")
            if mtype == GossipMessageType.NEW_STATEMENT:
                event = message.get("event")
                if not isinstance(event, dict):
                    return
                evt_id = event.get("header", {}).get("statement_id")
                if not evt_id or evt_id in self.events:
                    return
                print(f"Node {self.node_id}: received new statement {evt_id}")
                self.events[evt_id] = event
                self.save_state()
                threading.Thread(target=self.mine_event, args=(event,)).start()

            elif mtype == GossipMessageType.MINED_MICROBLOCK:
                evt_id = message.get("event_id")
                index = message.get("index")
                seed_hex = message.get("seed")
                if evt_id not in self.events or seed_hex is None or index is None:
                    return
                event = self.events[evt_id]
                if index < 0 or index >= len(event["microblocks"]):
                    return
                if event["mined_status"][index]:
                    return
                seed = bytes.fromhex(seed_hex)
                block = event["microblocks"][index]
                if verify_seed(seed, block):
                    print(f"Node {self.node_id}: verified microblock {index} for {evt_id}")
                    event["seeds"][index] = seed
                    event_manager.mark_mined(event, index)
                    self.save_state()
                    self.send_message(message)

            elif mtype == GossipMessageType.EVENT_FINALIZED:
                evt_id = message.get("event_id")
                if evt_id in self.events:
                    print(f"Node {self.node_id}: event {evt_id} finalized")
        except Exception as exc:
            print(f"Error handling message: {exc}")

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=1)
            except queue.Empty:
                continue
            self.handle_message(msg)

    def resolve_bets(self, event: Dict[str, Any]) -> None:
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
        listener = threading.Thread(target=self._message_loop, daemon=True)
        listener.start()

        for statement in self.listen_for_statements():
            event = self.create_event(statement)
            evt_id = event["header"]["statement_id"]
            self.events[evt_id] = event
            self.save_state()
            self.send_message({"type": GossipMessageType.NEW_STATEMENT, "event": event})
            self.mine_event(event)
            self.save_state()
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
