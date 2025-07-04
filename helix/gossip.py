"""Local gossip network for Helix nodes."""

from __future__ import annotations

import json
import queue
import threading
import time
import hashlib
from typing import Any, Dict

from .config import GENESIS_HASH


class LocalGossipNetwork:
    """A simple in-memory broadcast network for :class:`GossipNode`."""

    def __init__(self, *, seen_ttl: float = 300.0) -> None:
        self._nodes: Dict[str, GossipNode] = {}
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}
        self._seen_ttl = seen_ttl

    def _hash_message(self, message: Dict[str, Any]) -> str:
        data = json.dumps(message, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(data).hexdigest()

    def _purge_seen(self) -> None:
        if not self._seen:
            return
        now = time.monotonic()
        expired = [h for h, t in self._seen.items() if now - t > self._seen_ttl]
        for h in expired:
            self._seen.pop(h, None)

    def _is_new(self, message: Dict[str, Any]) -> bool:
        h = self._hash_message(message)
        self._purge_seen()
        return h not in self._seen

    def _mark_seen(self, message: Dict[str, Any]) -> None:
        h = self._hash_message(message)
        self._purge_seen()
        self._seen[h] = time.monotonic()

    def register(self, node: GossipNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def send(self, sender_id: str, message: Dict[str, Any]) -> None:
        """Broadcast ``message`` from ``sender_id`` to all other nodes."""
        msg_type = message.get("type")
        log = msg_type in {
            "NEW_STATEMENT",
            "MINED_MICROBLOCK",
            "EVENT_FINALIZED",
            "FINALIZED",
            "FINALIZED_BLOCK",
            "finalized_block",
        }
        if log:
            print(f"{sender_id} broadcasting {msg_type}")
        with self._lock:
            if not self._is_new(message):
                return
            self._mark_seen(message)
            for node_id, node in self._nodes.items():
                if node_id == sender_id:
                    continue
                node._queue.put(message)
                if log:
                    print(f"{node_id} received {msg_type}")


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
        self.blockchain: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Messaging helpers

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
        """Remove expired entries from ``_seen``."""
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
        """Send ``message`` to all peers on the network."""
        if self._is_new(message):
            self._mark_seen(message)
            self.network.send(self.node_id, message)

    def forward_message(self, message: Dict[str, Any]) -> None:
        """Re-broadcast ``message`` if it hasn't been seen before."""
        if self._is_new(message):
            self._mark_seen(message)
            self.network.send(self.node_id, message)

    # ------------------------------------------------------------------
    # Blockchain helpers

    def broadcast_block(self, block: Dict[str, Any]) -> None:
        """Broadcast a finalized block to peers."""
        self.send_message({"type": "FINALIZED_BLOCK", "block": block})

    def broadcast_finalized_block(self, event_id: str, block_header: Dict[str, Any]) -> None:
        """Broadcast a finalized block header for ``event_id``."""
        self.send_message({
            "type": "finalized_block",
            "event_id": event_id,
            "block_header": block_header,
        })

    def _validate_block(self, block: Dict[str, Any]) -> bool:
        """Return ``True`` if ``block`` correctly links to local chain."""
        import hashlib, json

        height = block.get("height")
        if height is None or height != len(self.blockchain):
            return False
        parent = self.blockchain[-1]["block_id"] if self.blockchain else GENESIS_HASH
        if block.get("parent_id") != parent:
            return False
        copy = dict(block)
        block_id = copy.pop("block_id", None)
        if block_id is None:
            return False
        digest = hashlib.sha256(
            json.dumps(copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return digest == block_id

    def apply_block(self, block: Dict[str, Any]) -> bool:
        """Validate and append ``block`` to ``blockchain``."""
        if not self._validate_block(block):
            return False
        self.blockchain.append(block)
        return True

    # ------------------------------------------------------------------
    # Presence handling

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
                msg_type = msg.get("type")
                print(f"{self.node_id} received message {msg_type}")
                return msg


def record_gossip_messages(
    node: GossipNode,
    path: str,
    *,
    limit: int | None = None,
    timeout: float | None = None,
) -> None:
    """Record messages received by ``node`` to ``path``.

    Messages are stored one-per-line as JSON objects. Recording stops after
    ``limit`` messages if provided, or when ``receive`` times out.
    """

    count = 0
    with open(path, "w", encoding="utf-8") as fh:
        while limit is None or count < limit:
            try:
                msg = node.receive(timeout=timeout)
            except queue.Empty:
                break
            json.dump(msg, fh, separators=(",", ":"))
            fh.write("\n")
            fh.flush()
            count += 1


def replay_gossip_messages(node: GossipNode, path: str) -> None:
    """Replay messages from ``path`` into ``node._handle_message``.

    The provided ``node`` must implement ``_handle_message``. Invalid JSON lines
    are ignored.
    """

    if not hasattr(node, "_handle_message"):
        raise AttributeError("node lacks _handle_message")

    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            node._handle_message(msg)  # type: ignore[attr-defined]


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "record_gossip_messages",
    "replay_gossip_messages",
]
