"""Abstract base classes for network transports."""

from __future__ import annotations

import abc
from typing import Dict, Any


class GossipTransport(abc.ABC):
    """Base API for sending gossip messages between nodes."""

    @abc.abstractmethod
    def send(self, peer: "Peer", message: Dict[str, Any]) -> None:
        """Send a message to ``peer``."""

    @abc.abstractmethod
    def receive(self, timeout: float | None = None) -> tuple["Peer", Dict[str, Any]]:
        """Wait for the next incoming message."""

    @abc.abstractmethod
    def add_peer(self, peer: "Peer") -> None:
        """Register a new peer with this transport."""

    @abc.abstractmethod
    def close(self) -> None:
        """Shut down the transport and release resources."""
