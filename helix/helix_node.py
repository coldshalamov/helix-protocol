"""Local gossip network for Helix nodes."""

from __future__ import annotations

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


class LocalGossipNetwork:
    """A simple in-memory broadcast network for :class:`GossipNode`."""

    def __init__(self) -> None:
        self._nodes: Dict[str, GossipNode] = {}
        self._lock = threading.Lock()

    def register(self, node: GossipNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def send(self, sender_id: str, message: Dict[str, Any]) -> None:
        """Broadcast ``message`` from ``sender_id`` to all other nodes."""
        with self._lock:
            for node_id, node in self._nodes.items():
                if node_id != sender_id:
                    node._queue.put(message)


class GossipNode:
    """Participant in a :class:`LocalGossipNetwork`."""

    PRESENCE_PING = "PING"
    PRESENCE_PONG = "PONG"

    def __init__(self, node_id: str, network: LocalGossipNetwork) -> None:
        self.node_id = node_id
        self.network = network
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self.known_peers: set[str] = set()
        self._seen: dict[str, float] = {}
        self._seen_ttl = 300.0  # seconds
        self.network.register(self)

    def _message_id(self, message: Dict[str, Any]) -> str | None:
        msg_type = message.get("type")
        if msg_type is None:
            return None
        if "event" in message:
            event_id = message["event"].get("header", {}).get("statement_id")
        else:
            event_id = message.get("event_id")
        if event_id is None:
            return None
        idx = message.get("index")
        return f"{msg_type}:{event_id}:{idx}" if idx is not None else f"{msg_type}:{event_id}"

    def _purge_seen(self) -> None:
        if not self._seen:
            return
        now = time.monotonic()
        expired = [m for m, t in self._seen.items() if now - t > self._seen_ttl]
        for m in expired:
            self._seen.pop(m, None)

    def _mark_seen(self, message: Dict[str, Any]) -> None:
        msg_id = self._message_id(message)
        if msg_id is not None:
            self._purge_seen()
            self._seen[msg_id] = time.monotonic()

    def _is_new(self, message: Dict[str, Any]) -> bool:
        msg_id = self._message_id(message)
        if msg_id is None:
            return True
        self._purge_seen()
        return msg_id not in self._seen

    def send_message(self, message: Dict[str, Any]) -> None:
        """Send ``message`` to all peers on the network if new."""
        if self._is_new(message):
            self._mark_seen(message)
            self.network.send(self.node_id, message)

    def forward_message(self, message: Dict[str, Any]) -> None:
        """Re-broadcast ``message`` if it hasn't been seen before."""
        if self._is_new(message):
            self._mark_seen(message)
            self.network.send(self.node_id, message)

    def broadcast_presence(self) -> None:
        """Announce this node to all peers."""
        self.send_message({"type": self.PRESENCE_PING, "sender": self.node_id})

    def _handle_presence(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        sender = message.get("sender")
        if not sender or sender == self.node_id:
            return
        if msg_type == self.PRESENCE_PING:
            self.known_peers.add(sender)
            self.send_message({"type": self.PRESENCE_PONG, "sender": self.node_id})
        elif msg_type == self.PRESENCE_PONG:
            self.known_peers.add(sender)

    def receive(self, timeout: float | None = None) -> Dict[str, Any]:
        """Return the next message for this node and handle presence messages."""
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining = None if end is None else max(0, end - time.monotonic())
            if end is not None and remaining == 0:
                raise queue.Empty
            msg = self._queue.get(timeout=remaining)
            if self._is_new(msg):
                self._mark_seen(msg)
                self._handle_presence(msg)
                return msg


class GossipMessageType:
    """Basic gossip message types used between :class:`HelixNode` peers."""
    NEW_STATEMENT = "NEW_STATEMENT"
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


class HelixNode(GossipNode):
    """Minimal Helix node used for tests."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        node_id: str = "NODE",
        network: LocalGossipNetwork | None = None,
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

    def create_event(self, statement: str, *, keyfile: str | None = None) -> dict:
        return event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            parent_id=GENESIS_HASH,
            keyfile=keyfile,
        )

    def import_event(self, event: dict) -> None:
        if event.get("header", {}).get("parent_id") != GENESIS_HASH:
            raise ValueError("invalid parent_id")
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    def mine_event(self, event: dict) -> None:
        for idx, block in enumerate(event["microblocks"]):
            if event["seeds"][idx]:
                continue
            simulate_mining(idx)
            best_seed: Optional[bytes] = None
            best_depth = 0

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
                    candidate = chain[0]
                    if (
                        best_seed is None
                        or found_depth < best_depth
                        or (found_depth == best_depth and len(candidate) < len(best_seed))
                    ):
                        best_seed = candidate
                        best_depth = found_depth

            if best_seed is not None:
                event["seeds"][idx] = {"seed": best_seed, "depth": best_depth}
                event_manager.mark_mined(event, idx)

    def finalize_event(self, event: dict) -> None:
        for bet in event.get("bets", {}).get("YES", []):
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if pub:
                self.balances[pub] = self.balances.get(pub, 0) + amt
        self.save_state()
        self.send_message({"type": GossipMessageType.FINALIZED, "balances": self.balances})

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
        elif msg_type == GossipMessageType.FINALIZED:
            balances = message.get("balances")
            if isinstance(balances, dict):
                self.balances = balances
                save_balances(self.balances, self.balances_file)

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=1.0)
            except queue.Empty:
                continue
            self._handle_message(msg)


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "HelixNode",
    "simulate_mining",
    "find_seed",
    "verify_seed",
]
