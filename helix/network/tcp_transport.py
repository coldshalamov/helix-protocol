"""Simple TCP-based gossip transport."""

from __future__ import annotations

import json
import socket
import threading
import queue
from typing import Dict, Any

from .peer import Peer
from .transport import GossipTransport


class TCPGossipTransport(GossipTransport):
    """TCP transport using a dedicated listen socket."""

    def __init__(self, host: str = "0.0.0.0", port: int = 0) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self.host, self.port = self._server.getsockname()
        self._server.listen()
        self._peers: list[Peer] = []
        self._recv_queue: "queue.Queue[tuple[Peer, Dict[str, Any]]]" = queue.Queue()
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, addr = self._server.accept()
                threading.Thread(target=self._client_loop, args=(conn, addr), daemon=True).start()
            except OSError:
                break

    def _client_loop(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        with conn:
            data = conn.recv(65536)
            if not data:
                return
            try:
                msg = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                return
            peer = Peer(addr[0], addr[1])
            self._recv_queue.put((peer, msg))

    def send(self, peer: Peer, message: Dict[str, Any]) -> None:
        data = json.dumps(message).encode("utf-8")
        with socket.create_connection((peer.host, peer.port)) as sock:
            sock.sendall(data)

    def receive(self, timeout: float | None = None) -> tuple[Peer, Dict[str, Any]]:
        return self._recv_queue.get(timeout=timeout)

    def add_peer(self, peer: Peer) -> None:
        if peer not in self._peers:
            self._peers.append(peer)

    def close(self) -> None:
        self._running = False
        try:
            self._server.close()
        finally:
            pass

