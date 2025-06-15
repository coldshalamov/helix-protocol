"""Networking-based gossip network for Helix nodes."""

from __future__ import annotations

from typing import Dict, Any

from .peer import Peer
from .transport import GossipTransport


class SocketGossipNetwork:
    """Peer-to-peer gossip network using a :class:`GossipTransport`."""

    def __init__(self, transport: GossipTransport) -> None:
        self.transport = transport
        self._peers: dict[str, Peer] = {}

    def register(self, node_id: str, peer: Peer) -> None:
        self._peers[node_id] = peer
        self.transport.add_peer(peer)

    def send(self, sender_id: str, message: Dict[str, Any]) -> None:
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
