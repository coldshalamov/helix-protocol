"""WebSocket-based gossip transport for Helix nodes."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Dict, Any

import websockets

from .peer import Peer
from .transport import GossipTransport


class WSGossipTransport(GossipTransport):
    """Gossip transport using WebSockets."""

    def __init__(self, host: str = "0.0.0.0", port: int = 0) -> None:
        self._loop = asyncio.new_event_loop()
        self._recv_queue: "queue.Queue[tuple[Peer, Dict[str, Any]]]" = queue.Queue()
        self._peers: list[Peer] = []
        self._server: websockets.Server | None = None
        self.host = host
        self.port = port
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._start_server(host, port)

    # ------------------------------------------------------------------
    # Internal helpers

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _start_server(self, host: str, port: int) -> None:
        async def _setup() -> None:
            self._server = await websockets.serve(self._handler, host, port)
            self.host, self.port = self._server.sockets[0].getsockname()

        fut = asyncio.run_coroutine_threadsafe(_setup(), self._loop)
        fut.result()

    async def _handler(self, websocket: websockets.ServerConnection) -> None:
        try:
            data = await websocket.recv()
        except Exception:
            return
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return
        addr = websocket.remote_address
        host, port = addr[:2]
        peer = Peer(str(host), int(port))
        self._recv_queue.put((peer, msg))

    # ------------------------------------------------------------------
    # GossipTransport API

    def send(self, peer: Peer, message: Dict[str, Any]) -> None:
        async def _send() -> None:
            uri = f"ws://{peer.host}:{peer.port}"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps(message))
        asyncio.run_coroutine_threadsafe(_send(), self._loop).result()

    def receive(self, timeout: float | None = None) -> tuple[Peer, Dict[str, Any]]:
        return self._recv_queue.get(timeout=timeout)

    def add_peer(self, peer: Peer) -> None:
        if peer not in self._peers:
            self._peers.append(peer)

    def close(self) -> None:
        if self._server is None:
            return

        async def _close() -> None:
            self._server.close()
            await self._server.wait_closed()
        asyncio.run_coroutine_threadsafe(_close(), self._loop).result()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()

