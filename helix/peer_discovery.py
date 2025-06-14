"""Peer discovery utilities for Helix nodes."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict

from .gossip import GossipNode
from .network import Peer, SocketGossipNetwork


@dataclass
class PeerInfo:
    host: str
    port: int
    last_seen: float = 0.0


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
        host: str = "0.0.0.0",
        port: int = 0,
        peers_file: str = "peers.json",
        ping_interval: float = 30.0,
    ) -> None:
        self.node = node
        self.host = host
        self.port = port
        self.peers_file = peers_file
        self.ping_interval = ping_interval
        self.known_peers: dict[str, PeerInfo] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.load_peers()
        self._reconnect_peers()

    # persistence ---------------------------------------------------------
    def load_peers(self) -> None:
        """Load peer information from ``self.peers_file``."""

        if os.path.exists(self.peers_file):
            try:
                with open(self.peers_file, "r", encoding="utf-8") as fh:
                    peers = json.load(fh)
                if isinstance(peers, list):
                    for peer in peers:
                        if not isinstance(peer, dict):
                            continue
                        node_id = peer.get("node_id")
                        host = peer.get("host")
                        port = peer.get("port")
                        last_seen = peer.get("last_seen", 0.0)
                        if node_id and host and isinstance(port, int):
                            self.known_peers[node_id] = PeerInfo(
                                host=str(host), port=int(port), last_seen=float(last_seen)
                            )
            except Exception as exc:  # pragma: no cover - graceful fail
                print(f"Error loading peers: {exc}")

    def save_peers(self) -> None:
        """Persist ``known_peers`` to ``self.peers_file``."""

        try:
            data = [
                {"node_id": nid, **asdict(info)} for nid, info in self.known_peers.items()
            ]
            with open(self.peers_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:  # pragma: no cover - graceful fail
            print(f"Error saving peers: {exc}")

    def _reconnect_peers(self) -> None:
        """Attempt to re-register any saved peers with the network."""

        if not isinstance(self.node.network, SocketGossipNetwork):
            return
        for node_id, info in self.known_peers.items():
            peer = Peer(info.host, info.port)
            self.node.network.register(node_id, peer)

    # messaging -----------------------------------------------------------
    def send_hello(self) -> None:
        """Broadcast a HELLO message announcing this node."""

        self.node.send_message(
            {
                "type": PeerDiscoveryMessageType.HELLO,
                "sender": self.node.node_id,
                "host": self.host,
                "port": self.port,
            }
        )

    def send_peers(self) -> None:
        """Broadcast the current peer list."""

        self.node.send_message(
            {
                "type": PeerDiscoveryMessageType.PEERS,
                "sender": self.node.node_id,
                "peers": [
                    {"node_id": nid, **asdict(info)}
                    for nid, info in self.known_peers.items()
                ],
            }
        )

    def send_ping(self) -> None:
        """Broadcast a PING message."""

        self.node.send_message(
            {
                "type": PeerDiscoveryMessageType.PING,
                "sender": self.node.node_id,
                "host": self.host,
                "port": self.port,
            }
        )

    def handle_message(self, message: Dict[str, Any]) -> None:
        """Update ``known_peers`` based on ``message``."""

        msg_type = message.get("type")
        sender = message.get("sender")
        print(f"peer_discovery received {msg_type} from {sender}")
        if sender == self.node.node_id:
            return

        if msg_type == PeerDiscoveryMessageType.HELLO:
            host = message.get("host")
            port = message.get("port")
            if sender and host and isinstance(port, int):
                self.known_peers[sender] = PeerInfo(host, int(port), time.time())
                self._reconnect_peers()
            self.send_peers()
            self.save_peers()
            print("handled HELLO -> sent peers")
        elif msg_type == PeerDiscoveryMessageType.PEERS:
            peers = message.get("peers", [])
            if isinstance(peers, list):
                for peer in peers:
                    if not isinstance(peer, dict):
                        continue
                    node_id = peer.get("node_id")
                    host = peer.get("host")
                    port = peer.get("port")
                    last_seen = peer.get("last_seen", time.time())
                    if node_id and host and isinstance(port, int):
                        self.known_peers[node_id] = PeerInfo(
                            host, int(port), float(last_seen)
                        )
                self._reconnect_peers()
                self.save_peers()
            print("handled PEERS -> updated list")
        elif msg_type == PeerDiscoveryMessageType.PING:
            host = message.get("host")
            port = message.get("port")
            if sender and host and isinstance(port, int):
                self.known_peers[sender] = PeerInfo(host, int(port), time.time())
            elif sender in self.known_peers:
                self.known_peers[sender].last_seen = time.time()
            self.node.send_message(
                {
                    "type": PeerDiscoveryMessageType.PONG,
                    "sender": self.node.node_id,
                    "host": self.host,
                    "port": self.port,
                }
            )
            print("handled PING -> sent PONG")
            self._reconnect_peers()
            self.save_peers()
        elif msg_type == PeerDiscoveryMessageType.PONG:
            if sender in self.known_peers:
                self.known_peers[sender].last_seen = time.time()
                self.save_peers()

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


__all__ = ["PeerDiscovery", "PeerDiscoveryMessageType", "PeerInfo"]
