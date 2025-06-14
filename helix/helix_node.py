"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import event_manager, minihelix, nested_miner
from .config import GENESIS_HASH
from .ledger import load_balances, save_balances
from .gossip import GossipNode, LocalGossipNetwork
from .network import SocketGossipNetwork


class GossipMessageType:
    """Basic gossip message types used between :class:`HelixNode` peers."""
    NEW_EVENT = "NEW_EVENT"
    # backwards compatibility
    NEW_STATEMENT = NEW_EVENT
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    FINALIZED = "FINALIZED"


def simulate_mining(index: int) -> None:
    """Placeholder hook executed before mining ``index``."""
    return None


def find_seed(target: bytes, attempts: int = 1_000_000) -> Optional[bytes]:
    """Search for a seed regenerating ``target``."""
    return minihelix.mine_seed(target, max_attempts=attempts)


def verify_seed(seed: bytes, target: bytes) -> bool:
    """Verify ``seed`` regenerates ``target``."""
    return minihelix.verify_seed(seed, target)


def verify_statement_id(event: Dict[str, Any]) -> bool:
    """Return ``True`` if the statement_id matches the statement hash."""
    statement = event.get("statement")
    stmt_id = event.get("header", {}).get("statement_id")
    if not isinstance(statement, str) or not stmt_id:
        return False
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    return digest == stmt_id


# The rest of the HelixNode class follows as in your working code,
# including the _send(), create_event(), import_event(), mine_event(), finalize_event(),
# _handle_message(), and _message_loop() methods.

# Exported symbols
__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "HelixNode",
    "simulate_mining",
    "find_seed",
    "verify_seed",
    "verify_statement_id",
]
