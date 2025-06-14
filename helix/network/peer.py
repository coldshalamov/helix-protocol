"""Information about peers for network communication."""

from dataclasses import dataclass


@dataclass
class Peer:
    """Represents a remote Helix node."""

    host: str
    port: int
    node_id: str | None = None
