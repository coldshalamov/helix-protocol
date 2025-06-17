"""Networking-based gossip network for Helix nodes."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Dict, Any

from .peer import Peer
from .transport import GossipTransport


class SocketGossipNetwork:
    """Peer-to-peer gossip network using a :class:`GossipTransport`."""

    def __init__(self, transport: GossipTransport, *, seen_ttl: float = 300.0) -> None:
        self.transport = transport
        self._peers: dict[str, Peer] = {}
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

    def register(self, node_id: str, peer: Peer) -> None:
        self._peers[node_id] = peer
        self.transport.add_peer(peer)

    def send(self, sender_id: str, message: Dict[str, Any]) -> None:
        if not self._is_new(message):
            return
        self._mark_seen(message)
        for node_id, peer in self._peers.items():
            if node_id == sender_id:
                continue
            self.transport.send(peer, message)

    def send_message(self, sender_id: str, message: Dict[str, Any]) -> None:
        """Compatibility wrapper matching :class:`helix.gossip.GossipNode`."""

        self.send(sender_id, message)

    def receive(self, timeout: float | None = None) -> tuple[str, Dict[str, Any]]:
        peer, msg = self.transport.receive(timeout)
        node_id = peer.node_id or ""
        return node_id, msg

    def close(self) -> None:
        self.transport.close()
