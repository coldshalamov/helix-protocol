"""Local gossip network for Helix nodes."""

from __future__ import annotations

import queue
import threading
from typing import Any, Dict


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
        msg_type = message.get("type")
        log = msg_type in {"NEW_STATEMENT", "MINED_MICROBLOCK", "EVENT_FINALIZED"}
        if log:
            print(f"{sender_id} broadcasting {msg_type}")
        with self._lock:
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
        self._seen: set[str] = set()
        self.network.register(self)

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

    def _mark_seen(self, message: Dict[str, Any]) -> None:
        msg_id = self._message_id(message)
        if msg_id is not None:
            self._seen.add(msg_id)

    def _is_new(self, message: Dict[str, Any]) -> bool:
        msg_id = self._message_id(message)
        return msg_id is None or msg_id not in self._seen

    def send_message(self, message: Dict[str, Any]) -> None:
        """Send ``message`` to all peers on the network."""
        self._mark_seen(message)
        self.network.send(self.node_id, message)

    def forward_message(self, message: Dict[str, Any]) -> None:
        """Re-broadcast ``message`` if it hasn't been seen before."""
        if self._is_new(message):
            self._mark_seen(message)
            self.network.send(self.node_id, message)

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
        msg = self._queue.get(timeout=timeout)
        self._handle_presence(msg)
        return msg


__all__ = ["LocalGossipNetwork", "GossipNode"]
