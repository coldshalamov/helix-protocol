from __future__ import annotations

import json
import logging
import os
import queue
import random
import threading
import hashlib
from pathlib import Path
from typing import Any, Dict, Generator
import time


def simulate_mining(index: int) -> None:
    """Sleep briefly to simulate mining work."""
    time.sleep(0.01)

GENESIS_HASH = "8b846bb24fd5f59dc0b8f968816521aae61c3dfe63e57fe3c8631c58d924a77d"

try:
    from . import event_manager
    from .signature_utils import verify_signature
    from .ledger import load_balances, save_balances
    from .minihelix import mine_seed as find_seed, verify_seed
    from .gossip import GossipNode, LocalGossipNetwork
except ImportError:
    from helix import event_manager
    from helix.signature_utils import verify_signature
    from helix.ledger import load_balances, save_balances
    from helix.minihelix import mine_seed as find_seed, verify_seed
    from helix.gossip import GossipNode, LocalGossipNetwork

GossipMessage = Dict[str, Any]

class GossipMessageType:
    NEW_STATEMENT = "NEW_STATEMENT"
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    EVENT_FINALIZED = "EVENT_FINALIZED"

def verify_originator_signature(event: Dict[str, Any]) -> bool:
    header = event.get("header", {}).copy()
    sig = header.pop("originator_sig", None)
    pub = header.pop("originator_pub", None)
    if not sig or not pub:
        return False
    return verify_signature(repr(header).encode("utf-8"), sig, pub)

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
        genesis_file: str = "genesis.json",
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
        self.genesis_file = genesis_file
        self.balance_lock = threading.Lock()
        self.balances = load_balances(self.balances_file)
        self.genesis_event: Dict[str, Any] = self._load_genesis()
        self.events: Dict[str, Dict[str, Any]] = {}
        self.known_peers: set[str] = set()
        self.load_state()
        self.update_known_peers()

    def _load_genesis(self) -> Dict[str, Any]:
        """Load and verify the genesis file."""
        if not os.path.exists(self.genesis_file):
            raise FileNotFoundError(self.genesis_file)
        with open(self.genesis_file, "rb") as fh:
            data = fh.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != GENESIS_HASH:
            raise ValueError("Genesis hash mismatch")
        try:
            return json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Error loading genesis JSON: {exc}")

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
                    parent_id = event.get("header", {}).get("parent_id")
                    if parent_id != GENESIS_HASH:
                        self.logger.warning("Ignoring event %s with invalid parent", fname)
                        continue
                    evt_id = event["header"]["statement_id"]
                    self.events[evt_id] = event
                except Exception as exc:
                    print(f"Failed to load event {fname}: {exc}")

        for evt in list(self.events.values()):
            if not evt.get("is_closed"):
                threading.Thread(target=self.mine_event, args=(evt,)).start()

    def save_state(self) -> None:
        with open(self.peers_file, "w", encoding="utf-8") as fh:
            json.dump(sorted(self.known_peers), fh, indent=2)
        save_balances(self.balances, self.balances_file)
        for event in self.events.values():
            event_manager.save_event(event, self.events_dir)

    def create_event(self, statement: str, *, keyfile: str | None = None) -> Dict[str, Any]:
        event = event_manager.create_event(statement, self.microblock_size, keyfile=keyfile)
        event["header"]["parent_id"] = GENESIS_HASH
        return event

    def import_event(self, event: Dict[str, Any]) -> None:
        parent = event.get("header", {}).get("parent_id")
        if parent != GENESIS_HASH:
            raise ValueError("invalid parent_id")
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        event_manager.save_event(event, self.events_dir)

    # ------------------------------------------------------------------
    # mining and gossip -------------------------------------------------
    def mine_event(self, event: Dict[str, Any]) -> None:
        """Mine microblocks for ``event`` and broadcast results."""
        for idx, block in enumerate(event["microblocks"]):
            if event["mined_status"][idx]:
                continue
            simulate_mining(idx)
            seed = find_seed(block)
            if seed is None or not verify_seed(seed, block):
                continue
            event["seeds"][idx] = seed
            event_manager.mark_mined(event, idx)
            self.save_state()
            msg = {
                "type": GossipMessageType.MINED_MICROBLOCK,
                "event_id": event["header"]["statement_id"],
                "index": idx,
                "seed": seed.hex(),
            }
            self.send_message(msg)

    def finalize_event(self, event: Dict[str, Any]) -> None:
        """Finalize ``event`` and distribute balances."""
        if not event.get("is_closed"):
            return
        yes_total = sum(b["amount"] for b in event["bets"]["YES"])
        no_total = sum(b["amount"] for b in event["bets"]["NO"])
        if yes_total == 0 and no_total == 0:
            return
        outcome = "YES" if yes_total >= no_total else "NO"
        winners = event["bets"][outcome]
        total = yes_total + no_total
        for bet in winners:
            share = bet["amount"] / total
            with self.balance_lock:
                self.balances[bet["pubkey"]] = self.balances.get(bet["pubkey"], 0) + share * total
        self.save_state()
        self.send_message({
            "type": GossipMessageType.EVENT_FINALIZED,
            "event_id": event["header"]["statement_id"],
        })

    # ------------------------------------------------------------------
    # networking --------------------------------------------------------
    def _message_loop(self) -> None:
        """Process incoming gossip messages."""
        while True:
            try:
                msg = self.receive(timeout=0.1)
            except queue.Empty:
                continue
            msg_type = msg.get("type")
            if msg_type == GossipMessageType.NEW_STATEMENT:
                event = msg.get("event")
                if not event:
                    continue
                evt_id = event.get("header", {}).get("statement_id")
                if evt_id in self.events:
                    continue
                if not verify_originator_signature(event):
                    self.logger.warning("Invalid signature for %s", evt_id)
                    continue
                self.events[evt_id] = event
                self.save_state()
                self.forward_message(msg)
                threading.Thread(target=self.mine_event, args=(event,)).start()
            elif msg_type == GossipMessageType.MINED_MICROBLOCK:
                evt_id = msg.get("event_id")
                idx = msg.get("index")
                seed_hex = msg.get("seed")
                if evt_id not in self.events or idx is None or seed_hex is None:
                    continue
                event = self.events[evt_id]
                seed = bytes.fromhex(seed_hex)
                block = event["microblocks"][idx]
                if not verify_seed(seed, block):
                    continue
                if event["mined_status"][idx]:
                    continue
                event["seeds"][idx] = seed
                event_manager.mark_mined(event, idx)
                self.save_state()
                self.forward_message(msg)
            elif msg_type == GossipMessageType.EVENT_FINALIZED:
                evt_id = msg.get("event_id")
                if evt_id not in self.events:
                    continue
                self.forward_message(msg)


__all__ = [
    "HelixNode",
    "GossipMessageType",
    "simulate_mining",
    "find_seed",
    "verify_seed",
]
