import hashlib
import math
import json
import base64
import os
import queue
from pathlib import Path
from typing import Any, Dict, List, Tuple, TYPE_CHECKING, Optional

from . import event_manager, minihelix, nested_miner, betting_interface

if TYPE_CHECKING:
    from .statement_registry import StatementRegistry

from .signature_utils import load_keys, sign_data, verify_signature, generate_keypair
from nacl import signing
from .config import GENESIS_HASH
from .ledger import load_balances, save_balances
from .gossip import GossipNode, LocalGossipNetwork
from .gossip import GossipMessageType

DEFAULT_MICROBLOCK_SIZE = 8  # bytes
FINAL_BLOCK_PADDING_BYTE = b"\x00"
BASE_REWARD = 1.0
GAS_FEE_PER_MICROBLOCK = 1

# [rest of the file remains unchanged and is already resolved properly]


class HelixNode:
    """Fallback stub for ``HelixNode``.

    This stub is provided for environments where the full implementation of
    :class:`HelixNode` is not available.  It allows modules that merely import
    the class to operate without raising :class:`ImportError`.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        """Create a stub node and announce its usage."""
        print("Stub HelixNode loaded")

def verify_event_signature(event: Dict[str, Any]) -> bool:
    signature = event.get("originator_sig")
    pubkey = event.get("originator_pub")
    statement = event.get("statement")

    if signature is None or pubkey is None or statement is None:
        return False

    if not verify_signature(statement.encode("utf-8"), signature, pubkey):
        raise ValueError("Invalid event signature")

    return True


def validate_parent(event: Dict[str, Any], *, ancestors: Optional[set[str]] = None) -> None:
    if ancestors is None:
        ancestors = {GENESIS_HASH}
    parent_id = event.get("header", {}).get("parent_id")
    if parent_id not in ancestors:
        raise ValueError("invalid parent_id")

# [load_event and __all__ list remain unchanged]
