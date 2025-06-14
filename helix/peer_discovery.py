"""Peer discovery utilities for Helix nodes."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

from .gossip import GossipNode


class PeerDiscoveryMessageType:
    """Message types used for peer discovery."""

    HELLO = "HELLO"
    PEERS = "PEERS"
    PING = "PING"
    PONG = "PONG"


class PeerDiscovery:
    """Simple peer discovery mechanism over :class:`GossipNode`."""

    def __init__(
        self,
        node: GossipNode,
        *,
        peers_file: str = "peers.json",
        ping_interval: float = 30.0,
    ) -> None:
        self.node = node
        self.peers_file = peers_file
        self.ping_interval = ping_interval
        self.known_peers: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.load_peers()

    # persistence ---------------------------------------------------------
    def load_peers(self) -> None:
        """Load peer IDs from ``self.peers_file`` into ``known_peers``."""

        if os.path.exists(self.peers_file):
            try:
                with open(self.peers_file, "r", encoding="utf-8") as fh:
                    peers = json.load(fh)
                if isinstance(peers, list):
                    self.known_peers.update(peers)
            except Exception as exc:  # pragma: no cover - graceful fail
                print(f"Error loading peers: {exc}")

    def save_peers(self) -> None:
        """Persist ``known_peers`` to ``self.peers_file``."""

        try:
            with open(self.peers_file, "w", encoding="utf-8") as fh:
                json.dump(sorted(self.known_peers), fh, indent=2)
        except Exception as exc:  # pragma: no cover - graceful fail
            print(f"Error saving peers: {exc}")

    # messaging -----------------------------------------------------------
    def send_hello(self) -> None:
        """Broadcast a HELLO message announcing this node."""

        self.node.send_message(
            {"type": PeerDiscoveryMessageType.HELLO, "sender": self.node.node_id}
        )

    def send_peers(self) -> None:
        """Broadcast the current peer list."""

        self.node.send_message(
            {
                "type": PeerDiscoveryMessageType.PEERS,
                "sender": self.node.node_id,
                "peers": list(self.known_peers),
            }
        )

    def send_ping(self) -> None:
        """Broadcast a PING message."""

        self.node.send_message(
            {"type": PeerDiscoveryMessageType.PING, "sender": self.node.node_id}
        )

    def handle_message(self, message: Dict[str, Any]) -> None:
        """Update ``known_peers`` based on ``message``."""

        msg_type = message.get("type")
        sender = message.get("sender")
        print(f"peer_discovery received {msg_type} from {sender}")
        if sender == self.node.node_id:
            return

        if msg_type == PeerDiscoveryMessageType.HELLO:
            if sender:
                self.known_peers.add(sender)
            self.send_peers()
            self.save_peers()
            print("handled HELLO -> sent peers")
        elif msg_type == PeerDiscoveryMessageType.PEERS:
            peers = message.get("peers", [])
            if isinstance(peers, list):
                self.known_peers.update(peers)
                self.save_peers()
            print("handled PEERS -> updated list")
        elif msg_type == PeerDiscoveryMessageType.PING:
            self.node.send_message(
                {"type": PeerDiscoveryMessageType.PONG, "sender": self.node.node_id}
            )
            print("handled PING -> sent PONG")
        elif msg_type == PeerDiscoveryMessageType.PONG:
            pass

    # lifecycle -----------------------------------------------------------
    def start(self) -> None:
        """Start periodic peer pings and announce presence."""

        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._thread.start()
        self.send_hello()

    def stop(self) -> None:
        """Stop periodic pings."""

        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _ping_loop(self) -> None:
        while not self._stop.wait(self.ping_interval):
            self.send_ping()


__all__ = ["PeerDiscovery", "PeerDiscoveryMessageType"]
